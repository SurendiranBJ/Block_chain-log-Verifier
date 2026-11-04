import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from localchain.core import Engine, atomic_json, now
from localchain.ledger import SimulationLedger
from localchain.server import BackgroundMonitor

class MonitorTests(unittest.TestCase):
    def until(self, predicate):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.01)
        self.fail('Automatic monitor did not update without a manual scan')

    def test_unhandled_failure_retries(self):
        class Unstable:
            count=0
            def verify(self):
                self.count+=1
                if self.count==1: raise RuntimeError('injected scan failure')
        engine=Unstable(); monitor=BackgroundMonitor(engine,interval=.02)
        with self.assertLogs(level='ERROR'):
            monitor.start()
            try:
                self.until(lambda: engine.count>=2 and monitor.status()['last_completed'] is not None)
                self.assertTrue(monitor.status()['alive'])
                self.assertEqual(monitor.status()['error'],'')
            finally: monitor.stop()
        self.assertFalse(monitor.status()['alive'])

    def test_automatic_tamper_restore_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); engine=Engine(root,SimulationLedger(root/'ledger.sqlite3'))
            source=engine.add_source('Live source')
            original={'event_id':'live-1','sequence':1,'timestamp':now(),'actor':'test','action':'login','message':'Original'}
            engine.ingest(source['id'],[original])
            monitor=BackgroundMonitor(engine,interval=.02); monitor.start()
            try:
                self.until(lambda: engine.get_snapshot()['status']=='VERIFIED')
                for value,kind in [('Changed','MODIFIED'),('Original','RESTORED'),('Changed again','MODIFIED')]:
                    record={**original,'message':value}
                    previous=len(engine.get_snapshot()['history'])
                    atomic_json(engine.path(source['id']),[record])
                    self.until(lambda: len(engine.get_snapshot()['history'])>previous)
                    self.assertEqual(engine.get_snapshot()['history'][0]['kind'],kind)
                self.assertEqual(len(engine.get_snapshot()['history']),3)
            finally:
                monitor.stop(); engine.db.close()
