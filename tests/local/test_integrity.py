import copy
import json
import tempfile
import unittest
from pathlib import Path
from localchain.core import Engine, atomic_json, now
from localchain.ledger import SimulationLedger


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = SimulationLedger(self.root / 'chain.sqlite3')
        self.engine = Engine(self.root, self.ledger)
        self.source = self.engine.add_source('Example application')
        self.sid = self.source['id']
        self.originals = [{'event_id': f'evt-{i}', 'sequence': i, 'timestamp': now(), 'actor': 'vijay', 'action': 'login', 'message': 'Original', 'metadata': {'ip': '127.0.0.1'}} for i in range(1,4)]
        self.engine.ingest(self.sid, self.originals)
        self.assertEqual(self.engine.verify()['status'], 'VERIFIED')

    def tearDown(self):
        self.engine.db.close()
        self.temp.cleanup()

    def write(self, value):
        atomic_json(self.engine.path(self.sid), value)
        return self.engine.verify()

    def test_repeated_tamper_restore_retains_every_transition(self):
        altered = copy.deepcopy(self.originals)
        altered[1]['message'] = 'Attack A'
        first = self.write(altered)
        self.assertEqual([r['state'] for r in first['logs']], ['VERIFIED','MODIFIED','VERIFIED'])
        self.assertEqual(first['logs'][1]['changes'], ['message'])
        self.assertEqual(len(self.engine.verify()['history']), 1)
        altered[1]['message'] = 'Attack B'
        self.assertEqual(len(self.write(altered)['history']), 2)
        self.assertEqual(self.write(self.originals)['status'], 'VERIFIED')
        self.write(altered)
        last = self.write(self.originals)
        self.assertEqual([h['kind'] for h in reversed(last['history'])], ['MODIFIED','MODIFIED','RESTORED','MODIFIED','RESTORED'])
        self.assertTrue(all(h['receipt'] for h in last['history']))

    def test_delete_has_no_cascading_reorder_false_alarm(self):
        result = self.write([self.originals[0], self.originals[2]])
        self.assertEqual([r['state'] for r in result['logs']], ['VERIFIED','DELETED','VERIFIED'])
        self.assertEqual(self.write(self.originals)['history'][0]['kind'], 'RESTORED')

    def test_duplicate_in_middle_does_not_cascade_reorder_alerts(self):
        result = self.write([self.originals[0], self.originals[1], self.originals[1], self.originals[2]])
        self.assertEqual([r['state'] for r in result['logs']], ['VERIFIED', 'DUPLICATE', 'VERIFIED'])

    def test_reordering_is_detected(self):
        result = self.write([self.originals[1], self.originals[0], self.originals[2]])
        self.assertEqual([r['state'] for r in result['logs']], ['REORDERED','REORDERED','VERIFIED'])

    def test_duplicate_and_unexpected(self):
        extra = {**self.originals[0], 'event_id': 'uncommitted', 'sequence': 10}
        result = self.write(self.originals + [self.originals[1], extra])
        self.assertEqual(result['logs'][1]['state'], 'DUPLICATE')
        self.assertEqual(result['logs'][-1]['state'], 'UNEXPECTED')
        self.assertEqual(self.write(self.originals)['status'], 'VERIFIED')

    def test_idempotent_retry_never_repairs_tampering(self):
        altered = copy.deepcopy(self.originals)
        altered[0]['message'] = 'Modified'
        self.write(altered)
        self.assertEqual(self.engine.ingest(self.sid,self.originals)['accepted'], 0)
        self.assertEqual(self.engine.verify()['logs'][0]['state'], 'MODIFIED')
        with self.assertRaises(ValueError):
            self.engine.ingest(self.sid,altered)

    def test_all_fields_are_committed(self):
        altered = copy.deepcopy(self.originals)
        altered[0]['metadata']['ip'] = '10.0.0.2'
        self.assertEqual(self.write(altered)['logs'][0]['state'], 'MODIFIED')
        altered[0]['new_field'] = True
        self.assertEqual(self.write(altered)['logs'][0]['state'], 'MODIFIED')

    def test_missing_or_malformed_source_never_looks_clean(self):
        self.engine.path(self.sid).unlink()
        self.assertEqual(self.engine.verify()['status'], 'ALERT')
        self.engine.path(self.sid).write_text('invalid')
        self.assertEqual(self.engine.verify()['sources'][0]['state'], 'SOURCE_UNREADABLE')
        self.assertEqual(self.write(self.originals)['history'][0]['kind'], 'RESTORED')

    def test_outage_does_not_resolve_alert(self):
        altered = copy.deepcopy(self.originals)
        altered[0]['message'] = 'Attack'
        self.write(altered)
        atomic_json(self.engine.path(self.sid), self.originals)
        old = self.ledger.get
        self.ledger.get = lambda key: (_ for _ in ()).throw(ConnectionError('Node offline'))
        result = self.engine.verify()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(len(result['history']), 1)
        self.ledger.get = old
        self.assertEqual(self.engine.verify()['history'][0]['kind'], 'RESTORED')

    def test_durable_history_survives_restart(self):
        altered = copy.deepcopy(self.originals)
        altered[0]['message'] = 'Attack'
        self.write(altered)
        self.engine.db.close()
        self.engine = Engine(self.root,self.ledger)
        self.assertEqual(self.engine.verify()['status'], 'ALERT')
        self.assertEqual(len(self.engine.history()), 1)
        self.assertEqual(self.write(self.originals)['history'][0]['kind'], 'RESTORED')

    def test_outbox_retries_after_chain_failure(self):
        original_put = self.ledger.put
        self.ledger.put = lambda *args: (_ for _ in ()).throw(ConnectionError('Node offline'))
        event = {**self.originals[0], 'event_id':'evt-4', 'sequence':4}
        self.engine.ingest(self.sid, [event])
        self.assertEqual(self.engine.verify()['status'], 'UNAVAILABLE')
        self.assertEqual(self.engine.get_snapshot()['pending'], 1)
        self.ledger.put = original_put
        self.assertEqual(self.engine.verify()['status'], 'VERIFIED')
        self.assertEqual(self.engine.get_snapshot()['pending'], 0)

    def test_evidence_tamper_fails_closed(self):
        with self.engine.db:
            self.engine.db.execute("UPDATE logs SET original='{}' WHERE event_id='evt-1'")
        self.assertEqual(self.engine.verify()['status'], 'UNAVAILABLE')

    def test_append_only_history_rejects_edit_and_delete(self):
        self.write(self.originals[1:])
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.db.execute('DELETE FROM observations')
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.db.execute("UPDATE observations SET kind='RESTORED'")
        self.engine.db.rollback()

    def test_invalid_payload_does_not_partially_ingest(self):
        valid = {**self.originals[0], 'event_id':'evt-4', 'sequence':4}
        for bad in (None, [], [valid,{}], [{**valid,'sequence':True}], [{**valid,'timestamp':'bad'}], [valid,valid]):
            with self.assertRaises(ValueError):
                self.engine.ingest(self.sid,bad)
        self.assertEqual(len(self.engine.read(self.sid)), 3)

    def test_source_token_is_scoped(self):
        other = self.engine.add_source('Second app')
        self.assertTrue(self.engine.authorize_source(self.sid,self.source['token']))
        self.assertFalse(self.engine.authorize_source(other['id'],self.source['token']))

    def test_deleted_metadata_is_detected_against_chain_inventory(self):
        with self.engine.db:
            self.engine.db.execute("DELETE FROM logs WHERE event_id='evt-1'")
        self.assertEqual(self.engine.verify()['status'], 'UNAVAILABLE')

    def test_missing_source_registration_fails_closed(self):
        with self.engine.db:
            self.engine.db.execute('DELETE FROM sources')
        self.assertEqual(self.engine.verify()['status'], 'UNAVAILABLE')

    def test_symlink_source_rejected(self):
        self.engine.path(self.sid).unlink()
        target = self.root/'outside.json'
        target.write_text('[]')
        self.engine.path(self.sid).symlink_to(target)
        self.assertEqual(self.engine.verify()['status'], 'ALERT')


if __name__ == '__main__':
    unittest.main()
