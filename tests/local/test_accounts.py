import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from localchain.accounts import Accounts
from localchain.agent import read_events
from localchain.core import Engine, now
from localchain.ledger import SimulationLedger
from localchain.server import make_server, BackgroundMonitor
from test_http import FakeServer, Connection


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.ledger=SimulationLedger(self.root/'ledger.sqlite3')
        self.legacy=Engine(self.root,self.ledger)
        self.accounts=Accounts(self.root,self.ledger,self.legacy)
        self.server=make_server(self.legacy,'legacy-token',server_class=FakeServer,accounts=self.accounts)

    def tearDown(self):
        self.accounts.close();self.legacy.db.close();self.temp.cleanup()

    def request(self,path,body=None,cookie=None,token=None):
        payload=json.dumps(body).encode() if body is not None else b''
        headers={'Host':'127.0.0.1:8080','Content-Type':'application/json','Content-Length':str(len(payload)),'Connection':'close'}
        if cookie:headers['Cookie']=cookie
        if token:headers['Authorization']='Bearer '+token
        raw=f"{'POST' if body is not None else 'GET'} {path} HTTP/1.1\r\n".encode()+''.join(f'{k}: {v}\r\n' for k,v in headers.items()).encode()+b'\r\n'+payload
        conn=Connection(raw);self.server.handler(conn,('127.0.0.1',1),self.server)
        head,body=conn.output.getvalue().split(b'\r\n\r\n',1)
        return int(head.split()[1]),head.decode(),json.loads(body) if body else None

    def signup(self,email='vijay@example.test',mode='file'):
        status,headers,body=self.request('/api/signup',{'name':'Vijay','email':email,'password':'correct horse battery','source_name':'My existing project','source_mode':mode})
        self.assertEqual(status,201)
        cookie=next(line.split(': ',1)[1].split(';')[0] for line in headers.splitlines() if line.startswith('Set-Cookie:'))
        return body,cookie

    def event(self):
        return {'event_id':'evt-1','sequence':1,'timestamp':now(),'actor':'user','action':'login','message':'Original'}

    def test_signup_requires_source_and_password_and_never_stores_plaintext(self):
        self.assertEqual(self.request('/api/signup',{'name':'a','email':'a@b.test','password':'short','source_name':'App','source_mode':'file'})[0],400)
        result,cookie=self.signup()
        self.assertEqual(result['source']['mode'],'file')
        self.assertTrue(result['source']['token'])
        self.assertNotIn('password',result['user'])
        raw=(self.root/'accounts.sqlite3').read_bytes()
        self.assertNotIn(b'correct horse battery',raw)
        self.assertEqual(self.request('/api/signup',{'name':'a','email':'VIJAY@example.test','password':'a sufficiently long password','source_name':'app','source_mode':'api'})[0],400)

    def test_account_and_source_tokens_cannot_cross_workspaces(self):
        alice,ac=self.signup('alice@example.test');bob,bc=self.signup('bob@example.test')
        source=alice['source'];event=self.event()
        route='/api/sources/'+source['id']+'/sync'
        self.assertEqual(self.request(route,{'events':[event]},token=bob['source']['token'])[0],401)
        self.assertEqual(self.request(route,{'events':[event]},token=source['token'])[0],202)
        self.accounts.verify()
        self.assertEqual(len(self.request('/api/snapshot',cookie=ac)[2]['logs']),1)
        self.assertEqual(self.request('/api/snapshot',cookie=bc)[2]['logs'],[])
        self.assertEqual(self.request('/api/export',cookie=bc)[2]['history'],[])
        self.assertEqual(self.request('/api/snapshot',token=source['token'])[0],401)
        self.assertEqual(self.request('/api/sources/'+source['id']+'/rotate-token',{},cookie=bc)[0],400)
        self.assertEqual(self.legacy.get_snapshot()['logs'],[])

    def test_login_logout_and_persisted_identity(self):
        result,cookie=self.signup()
        self.assertEqual(self.request('/api/login',{'email':'vijay@example.test','password':'wrong password'})[0],401)
        status,headers,body=self.request('/api/login',{'email':'VIJAY@example.test','password':'correct horse battery'})
        self.assertEqual(status,200);self.assertEqual(body['user']['id'],result['user']['id'])
        self.request('/api/logout',{},cookie=cookie)
        self.assertEqual(self.request('/api/snapshot',cookie=cookie)[0],401)
        self.accounts.close();self.accounts=Accounts(self.root,self.ledger,self.legacy)
        self.assertEqual(self.accounts.authenticate('vijay@example.test','correct horse battery')['id'],result['user']['id'])
        self.assertEqual(len(self.accounts.engines[result['user']['id']].sources()),1)

    def test_external_snapshot_preserves_modification_deletion_restoration(self):
        result,cookie=self.signup();source=result['source'];route='/api/sources/'+source['id']+'/sync';event=self.event()
        self.request(route,{'events':[event]},token=source['token']);self.accounts.verify()
        original=self.request('/api/snapshot',cookie=cookie)[2]['logs'][0]['expected_hash']
        expected=[]
        for values,kind in [([{**event,'message':'Altered'}],'MODIFIED'),([event],'RESTORED'),([],'DELETED'),([event],'RESTORED')]:
            self.assertEqual(self.request(route,{'events':values},token=source['token'])[0],202)
            self.accounts.verify();snapshot=self.request('/api/snapshot',cookie=cookie)[2]
            self.assertEqual(snapshot['logs'][0]['expected_hash'],original)
            expected.append(kind)
            self.assertEqual([h['kind'] for h in reversed(snapshot['history'])],expected)

    def test_snapshot_cannot_be_used_on_api_source_and_token_rotation_revokes(self):
        result,cookie=self.signup(mode='api');source=result['source'];route='/api/sources/'+source['id']
        self.assertEqual(self.request(route+'/sync',{'events':[]},token=source['token'])[0],400)
        status,_,new=self.request(route+'/rotate-token',{},cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual(self.request(route+'/events',{'events':[self.event()]},token=source['token'])[0],401)
        self.assertEqual(self.request(route+'/events',{'events':[self.event()]},token=new['token'])[0],202)

    def test_offline_file_is_unavailable_and_reconnect_restores(self):
        result,_=self.signup();sid=result['source']['id'];engine=self.accounts.engines[result['user']['id']];event=self.event()
        engine.sync(sid,[event]);self.assertEqual(engine.verify()['status'],'VERIFIED')
        with engine.lock,engine.db:
            engine.db.execute("UPDATE sources SET last_seen='2000-01-01T00:00:00+00:00' WHERE id=?",(sid,))
        snapshot=engine.verify();self.assertEqual(snapshot['logs'][0]['state'],'UNAVAILABLE')
        self.assertEqual(snapshot['sources'][0]['state'],'SOURCE_UNREADABLE')
        engine.source_unavailable(sid,'File cannot be read');self.assertEqual(engine.verify()['logs'][0]['state'],'UNAVAILABLE')
        engine.sync(sid,[event]);self.assertEqual(engine.verify()['status'],'VERIFIED')
        self.assertIn('RESTORED',[h['kind'] for h in engine.history()])

    def test_background_detects_external_changes_without_verify_endpoint(self):
        result,cookie=self.signup();source=result['source'];route='/api/sources/'+source['id']+'/sync';event=self.event()
        monitor=BackgroundMonitor(self.accounts,interval=.03);monitor.start()
        def wait_for(predicate):
            until=time.monotonic()+3
            while time.monotonic()<until:
                snapshot=self.request('/api/snapshot',cookie=cookie)[2]
                if predicate(snapshot):return snapshot
                time.sleep(.01)
            self.fail('Automatic monitor did not update')
        try:
            self.request(route,{'events':[event]},token=source['token'])
            wait_for(lambda s:s['status']=='VERIFIED')
            self.request(route,{'events':[{**event,'message':'Tampered'}]},token=source['token'])
            wait_for(lambda s:s['status']=='ALERT')
            self.request(route,{'events':[event]},token=source['token'])
            snap=wait_for(lambda s:s['status']=='VERIFIED' and any(h['kind']=='RESTORED' for h in s['history']))
            self.assertIn('MODIFIED',[h['kind'] for h in snap['history']])
        finally:monitor.stop()

    def test_standalone_agent_delivers_edit_and_restoration_to_own_account(self):
        from unittest.mock import patch
        from contextlib import redirect_stdout, redirect_stderr
        from localchain.agent import main
        result,cookie=self.signup()
        source=result['source']; log=self.root/'application.log';log.write_text('Original\n')
        config=self.root/'connection.json'
        config.write_text(json.dumps({'source_id':source['id'],'token':source['token'],'mode':'file',
                                      'api_url':'http://127.0.0.1:8080','file_path':str(log),'format':'text'}))
        owner=self.accounts.engines[result['user']['id']]
        class Reply:
            def __init__(self,body):self.body=io.BytesIO(json.dumps(body).encode())
            def __enter__(self):return self.body
            def __exit__(self,*args):pass
        def bridge(request,timeout):
            from urllib.parse import urlsplit
            status,_,body=self.request(urlsplit(request.full_url).path,json.loads(request.data),token=request.get_header('Authorization').removeprefix('Bearer '))
            self.assertEqual(status,202)
            return Reply(body)
        def run_agent(exit_code=0):
            with patch('sys.argv',['agent.py','--config',str(config),'--once']),patch('localchain.agent.urlopen',bridge),patch('localchain.agent.signal.signal'),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(main(),exit_code)
            self.accounts.verify()
        run_agent();self.assertEqual(owner.get_snapshot()['status'],'VERIFIED')
        log.write_text('Changed\n');run_agent();self.assertEqual(owner.get_snapshot()['logs'][0]['state'],'MODIFIED')
        log.write_text('Original\n');run_agent();self.assertEqual(owner.get_snapshot()['logs'][0]['state'],'VERIFIED')
        self.assertEqual([h['kind'] for h in reversed(owner.history())],['MODIFIED','RESTORED'])
        log.unlink();run_agent(1);self.assertEqual(owner.get_snapshot()['logs'][0]['state'],'UNAVAILABLE')


class AgentTests(unittest.TestCase):
    def test_text_identity_survives_edit_restore_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'app.log';path.write_text('Original\n');state={}
            first=read_events(path,'text',state)
            path.write_text('Altered\n');changed=read_events(path,'text',state)
            self.assertEqual(first[0]['event_id'],changed[0]['event_id'])
            self.assertEqual(first[0]['timestamp'],changed[0]['timestamp'])
            path.write_text('Original\n');self.assertEqual(first,read_events(path,'text',json.loads(json.dumps(state))))
            path.write_text('Original\nunfinished');self.assertEqual(len(read_events(path,'text',state)),1)

    def test_structured_jsonl_and_generic_jsonl_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'app.log';event={'event_id':'a','sequence':1,'timestamp':now(),'actor':'u','action':'login','message':'ok'}
            path.write_text(json.dumps(event)+'\n');self.assertEqual(read_events(path,'jsonl',{}),[event])
            path.write_text('{"level":"info","msg":"ok"}\n');self.assertEqual(read_events(path,'jsonl',{})[0]['data']['level'],'info')
            path.write_text('[malformed')
            with self.assertRaises(ValueError):read_events(path,'json',{})
