"""Reproducible one-validator Clique lab; separate observer nodes are optional."""
import argparse
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path
from localchain.core import atomic_json


def geth_binary():
    local = Path('bin/geth').resolve()
    executable = str(local) if local.exists() else shutil.which('geth')
    if not executable:
        raise SystemExit('Install Geth 1.13.15: python scripts/download_geth.py')
    version = subprocess.check_output([executable, 'version'], text=True)
    if 'Version: 1.13.15' not in version:
        raise SystemExit('This legacy Clique lab requires exactly Geth 1.13.15 (newer Geth removed sealing).')
    return executable


def client(config):
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    web3 = Web3(Web3.HTTPProvider(config['rpc'], request_kwargs={'timeout': 5}))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if web3.eth.chain_id != config['chain_id']:
        raise SystemExit('Wrong chain ID')
    return web3


def main():
    parser = argparse.ArgumentParser(description='Manage isolated LogChain Ethereum lab')
    parser.add_argument('command', choices=['init', 'start', 'deploy', 'observer', 'smoke'])
    parser.add_argument('--data', default='runtime')
    parser.add_argument('--enode', help='Approved primary/observer enode URL, reachable on private LAN')
    parser.add_argument('--port', type=int, default=30304, help='Observer P2P port')
    parser.add_argument('--rpc-port', type=int, default=8546, help='Observer RPC (loopback only)')
    parser.add_argument('--observer-name', default='observer1')
    parser.add_argument('--netrestrict', default='127.0.0.0/8', help='Allowed P2P CIDRs; use your actual private LAN CIDR for remote peers')
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(args.data).resolve()
    root.mkdir(parents=True, exist_ok=True)
    config_file = root / 'chain.json'
    if args.command == 'init':
        if config_file.exists() or (root / 'node').exists():
            raise SystemExit('Existing chain detected. Initialization refuses to replace keys or chain data.')
        from eth_account import Account
        validator, writer = Account.create(), Account.create()
        password = secrets.token_urlsafe(32)
        node = root / 'node'
        (node / 'keystore').mkdir(parents=True)
        atomic_json(node / 'keystore/validator.json', Account.encrypt(validator.key, password))
        (root / 'validator.password').write_text(password)
        genesis = {'config': {'chainId': 12345, 'homesteadBlock': 0, 'eip150Block': 0, 'eip155Block': 0, 'eip158Block': 0,
                             'byzantiumBlock': 0, 'constantinopleBlock': 0, 'petersburgBlock': 0, 'istanbulBlock': 0,
                             'berlinBlock': 0, 'clique': {'period': 2, 'epoch': 30000}},
                   'difficulty': '1', 'gasLimit': '12000000',
                   'extraData': '0x' + '00' * 32 + validator.address[2:].lower() + '00' * 65,
                   'alloc': {writer.address[2:]: {'balance': '1000000000000000000000000'}}}
        atomic_json(root / 'genesis.json', genesis)
        atomic_json(config_file, {'rpc': 'http://127.0.0.1:8545', 'chain_id': 12345, 'validator': validator.address,
                                 'writer_key': writer.key.hex(), 'contract': '', 'peer_rpcs': []})
        print('Created one-validator genesis and a separate funded contract writer. Secrets are stored with owner-only permissions.')
        print('Next: python -m localchain.setup start')
        return
    if not config_file.exists() and args.command != 'observer':
        raise SystemExit('Run init first')
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    if args.command in ('start', 'observer'):
        geth = geth_binary()
        if args.command == 'observer':
            if not args.enode or not args.enode.startswith('enode://'):
                raise SystemExit('Pass --enode with an approved peer. Copy only genesis.json to the observer data directory first.')
            if not args.observer_name.replace('-', '').isalnum():
                raise SystemExit('Invalid observer name')
            node = root / args.observer_name
        else:
            node = root / 'node'
        genesis_file = root / 'genesis.json'
        if not genesis_file.exists():
            raise SystemExit('Missing genesis.json')
        if not (node / 'geth/chaindata').exists():
            subprocess.run([geth, '--datadir', str(node), 'init', str(genesis_file)], check=True)
        command = [geth, '--datadir', str(node), '--networkid', '12345', '--syncmode', 'full', '--nodiscover',
                   '--netrestrict', args.netrestrict, '--http', '--http.addr', '127.0.0.1', '--http.vhosts', 'localhost,127.0.0.1',
                   '--http.api', 'eth,net,web3', '--http.port', str(args.rpc_port if args.command == 'observer' else 8545),
                   '--port', str(args.port if args.command == 'observer' else 30303)]
        if args.command == 'start':
            command += ['--mine', '--miner.etherbase', config['validator'], '--unlock', config['validator'],
                        '--password', str(root / 'validator.password'), '--allow-insecure-unlock', '--miner.gasprice', '1000000000']
        else:
            # StaticNodes is persisted so nodiscover still establishes the approved connection.
            toml = root / (args.observer_name + '.toml')
            toml.write_text('[Node.P2P]\nStaticNodes = [' + json.dumps(args.enode) + ']\n')
            command += ['--config', str(toml)]
        print('Starting local Clique lab. RPC is loopback-only; admin/personal are not exposed over HTTP.', flush=True)
        os.execv(geth, command)
    web3 = client(config)
    if args.command == 'deploy':
        if config.get('contract'):
            raise SystemExit('Contract already configured. Refusing to replace the existing integrity ledger.')
        import solcx
        import solcx.install
        solcx.install.BINARY_DOWNLOAD_BASE = 'https://binaries.soliditylang.org/{}-amd64/{}'
        solcx.install_solc('0.8.19')
        source = (Path(__file__).resolve().parents[1] / 'contracts/LogIntegrityV3.sol').read_text()
        compiled = solcx.compile_standard({'language': 'Solidity', 'sources': {'LogIntegrityV3.sol': {'content': source}},
                    'settings': {'optimizer': {'enabled': True, 'runs': 200}, 'viaIR': True, 'evmVersion': 'berlin',
                                 'outputSelection': {'*': {'*': ['abi', 'evm.bytecode.object']}}}}, solc_version='0.8.19')
        artifact = compiled['contracts']['LogIntegrityV3.sol']['LogIntegrityV3']
        account = web3.eth.account.from_key(config['writer_key'])
        contract = web3.eth.contract(abi=artifact['abi'], bytecode=artifact['evm']['bytecode']['object'])
        tx = contract.constructor().build_transaction({'from': account.address, 'chainId': config['chain_id'],
                'nonce': web3.eth.get_transaction_count(account.address, 'pending'), 'gas': 5000000, 'gasPrice': web3.to_wei(1, 'gwei')})
        signed = account.sign_transaction(tx)
        receipt = web3.eth.wait_for_transaction_receipt(web3.eth.send_raw_transaction(signed.raw_transaction), timeout=120)
        if receipt['status'] != 1:
            raise SystemExit('Deployment reverted')
        config['contract'] = receipt['contractAddress']
        config['genesis_hash'] = web3.eth.get_block(0)['hash'].hex()
        atomic_json(config_file, config)
        atomic_json(root / 'deployment.json', {'contract': config['contract'], 'chain_id': config['chain_id'], 'block': receipt['blockNumber'], 'tx': receipt['transactionHash'].hex()})
        print('Contract deployed:', config['contract'])
        print('Start the monitor: python -m localchain.server')
    elif args.command == 'smoke':
        import tempfile
        import uuid
        from localchain.ledger import EthereumLedger
        from localchain.core import Engine, now
        # Real RPC lifecycle test; temporary app state, append-only test commitments remain on-chain.
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, EthereumLedger(config))
            sid = engine.add_source('RPC smoke test')['id']
            event = {'event_id': uuid.uuid4().hex, 'sequence': 1, 'timestamp': now(), 'actor': 'smoke', 'action': 'test', 'message': 'original'}
            engine.ingest(sid, [event])
            result = engine.verify()
            if result['status'] != 'VERIFIED':
                raise SystemExit('Initial verification failed: ' + result['error'])
            altered = {**event, 'message': 'altered'}
            atomic_json(engine.path(sid), [altered])
            assert engine.verify()['status'] == 'ALERT'
            atomic_json(engine.path(sid), [event])
            result = engine.verify()
            assert result['status'] == 'VERIFIED', result['error']
            assert [h['kind'] for h in result['history']] == ['RESTORED', 'MODIFIED']
            print('PASS: real Ethereum ingestion → alteration → restoration, both incidents anchored.')


if __name__ == '__main__':
    main()
