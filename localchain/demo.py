"""Separate local web app. Emits real logs through the authenticated ingestion API."""
import argparse
import json
import os
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from localchain.core import atomic_json, now
from localchain.ledger import canonical

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Northstar · Connected audit source</title><style>
body{font:16px system-ui;background:#f3f6f9;color:#182b3e;margin:0}main{max-width:820px;margin:7vh auto;padding:32px}small{color:#167563;letter-spacing:2px}h1{font-size:42px;margin:14px 0}p{color:#607180;line-height:1.7}section{background:white;padding:26px;border-radius:18px;border:1px solid #dce5eb;margin:24px 0}button,select{padding:13px 18px;border-radius:8px;border:1px solid #cad7df;background:white;font:inherit;margin:5px;cursor:pointer}button:first-of-type{background:#136e5a;color:white;border:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}a{color:#147864}#message{min-height:24px}label{display:block}</style><main><small>CONNECTED APPLICATION / LOCAL DEMO</small><h1>Northstar workspace</h1><p>A sample business application connected to LogChain. Every action generates a real audit record. Use the isolated test controls to see how tampering and restoration appear in the monitor.</p><section><h2>Workspace actions</h2><button data-action="login">Sign in as Vijay</button><button data-action="export">Export customer report</button><button data-action="permission">Update member access</button></section><section><h2>Integrity test lab</h2><p>These controls change only this demo application's source file. The original blockchain commitment stays unchanged.</p><label for="event">Choose a log</label><select id="event"></select><div><button data-action="modify">Alter message</button><button data-action="restore">Restore original</button><button data-action="delete">Delete log</button><button data-action="reorder">Swap last two</button></div><p id="message" role="status"></p><pre id="logs"></pre></section><a href="http://127.0.0.1:8080" target="_blank" rel="noopener">Open integrity dashboard ↗</a></main><script>
const csrf='__CSRF__'; async function refresh(){let r=await fetch('/logs');let d=await r.json();let s=document.querySelector('#event'),old=s.value;s.replaceChildren();for(let e of d.originals){let o=document.createElement('option');o.value=e.event_id;o.textContent=e.sequence+' · '+e.action;s.append(o)}s.value=old||s.options[0]?.value||'';document.querySelector('#logs').textContent=JSON.stringify(d.current,null,2)}
document.querySelectorAll('button').forEach(b=>b.onclick=async()=>{b.disabled=true;try{let r=await fetch('/action',{method:'POST',headers:{'Content-Type':'application/json','X-Demo-CSRF':csrf},body:JSON.stringify({action:b.dataset.action,event_id:document.querySelector('#event').value})});let d=await r.json();document.querySelector('#message').textContent=d.message||d.error;await refresh()}catch(e){document.querySelector('#message').textContent=e.message}finally{b.disabled=false}});refresh();</script></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='runtime')
    parser.add_argument('--api', default='http://127.0.0.1:8080')
    parser.add_argument('--port', type=int, default=8081)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(args.data).resolve()
    lock = threading.Lock()
    config_file = root / 'demo-source.json'
    csrf = secrets.token_urlsafe(24)

    def post(path, data, token):
        request = Request(args.api + path, data=canonical(data).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        with urlopen(request, timeout=60) as response:
            return json.load(response)

    if config_file.exists():
        config = json.loads(config_file.read_text())
    else:
        config = post('/api/sources', {'name': 'Northstar · Demo web app'}, (root / 'admin.token').read_text().strip())
        atomic_json(config_file, config)
    original_file = root / 'demo-originals.json'
    if not original_file.exists():
        atomic_json(original_file, [])
    source_path = Path(config['path'])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, mime='application/json'):
            content = data.encode() if isinstance(data, str) else canonical(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def valid_host(self):
            return self.headers.get('Host') in (f'localhost:{args.port}', f'127.0.0.1:{args.port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Invalid host'})
            if self.path == '/':
                return self.send(200, PAGE.replace('__CSRF__', csrf), 'text/html')
            if self.path == '/logs':
                return self.send(200, {'originals': json.loads(original_file.read_text()), 'current': json.loads(source_path.read_text())})
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('X-Demo-CSRF') != csrf:
                return self.send(403, {'error': 'Forbidden'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size < 10000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                with lock:
                    originals = json.loads(original_file.read_text())
                    current = json.loads(source_path.read_text())
                    action = body['action']
                    if action in ('login', 'export', 'permission'):
                        event = {'event_id': uuid.uuid4().hex, 'sequence': max([e['sequence'] for e in originals], default=0) + 1,
                                 'timestamp': now(), 'actor': 'vijay@northstar.local', 'action': action,
                                 'message': {'login': 'User signed in successfully', 'export': 'Customer report exported', 'permission': 'Member access changed to viewer'}[action], 'ip': '127.0.0.1'}
                        post('/api/sources/' + config['id'] + '/events', {'events': [event]}, config['token'])
                        atomic_json(original_file, originals + [event])
                    elif action == 'reorder':
                        if len(current) < 2:
                            raise ValueError('Generate at least two logs first')
                        current[-1], current[-2] = current[-2], current[-1]
                        atomic_json(source_path, current)
                    else:
                        original = next((e for e in originals if e['event_id'] == body.get('event_id')), None)
                        if original is None:
                            raise ValueError('Choose a log first')
                        if action == 'restore':
                            current = [e for e in current if e.get('event_id') != original['event_id']] + [original]
                            current.sort(key=lambda e: e['sequence'])
                        elif action == 'delete':
                            current = [e for e in current if e.get('event_id') != original['event_id']]
                        elif action == 'modify':
                            found = next((e for e in current if e.get('event_id') == original['event_id']), None)
                            if found is None:
                                raise ValueError('Restore the deleted log before modifying it')
                            found['message'] = 'Altered audit message · ' + now()
                        else:
                            raise ValueError('Unknown action')
                        atomic_json(source_path, current)
                self.send(200, {'message': 'Action saved. Allow the monitor to complete a scan before restoring.'})
            except Exception as exc:
                self.send(400, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Demo web app: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
