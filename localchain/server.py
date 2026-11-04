"""Loopback-only HTTP service with authenticated UI/API and background verification."""
import argparse
import json
import logging
import mimetypes
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from localchain.accounts import Accounts
from localchain.core import Engine, atomic_json
from localchain.ledger import EthereumLedger, SimulationLedger, canonical

STATIC = Path(__file__).parent / 'static'


class BackgroundMonitor:
    """Run independent scans; one unexpected failure must not end monitoring."""
    def __init__(self, engine, interval=1):
        self.engine = engine
        self.interval = interval
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.last_started = None
        self.last_completed = None
        self.error = ''
        self.thread = threading.Thread(target=self.run, name='integrity-monitor', daemon=True)

    def start(self):
        self.thread.start()

    def status(self):
        with self.state_lock:
            return {'alive': self.thread.is_alive(), 'interval_seconds': self.interval,
                    'last_started': self.last_started, 'last_completed': self.last_completed,
                    'error': self.error}

    def run(self):
        while not self.stop_event.is_set():
            started = time.monotonic()
            with self.state_lock:
                self.last_started = time.time()
            try:
                self.engine.verify()
            except Exception:
                logging.exception('Automatic integrity scan failed; retrying')
                with self.state_lock:
                    self.error = 'Automatic scan failed; retrying. Inspect the server terminal.'
            else:
                with self.state_lock:
                    self.last_completed = time.time()
                    self.error = ''
            self.stop_event.wait(max(0.05, self.interval - (time.monotonic() - started)))

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)


def make_server(engine, token, port=8080, server_class=ThreadingHTTPServer, monitor=None, accounts=None):
    sessions = {}
    session_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Never log tokens or raw audit payloads.

        def send(self, status, data, mime='application/json', cookie=None):
            body = data if isinstance(data, bytes) else canonical(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(body)

        def identity(self):
            bearer = self.headers.get('Authorization', '').removeprefix('Bearer ')
            if secrets.compare_digest(bearer, token):
                return {'id':'legacy','name':'Existing local workspace','email':''}
            try:
                cookies = SimpleCookie(self.headers.get('Cookie', ''))
                session = cookies['session'].value if 'session' in cookies else ''
                with session_lock:
                    entry = sessions.get(session)
                    if entry and time.time() - entry['created'] < 12 * 3600:
                        return entry['user']
                    sessions.pop(session, None)
            except Exception:
                pass
            return None

        def admin(self):
            return self.identity() is not None

        def workspace(self):
            user = self.identity()
            if not user:
                return None
            return engine if user['id']=='legacy' else accounts.engines[user['id']]

        def signed_in(self, user, extra=None, status=200):
            session = secrets.token_urlsafe(32)
            with session_lock:
                sessions[session] = {'user':user,'created':time.time()}
            return self.send(status, {'ok':True,'user':user,**(extra or {})},
                             cookie=f'session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')

        def safe_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.safe_host():
                return self.send(403, {'error': 'Invalid host'})
            path = urlsplit(self.path).path
            if path == '/agent.py':
                return self.send(200, (Path(__file__).parent/'agent.py').read_bytes(), 'text/x-python; charset=utf-8')
            if path in ('/', '/app.js', '/style.css'):
                name = 'index.html' if path == '/' else path[1:]
                return self.send(200, (STATIC / name).read_bytes(), mimetypes.guess_type(name)[0] + '; charset=utf-8')
            if not self.admin():
                return self.send(401, {'error': 'Sign in to your account'})
            workspace = self.workspace()
            if path == '/api/snapshot':
                snapshot = workspace.get_snapshot()
                snapshot['user'] = self.identity()
                if monitor is not None:
                    snapshot['monitor'] = monitor.status()
                return self.send(200, snapshot)
            if path == '/api/export':
                return self.send(200, {'format': 'logchain-evidence-v1', **workspace.get_snapshot()})
            return self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.safe_host():
                return self.send(403, {'error': 'Invalid host'})
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.send(403, {'error': 'Cross-origin request rejected'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 1024 * 1024:
                    return self.send(413, {'error': 'Request must be 1 byte–1 MiB'})
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.send(415, {'error': 'Use application/json'})
                body = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON numbers are not allowed')))
                if not isinstance(body, dict):
                    raise ValueError('Expected JSON object')
                path = urlsplit(self.path).path
                if path == '/api/signup':
                    if accounts is None:
                        return self.send(404, {'error':'Account creation is unavailable'})
                    user, source = accounts.create(body.get('name'),body.get('email'),body.get('password'),
                                                   body.get('source_name'),body.get('source_mode'))
                    return self.signed_in(user, {'source':source}, status=201)
                if path == '/api/login':
                    if 'token' in body:
                        if not isinstance(body['token'],str) or not secrets.compare_digest(body['token'],token):
                            return self.send(401, {'error':'Incorrect administrator token'})
                        return self.signed_in({'id':'legacy','name':'Existing local workspace','email':''})
                    user = accounts.authenticate(body.get('email'),body.get('password')) if accounts else None
                    if not user:
                        return self.send(401, {'error':'Incorrect email or password'})
                    return self.signed_in(user)
                parts = path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','sources'] and parts[3] in ('events','sync','unavailable'):
                    sid = parts[2]
                    bearer = self.headers.get('Authorization','').removeprefix('Bearer ')
                    target = accounts.source_engine(sid,bearer) if accounts else (engine if engine.authorize_source(sid,bearer) else None)
                    if target is None:
                        return self.send(401, {'error':'Invalid source token'})
                    if parts[3]=='events':
                        result = target.ingest(sid,body.get('events'))
                    elif parts[3]=='sync':
                        result = target.sync(sid,body.get('events'))
                    else:
                        result = target.source_unavailable(sid,body.get('error'))
                    return self.send(202,result)
                if not self.admin():
                    return self.send(401, {'error': 'Sign in required'})
                workspace = self.workspace()
                if path == '/api/logout':
                    cookies = SimpleCookie(self.headers.get('Cookie', ''))
                    if 'session' in cookies:
                        with session_lock:
                            sessions.pop(cookies['session'].value,None)
                    return self.send(200, {'ok': True}, cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if path == '/api/sources':
                    return self.send(201, workspace.add_source(body.get('name'),body.get('mode','api')))
                if len(parts)==4 and parts[:2]==['api','sources'] and parts[3]=='rotate-token':
                    return self.send(200,workspace.rotate_source_token(parts[2]))
                if path == '/api/verify':
                    threading.Thread(target=workspace.verify, daemon=True).start()
                    return self.send(202, {'message': 'Verification started'})
                return self.send(404, {'error': 'Not found'})
            except (ValueError, TypeError, KeyError, OSError) as exc:
                return self.send(400, {'error': str(exc)})
            except Exception:
                logging.exception('Request failed')
                return self.send(500, {'error': 'Internal failure; inspect service logs'})

    return server_class(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='LogChain local integrity monitor')
    parser.add_argument('--data', default='runtime')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--simulate', action='store_true', help='Explicit offline simulator, NOT blockchain verification')
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(args.data).resolve()
    root.mkdir(parents=True, exist_ok=True)
    mode_file = root / 'mode.txt'
    mode = 'simulation' if args.simulate else 'ethereum'
    if mode_file.exists() and mode_file.read_text() != mode:
        parser.error('Use a different --data directory when switching between simulator and Ethereum')
    mode_file.write_text(mode)
    token_file = root / 'admin.token'
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32))
    token_file.chmod(0o600)
    if args.simulate:
        ledger = SimulationLedger(root / 'simulation.sqlite3')
    else:
        config_path = root / 'chain.json'
        if not config_path.exists():
            parser.error('Run python -m localchain.setup init, start the node, then run python -m localchain.setup deploy')
        config = json.loads(config_path.read_text())
        if not config.get('contract'):
            parser.error('Deploy the contract first: python -m localchain.setup deploy')
        ledger = EthereumLedger(config)
    engine = Engine(root, ledger)
    accounts = Accounts(root, ledger, engine)
    monitor = BackgroundMonitor(accounts)
    server = make_server(engine, token_file.read_text().strip(), args.port, monitor=monitor, accounts=accounts)
    monitor.start()
    print(f'LogChain: http://127.0.0.1:{args.port}\nMode: {ledger.mode}\nAdministrator token file: {token_file}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        server.server_close()


if __name__ == '__main__':
    main()
