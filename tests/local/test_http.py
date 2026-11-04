"""Exercise actual request handlers over in-memory streams; no sockets required."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from localchain.core import Engine, now
from localchain.ledger import SimulationLedger
from localchain.server import make_server


class FakeServer:
    def __init__(self, address, handler):
        self.handler = handler
        self.server_port = address[1]


class Connection:
    def __init__(self, raw):
        self.input = io.BytesIO(raw)
        self.output = io.BytesIO()
    def makefile(self, *args):
        return self.input
    def sendall(self, data):
        self.output.write(data)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.engine = Engine(root, SimulationLedger(root/'chain.sqlite3'))
        self.server = make_server(self.engine,'admin-test-token',server_class=FakeServer)

    def tearDown(self):
        self.engine.db.close()
        self.temp.cleanup()

    def request(self, path, body=None, token=None, headers=None):
        content = json.dumps(body).encode() if body is not None else b''
        head = {'Host':'127.0.0.1:8080', 'Content-Type':'application/json', 'Content-Length':str(len(content)), 'Connection':'close'}
        if token:
            head['Authorization'] = 'Bearer ' + token
        head.update(headers or {})
        method = 'POST' if body is not None else 'GET'
        raw = f'{method} {path} HTTP/1.1\r\n'.encode()+''.join(f'{k}: {v}\r\n' for k,v in head.items()).encode()+b'\r\n'+content
        conn = Connection(raw)
        self.server.handler(conn,('127.0.0.1',1234),self.server)
        response = conn.output.getvalue()
        header, payload = response.split(b'\r\n\r\n',1)
        status = int(header.split(b' ')[1])
        return status,header.decode(),payload

    def test_auth_required_and_login_session(self):
        self.assertEqual(self.request('/api/snapshot')[0],401)
        self.assertEqual(self.request('/api/login',{'token':'bad'})[0],401)
        status,headers,body = self.request('/api/login',{'token':'admin-test-token'})
        self.assertEqual(status,200)
        self.assertIn('HttpOnly; SameSite=Strict', headers)
        cookie=next(line.split(': ',1)[1].split(';')[0] for line in headers.splitlines() if line.startswith('Set-Cookie:'))
        self.assertEqual(self.request('/api/snapshot',headers={'Cookie':cookie})[0],200)
        self.request('/api/logout',{},headers={'Cookie':cookie})
        self.assertEqual(self.request('/api/snapshot',headers={'Cookie':cookie})[0],401)

    def test_source_ingestion_and_export(self):
        status,_,body=self.request('/api/sources',{'name':'Test app'},token='admin-test-token')
        self.assertEqual(status,201)
        source=json.loads(body)
        path='/api/sources/'+source['id']+'/events'
        event={'event_id':'a','sequence':1,'timestamp':now(),'actor':'vijay','action':'login','message':'signed in'}
        self.assertEqual(self.request(path,{'events':[event]},token='wrong')[0],401)
        self.assertEqual(self.request(path,{'events':[event]},token=source['token'])[0],202)
        self.assertEqual(self.request('/api/export',token=source['token'])[0],401)
        self.engine.verify()
        status,_,body=self.request('/api/export',token='admin-test-token')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['status'],'VERIFIED')

    def test_csrf_and_dns_rebinding_rejected(self):
        self.assertEqual(self.request('/api/sources',{'name':'a'},token='admin-test-token',headers={'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.request('/',headers={'Host':'evil.example:8080'})[0],403)

    def test_malformed_payload_and_content_type(self):
        self.assertEqual(self.request('/api/sources',[],token='admin-test-token')[0],400)
        self.assertEqual(self.request('/api/sources',{'name':'a'},token='admin-test-token',headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/api/sources',{'name':'a'},token='admin-test-token',headers={'Content-Length':'1048577'})[0],413)

    def test_static_csp_and_no_arbitrary_file_access(self):
        status,headers,body=self.request('/')
        self.assertEqual(status,200)
        self.assertIn('Content-Security-Policy',headers)
        self.assertIn(b'LogChain',body)
        self.assertEqual(self.request('/../../etc/passwd',token='admin-test-token')[0],404)


if __name__ == '__main__':
    unittest.main()
