"""Durable outbox, source snapshots, exact verification, append-only observations."""
import copy
import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from localchain.ledger import canonical, digest


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def validate(event):
    if not isinstance(event, dict):
        raise ValueError('Each log must be a JSON object')
    for field in ('event_id', 'timestamp', 'action', 'actor', 'message'):
        if not isinstance(event.get(field), str) or not event[field].strip() or len(event[field]) > 10000:
            raise ValueError(f'{field} must be a non-empty string (maximum 10000 characters)')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', event['event_id']):
        raise ValueError('event_id must use letters, numbers, dot, colon, underscore or dash')
    if type(event.get('sequence')) is not int or event['sequence'] < 1:
        raise ValueError('sequence must be a positive integer')
    try:
        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError('timestamp must be ISO 8601 with a timezone')
    if len(canonical(event).encode()) > 32768:
        raise ValueError('Log exceeds 32 KiB')


class Engine:
    def __init__(self, directory, ledger):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        identity_file = self.root / 'workspace.id'
        if not identity_file.exists():
            if (self.root / 'audit.sqlite3').exists():
                raise RuntimeError('Workspace identity missing. Restore it from backup; do not reset the ledger.')
            identity_file.write_text(uuid.uuid4().hex)
        self.namespace = 'ws:' + identity_file.read_text().strip() + ':'
        self.logs = self.root / 'sources'
        self.logs.mkdir(exist_ok=True)
        self.ledger = ledger
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'audit.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,name TEXT NOT NULL,token TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS logs(source TEXT,event_id TEXT,sequence INTEGER,original TEXT,hash TEXT,key TEXT UNIQUE,receipt TEXT,created TEXT,PRIMARY KEY(source,event_id),UNIQUE(source,sequence));
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT,event_id TEXT,kind TEXT,created TEXT,payload TEXT,hash TEXT,key TEXT UNIQUE,receipt TEXT);
        CREATE TABLE IF NOT EXISTS states(source TEXT,event_id TEXT,fingerprint TEXT,state TEXT,PRIMARY KEY(source,event_id));
        CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'History is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS observations_no_edit BEFORE UPDATE OF source,event_id,kind,created,payload,hash,key ON observations BEGIN SELECT RAISE(ABORT,'History is append-only'); END;
        ''')
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(sources)')}
        for name, definition in [('mode', "TEXT NOT NULL DEFAULT 'api'"), ('last_seen', 'TEXT'), ('remote_error', 'TEXT')]:
            if name not in columns:
                self.db.execute(f'ALTER TABLE sources ADD COLUMN {name} {definition}')
        self.db.commit()
        self.snapshot = {'status': 'STARTING', 'checked_at': None, 'logs': [], 'sources': [], 'history': [], 'network': {'connected': False, 'mode': ledger.mode}, 'error': ''}
        self.scan_lock = threading.Lock()

    def sources(self):
        return [dict(r) for r in self.db.execute('SELECT id,name,created,mode,last_seen,remote_error FROM sources ORDER BY created')]

    def add_source(self, name, mode='api'):
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError('Source name must be 1–80 characters')
        if mode not in ('api', 'file'):
            raise ValueError('Choose API or file agent')
        with self.lock, self.db:
            sid = uuid.uuid4().hex[:12]
            token = secrets.token_urlsafe(32)
            self.db.execute('INSERT INTO sources(id,name,token,created,mode) VALUES (?,?,?,?,?)', (sid, name.strip(), token, now(), mode))
            atomic_json(self.path(sid), [])
            return {'id': sid, 'name': name.strip(), 'token': token, 'mode': mode, 'path': str(self.path(sid))}

    def path(self, sid):
        if not re.fullmatch(r'[a-f0-9]{12}', sid):
            raise ValueError('Invalid source ID')
        return self.logs / (sid + '.json')

    def authorize_source(self, sid, token):
        with self.lock:
            row = self.db.execute('SELECT token FROM sources WHERE id=?', (sid,)).fetchone()
            return bool(row and secrets.compare_digest(row[0], token))

    def read(self, sid):
        path = self.path(sid)
        if path.is_symlink():
            raise ValueError('Source symlinks are not allowed')
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Source exceeds 16 MiB; rotate to a new source')
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            raise ValueError('Source must be a JSON array of log objects')
        return value

    def ingest(self, sid, events):
        if not isinstance(events, list) or not 1 <= len(events) <= 100:
            raise ValueError('Supply 1–100 logs')
        for event in events:
            validate(event)
        if len({e['event_id'] for e in events}) != len(events) or len({e['sequence'] for e in events}) != len(events):
            raise ValueError('Duplicate event ID or sequence in request')
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sources WHERE id=?', (sid,)).fetchone():
                raise ValueError('Unknown source')
            current = self.read(sid)
            maximum = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM logs WHERE source=?', (sid,)).fetchone()[0]
            additions = []
            for event in events:
                row = self.db.execute('SELECT hash FROM logs WHERE source=? AND event_id=?', (sid, event['event_id'])).fetchone()
                if row:
                    if row[0] != digest(event):
                        raise ValueError('Event ID already committed with different content')
                    continue  # An idempotent retry never overwrites a modified source.
                if event['sequence'] <= maximum:
                    raise ValueError('New logs must have increasing, unique sequence numbers')
                if any(e.get('event_id') == event['event_id'] or e.get('sequence') == event['sequence'] for e in current):
                    raise ValueError('Uncommitted entry already exists in source; investigate it first')
                maximum = event['sequence']
                additions.append(event)
            with self.db:
                for event in additions:
                    key = self.namespace + 'log:' + sid + ':' + event['event_id']
                    self.db.execute('INSERT INTO logs VALUES (?,?,?,?,?,?,NULL,?)', (sid, event['event_id'], event['sequence'], canonical(event), digest(event), key, now()))
            # DB first: a crash here leaves a detectable missing source log, never an untracked trusted log.
            atomic_json(self.path(sid), current + additions)
            with self.db:
                self.db.execute('UPDATE sources SET last_seen=? WHERE id=?', (now(), sid))
            return {'accepted': len(additions), 'status': 'PENDING', 'message': 'Saved. Background worker will anchor and verify.'}

    def rotate_source_token(self, sid):
        with self.lock, self.db:
            row = self.db.execute('SELECT name,mode FROM sources WHERE id=?', (sid,)).fetchone()
            if not row:
                raise ValueError('Unknown source')
            token = secrets.token_urlsafe(32)
            self.db.execute('UPDATE sources SET token=? WHERE id=?', (token, sid))
            return {'id': sid, 'name': row['name'], 'mode': row['mode'], 'token': token}

    def source_unavailable(self, sid, message):
        if not isinstance(message, str) or len(message) > 500:
            raise ValueError('Provide an error message of at most 500 characters')
        with self.lock, self.db:
            self.db.execute('UPDATE sources SET remote_error=?,last_seen=? WHERE id=?', (message,now(),sid))
        return {'status':'SOURCE_UNAVAILABLE'}

    def sync(self, sid, events):
        """Mirror observed source contents; keep previously trusted originals immutable."""
        if not isinstance(events, list) or len(events) > 10000 or any(not isinstance(e, dict) for e in events):
            raise ValueError('Supply an array of at most 10000 log objects')
        with self.lock:
            source = self.db.execute('SELECT mode FROM sources WHERE id=?', (sid,)).fetchone()
            if not source or source['mode'] != 'file':
                raise ValueError('Snapshot sync requires a file-agent source')
            known = {r['event_id'] for r in self.db.execute('SELECT event_id FROM logs WHERE source=?', (sid,))}
            maximum = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM logs WHERE source=?', (sid,)).fetchone()[0]
            additions = []
            seen = set()
            for event in events:
                eid = event.get('event_id')
                # Unknown/repeated entries stay untrusted and are flagged by the verifier.
                # Only well-formed append events can receive a first commitment.
                if isinstance(eid, str) and eid not in known and eid not in seen:
                    try:
                        validate(event)
                    except ValueError:
                        continue
                    if event['sequence'] > maximum:
                        maximum = event['sequence']
                        seen.add(eid)
                        additions.append(event)
            with self.db:
                for event in additions:
                    key = self.namespace + 'log:' + sid + ':' + event['event_id']
                    self.db.execute('INSERT INTO logs VALUES (?,?,?,?,?,?,NULL,?)',
                                    (sid,event['event_id'],event['sequence'],canonical(event),digest(event),key,now()))
                self.db.execute('UPDATE sources SET last_seen=?,remote_error=NULL WHERE id=?', (now(), sid))
            atomic_json(self.path(sid), events)
            return {'accepted':len(additions), 'observed':len(events), 'status':'PENDING'}

    def observe(self, sid, eid, kind, actual, expected, details):
        fingerprint = digest({'kind': kind, 'actual': actual})
        previous = self.db.execute('SELECT fingerprint,state FROM states WHERE source=? AND event_id=?', (sid, eid)).fetchone()
        if previous and previous['fingerprint'] == fingerprint:
            return
        if kind != 'VERIFIED' or (previous and previous['state'] != 'VERIFIED'):
            event_kind = 'RESTORED' if kind == 'VERIFIED' else kind
            prev = self.db.execute('SELECT hash FROM observations ORDER BY id DESC LIMIT 1').fetchone()
            payload = {'source': sid, 'event_id': eid, 'kind': event_kind, 'timestamp': now(), 'expected_hash': expected,
                       'actual_hash': actual, 'details': details, 'previous_observation': prev[0] if prev else '0' * 64}
            key = self.namespace + 'incident:' + uuid.uuid4().hex
            self.db.execute('INSERT INTO observations(source,event_id,kind,created,payload,hash,key) VALUES(?,?,?,?,?,?,?)',
                            (sid, eid, event_kind, payload['timestamp'], canonical(payload), digest(payload), key))
        self.db.execute('INSERT OR REPLACE INTO states VALUES(?,?,?,?)', (sid, eid, fingerprint, kind))

    def flush(self):
        # One transaction sender/worker serializes nonces. Restart retries use immutable keys.
        for table in ('logs', 'observations'):
            for row in self.db.execute(f'SELECT * FROM {table} WHERE receipt IS NULL').fetchall():
                content = json.loads(row['original' if table == 'logs' else 'payload'])
                if digest(content) != row['hash']:
                    raise RuntimeError('Pending evidence was modified; anchoring blocked')
                receipt = self.ledger.put(row['key'], row['hash'])
                with self.db:
                    self.db.execute(f'UPDATE {table} SET receipt=? WHERE key=?', (canonical(receipt), row['key']))

    def verify(self):
        if not self.scan_lock.acquire(blocking=False):
            return self.get_snapshot()
        try:
            with self.lock:
                try:
                    self.flush()
                    network = self.ledger.status()
                    local_keys = {r[0] for r in self.db.execute('SELECT key FROM logs UNION SELECT key FROM observations')}
                    chain_keys = {k for k in self.ledger.keys() if k.startswith(self.namespace)}
                    if chain_keys != local_keys:
                        raise RuntimeError('Ledger inventory differs from local evidence. Restore missing evidence from backup.')
                    orphaned = self.db.execute('SELECT count(*) FROM logs WHERE source NOT IN (SELECT id FROM sources)').fetchone()[0]
                    if orphaned:
                        raise RuntimeError('Source registration missing from local evidence')
                    rows, source_states = [], []
                    for source in self.sources():
                        sid = source['id']
                        expected_rows = self.db.execute('SELECT * FROM logs WHERE source=? ORDER BY sequence', (sid,)).fetchall()
                        if source['mode'] == 'file' and not source['last_seen'] and not expected_rows and not source['remote_error']:
                            source_states.append({**source,'state':'PENDING','count':0,'path':str(self.path(sid))})
                            continue
                        try:
                            if source['mode'] == 'file':
                                if source['remote_error']:
                                    raise ValueError(source['remote_error'])
                                if not source['last_seen'] or (datetime.now(timezone.utc)-datetime.fromisoformat(source['last_seen'])).total_seconds()>15:
                                    raise ValueError('Source agent is not connected; current external content is unavailable')
                            current = self.read(sid)
                            read_error = None
                        except (OSError, ValueError) as exc:
                            current = []
                            read_error = str(exc)
                        if read_error:
                            with self.db:
                                self.observe(sid, '@source', 'SOURCE_UNREADABLE', digest(read_error), '', {'message': read_error})
                            source_states.append({**source, 'state': 'SOURCE_UNREADABLE', 'count': len(expected_rows), 'path': str(self.path(sid))})
                            for row in expected_rows:
                                rows.append(self.row_view(row, None, 'UNAVAILABLE', '', [], source['name']))
                            continue
                        with self.db:
                            self.observe(sid, '@source', 'VERIFIED', '', '', {'message': 'Source is readable again'})
                        ids = [e.get('event_id') for e in current]
                        counts = Counter(canonical(eid) for eid in ids)
                        expected_ids = {r['event_id'] for r in expected_rows}
                        # Compare relative order of surviving known IDs: deleting one log does not flag every subsequent log.
                        survivors = list(dict.fromkeys(eid for eid in ids if isinstance(eid, str) and eid in expected_ids))
                        ordered = [r['event_id'] for r in expected_rows if r['event_id'] in survivors]
                        misplaced = {a for a, b in zip(survivors, ordered) if a != b}
                        for row in expected_rows:
                            trusted = self.ledger.get(row['key'])
                            if trusted is None or trusted != row['hash']:
                                raise RuntimeError('Missing or conflicting blockchain commitment: ' + row['event_id'])
                            original = json.loads(row['original'])
                            if digest(original) != trusted:
                                raise RuntimeError('Evidence store was modified: ' + row['event_id'])
                            matches = [e for e in current if e.get('event_id') == row['event_id']]
                            actual = matches[0] if matches else None
                            actual_hash = digest(actual) if actual is not None else ''
                            changes = [k for k in sorted(set(original) | set(actual or {})) if (actual or {}).get(k) != original.get(k) or (k in (actual or {})) != (k in original)]
                            if not matches:
                                state = 'DELETED'
                            elif counts[canonical(row['event_id'])] > 1:
                                state = 'DUPLICATE'
                                actual_hash = digest(matches)
                            elif actual_hash != trusted:
                                state = 'MODIFIED'
                            elif row['event_id'] in misplaced:
                                state = 'REORDERED'
                                actual_hash = digest(survivors)
                            else:
                                state = 'VERIFIED'
                            with self.db:
                                self.observe(sid, row['event_id'], state, actual_hash, trusted, {'changed_fields': changes, 'observed': actual, 'order': survivors if state == 'REORDERED' else None})
                            rows.append(self.row_view(row, actual, state, actual_hash, changes, source['name']))
                        unknown = set()
                        for index, event in enumerate(current):
                            if not isinstance(event.get('event_id'), str) or event['event_id'] not in expected_ids:
                                eid = '@unexpected:' + str(index) + ':' + str(event.get('event_id', '?'))[:128]
                                unknown.add(eid)
                                with self.db:
                                    self.observe(sid, eid, 'UNEXPECTED', digest(event), '', {'observed': event})
                                rows.append({'source': sid, 'source_name': source['name'], 'event_id': eid, 'state': 'UNEXPECTED', 'current': event, 'original': None, 'actual_hash': digest(event), 'expected_hash': '', 'changes': [], 'receipt': None})
                        for state_row in self.db.execute("SELECT event_id FROM states WHERE source=? AND state='UNEXPECTED'", (sid,)).fetchall():
                            if state_row[0] not in unknown:
                                with self.db:
                                    self.observe(sid, state_row[0], 'VERIFIED', '', '', {'message': 'Unexpected entry removed'})
                        source_states.append({**source, 'state': 'ALERT' if any(r['source'] == sid and r['state'] != 'VERIFIED' for r in rows) else 'HEALTHY', 'count': len(current), 'path': str(self.path(sid))})
                    self.flush()
                    history = self.history()
                    previous = '0' * 64
                    for event in reversed(history):
                        if digest(event['payload']) != event['hash'] or event['payload']['previous_observation'] != previous or self.ledger.get(event['key']) != event['hash']:
                            raise RuntimeError('Incident history failed integrity verification')
                        previous = event['hash']
                    status = 'ALERT' if any(s['state'] not in ('HEALTHY','PENDING') for s in source_states) else ('VERIFIED' if rows else 'NO_DATA')
                    self.snapshot = {'status': status, 'checked_at': now(), 'logs': rows, 'sources': source_states, 'history': history, 'network': network, 'error': ''}
                except Exception as exc:
                    self.snapshot = {**self.snapshot, 'status': 'UNAVAILABLE', 'error': str(exc), 'network': {'connected': False, 'mode': self.ledger.mode}, 'history': self.history()}
                return copy.deepcopy(self.snapshot)
        finally:
            self.scan_lock.release()

    def history(self):
        items = []
        for row in self.db.execute('SELECT * FROM observations ORDER BY id DESC'):
            item = dict(row)
            item['payload'] = json.loads(item['payload'])
            item['receipt'] = json.loads(item['receipt']) if item['receipt'] else None
            items.append(item)
        return items

    def row_view(self, row, actual, state, actual_hash, changes, name):
        return {'source': row['source'], 'source_name': name, 'event_id': row['event_id'], 'sequence': row['sequence'], 'state': state,
                'original': json.loads(row['original']), 'current': actual, 'expected_hash': row['hash'], 'actual_hash': actual_hash,
                'changes': changes, 'receipt': json.loads(row['receipt']) if row['receipt'] else None}

    def get_snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.snapshot)
            # Include newly registered sources before their first worker scan.
            if not result['sources']:
                result['sources'] = [{**s, 'state': 'PENDING', 'count': 0, 'path': str(self.path(s['id']))} for s in self.sources()]
            result['pending'] = self.db.execute('SELECT count(*) FROM logs WHERE receipt IS NULL').fetchone()[0] + self.db.execute('SELECT count(*) FROM observations WHERE receipt IS NULL').fetchone()[0]
            return result
