"""Ethereum commitments, plus an explicitly opt-in simulator for offline UI tests."""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class SimulationLedger:
    mode = 'SIMULATION — not a blockchain'

    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS commitments (key TEXT PRIMARY KEY, hash TEXT NOT NULL)')

    def get(self, key):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT hash FROM commitments WHERE key=?', (key,)).fetchone()
            return row[0] if row else None

    def keys(self):
        with sqlite3.connect(self.path) as db:
            return [r[0] for r in db.execute('SELECT key FROM commitments')]

    def put(self, key, value):
        previous = self.get(key)
        if previous and previous != value:
            raise ValueError('Commitment conflict')
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR IGNORE INTO commitments VALUES (?, ?)', (key, value))
        return {'transaction': 'simulation', 'block': None}

    def status(self):
        with sqlite3.connect(self.path) as db:
            count = db.execute('SELECT count(*) FROM commitments').fetchone()[0]
        return {'connected': True, 'mode': self.mode, 'block': None, 'peers': 0, 'commitments': count, 'nodes': []}


class EthereumLedger:
    mode = 'Private Ethereum · Clique PoA'

    def __init__(self, config):
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        self.write_lock = threading.Lock()
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config['rpc'], request_kwargs={'timeout': 5}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        abi = json.loads((Path(__file__).resolve().parents[1] / 'backend/LogIntegrityV3_abi.json').read_text())
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(config['contract']), abi=abi)
        self.account = self.w3.eth.account.from_key(config['writer_key'])

    def check(self):
        if self.w3.eth.chain_id != self.config['chain_id']:
            raise RuntimeError('Wrong chain ID: verification blocked')
        if not self.w3.eth.get_code(self.contract.address):
            raise RuntimeError('Contract missing: verification blocked')
        expected = self.config.get('genesis_hash')
        if expected and self.w3.eth.get_block(0)['hash'].hex() != expected:
            raise RuntimeError('Wrong genesis: verification blocked')

    def get(self, key):
        self.check()
        result = self.contract.functions.getBatch('LOCALCHAIN-V1', key).call()
        if not result[3]:
            return None
        if result[1] != 1 or list(result[4]) != [key] or list(result[6]) != [result[0]]:
            raise RuntimeError('Invalid commitment structure')
        return result[0]

    def keys(self):
        self.check()
        return list(self.contract.functions.getCaseBatches('LOCALCHAIN-V1').call())

    def put(self, key, value):
        with self.write_lock:
            return self._put(key, value)

    def _put(self, key, value):
        existing = self.get(key)
        if existing:
            if existing != value:
                raise RuntimeError('Immutable commitment conflict')
            return {'transaction': 'recovered-on-chain', 'block': None}
        fn = self.contract.functions.anchorBatch('LOCALCHAIN-V1', key, value, 1, [key], [1], [value])
        tx = fn.build_transaction({'from': self.account.address, 'nonce': self.w3.eth.get_transaction_count(self.account.address, 'pending'),
                                  'chainId': self.config['chain_id'], 'gasPrice': self.w3.to_wei(1, 'gwei'),
                                  'gas': int(fn.estimate_gas({'from': self.account.address}) * 1.2)})
        signed = self.account.sign_transaction(tx)
        txid = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(txid, timeout=25, poll_latency=1)
        if receipt['status'] != 1:
            raise RuntimeError('Anchor transaction reverted')
        return {'transaction': txid.hex(), 'block': receipt['blockNumber']}

    def status(self):
        self.check()
        nodes = []
        from web3 import Web3
        for url in self.config.get('peer_rpcs', []):
            try:
                peer = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 2}))
                from web3.middleware import ExtraDataToPOAMiddleware
                peer.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                same = peer.eth.chain_id == self.config['chain_id'] and peer.eth.get_block(0)['hash'] == self.w3.eth.get_block(0)['hash']
                nodes.append({'url': url, 'connected': same, 'block': peer.eth.block_number})
            except Exception:
                nodes.append({'url': url, 'connected': False})
        return {'connected': True, 'mode': self.mode, 'block': self.w3.eth.block_number, 'peers': self.w3.net.peer_count,
                'chain_id': self.config['chain_id'], 'contract': self.contract.address, 'nodes': nodes}
