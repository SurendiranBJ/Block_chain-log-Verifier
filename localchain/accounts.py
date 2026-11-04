"""Local accounts with isolated evidence stores and password authentication."""
import hashlib
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from localchain.core import Engine, now


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class Accounts:
    def __init__(self, root, ledger, legacy):
        self.root = Path(root)
        self.ledger = ledger
        self.legacy = legacy
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/'accounts.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL,created TEXT NOT NULL)')
        self.db.commit()
        self.engines = {r['id']: Engine(self.root/'accounts'/r['id'], ledger) for r in self.db.execute('SELECT id FROM accounts')}
        self.failures = {}

    def create(self, name, email, password, source_name, source_mode):
        if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Enter your name (1–80 characters)')
        if not isinstance(email,str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            raise ValueError('Enter a valid email address')
        if not isinstance(password,str) or not 12 <= len(password) <= 256:
            raise ValueError('Use a password of 12–256 characters')
        if not isinstance(source_name,str) or not 1<=len(source_name.strip())<=80 or source_mode not in ('api','file'):
            raise ValueError('Choose a source name and connection method')
        email=email.strip().lower()
        salt=secrets.token_hex(16)
        hashed=password_hash(password,salt)
        with self.lock:
            if self.db.execute('SELECT 1 FROM accounts WHERE email=?',(email,)).fetchone():
                raise ValueError('An account already exists for that email; sign in instead')
            aid=secrets.token_hex(16)
            engine=Engine(self.root/'accounts'/aid,self.ledger)
            source=engine.add_source(source_name,source_mode)
            with self.db:
                self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?)',(aid,email,name.strip(),salt,hashed,now()))
            self.engines[aid]=engine
            return {'id':aid,'name':name.strip(),'email':email},source

    def authenticate(self, email, password):
        if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or len(password)>256:
            return None
        email=email.strip().lower()
        with self.lock:
            failures,blocked_until=self.failures.get(email,(0,0))
            if time.monotonic()<blocked_until:
                raise ValueError('Too many attempts. Wait one minute before trying again.')
            row=self.db.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
        expected=row['password'] if row else '0'*128
        actual=password_hash(password,row['salt'] if row else '0'*32)
        if not row or not secrets.compare_digest(actual,expected):
            with self.lock:
                failures+=1
                self.failures[email]=(failures,time.monotonic()+60 if failures>=5 else 0)
            return None
        with self.lock:
            self.failures.pop(email,None)
        return {k:row[k] for k in ('id','name','email')}

    def all_engines(self):
        with self.lock:
            return [self.legacy,*self.engines.values()]

    def source_engine(self, sid, token):
        return next((engine for engine in self.all_engines() if engine.authorize_source(sid,token)),None)

    def verify(self):
        for engine in self.all_engines():
            try:
                engine.verify()
            except Exception:
                import logging
                logging.exception('Account scan failed; other accounts continue monitoring')

    def close(self):
        for engine in self.engines.values():
            engine.db.close()
        self.db.close()
