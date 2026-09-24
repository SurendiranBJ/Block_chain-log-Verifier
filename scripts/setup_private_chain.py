"""
LogChain - Secure Private Chain Setup
Generates fresh validator accounts for Device 1 and Device 2,
creates keystores and password files, and builds a matching genesis.json.

Zero hard-coded compromised keys.

Usage:
    python scripts/setup_private_chain.py
"""
import json
import os
import secrets
import sys
from pathlib import Path
from web3 import Web3

_ROOT = Path(__file__).resolve().parent.parent


def setup_chain():
    print("============================================================")
    print(" LogChain - Secure Private Chain Setup (2-Validator Clique PoA)")
    print("============================================================")

    w3 = Web3()

    # 1. Generate fresh validator for Device 1
    acct1 = w3.eth.account.create()
    pwd1 = secrets.token_hex(16)
    keystore1 = acct1.encrypt(pwd1)

    node1_dir = _ROOT / "node1_data"
    node1_dir.mkdir(parents=True, exist_ok=True)
    (node1_dir / "keystore").mkdir(exist_ok=True)
    with open(node1_dir / "password.txt", "w") as f:
        f.write(pwd1)
    with open(node1_dir / "keystore" / f"UTC--node1--{acct1.address.lower()}", "w") as f:
        json.dump(keystore1, f, indent=2)

    # 2. Generate fresh validator for Device 2
    acct2 = w3.eth.account.create()
    pwd2 = secrets.token_hex(16)
    keystore2 = acct2.encrypt(pwd2)

    node2_dir = _ROOT / "node2_data"
    node2_dir.mkdir(parents=True, exist_ok=True)
    (node2_dir / "keystore").mkdir(exist_ok=True)
    with open(node2_dir / "password.txt", "w") as f:
        f.write(pwd2)
    with open(node2_dir / "keystore" / f"UTC--node2--{acct2.address.lower()}", "w") as f:
        json.dump(keystore2, f, indent=2)

    # 3. Generate Clique extradata
    # Clique PoA extradata: 32 bytes 0x00 + 20 bytes per signer (sorted/ordered) + 65 bytes 0x00
    addr1_bytes = bytes.fromhex(acct1.address[2:].lower())
    addr2_bytes = bytes.fromhex(acct2.address[2:].lower())
    signers_bytes = addr1_bytes + addr2_bytes

    prefix = b"\x00" * 32
    suffix = b"\x00" * 65
    extradata = "0x" + (prefix + signers_bytes + suffix).hex()

    # 4. Generate genesis.json
    genesis = {
        "config": {
            "chainId": 12345,
            "homesteadBlock": 0,
            "eip150Block": 0,
            "eip155Block": 0,
            "eip158Block": 0,
            "byzantiumBlock": 0,
            "constantinopleBlock": 0,
            "petersburgBlock": 0,
            "istanbulBlock": 0,
            "clique": {
                "period": 5,
                "epoch": 30000,
            },
        },
        "difficulty": "1",
        "gasLimit": "8000000",
        "extradata": extradata,
        "alloc": {
            acct1.address: {"balance": "1000000000000000000000"},
            acct2.address: {"balance": "1000000000000000000000"},
        },
    }

    genesis_path = _ROOT / "genesis.json"
    with open(genesis_path, "w") as f:
        json.dump(genesis, f, indent=2)
    print(f"\n[PASS] Updated genesis.json with fresh signers")

    print(f"\n[Device 1 Validator]")
    print(f"  Address:     {acct1.address}")
    print(f"  Private Key: {acct1.key.hex()}")
    print(f"  Password:    {pwd1}")
    print(f"  Keystore:    {node1_dir / 'keystore'}")

    print(f"\n[Device 2 Validator]")
    print(f"  Address:     {acct2.address}")
    print(f"  Private Key: {acct2.key.hex()}")
    print(f"  Password:    {pwd2}")
    print(f"  Keystore:    {node2_dir / 'keystore'}")

    # Generate sample .env snippet
    env_sample = f"""
# Copy to .env for Device 1:
BLOCKCHAIN_ACCOUNT={acct1.address}
BLOCKCHAIN_PRIVATE_KEY={acct1.key.hex()}
BLOCKCHAIN_PASSWORD={pwd1}
CHAIN_ID=12345
DEVICE1_IP=127.0.0.1
DEVICE2_IP=127.0.0.1

# For Device 2 (.env):
DEVICE2_ACCOUNT={acct2.address}
DEVICE2_PRIVATE_KEY={acct2.key.hex()}
DEVICE2_PASSWORD={pwd2}
"""
    print("\n============================================================")
    print("SETUP INSTRUCTIONS:")
    print("1. Keystore files and passwords created in node1_data and node2_data.")
    print("2. genesis.json is configured with both accounts as active signers.")
    print("3. On Device 1: initialize Geth (`geth --datadir node1_data init genesis.json`).")
    print("4. On Device 2: copy genesis.json, initialize Geth (`geth --datadir node2_data init genesis.json`).")
    print("5. Start Device 1 (`./scripts/start_device1.sh`).")
    print("6. Start Device 2 (`./scripts/start_device2.sh`).")
    print("7. Connect peers (`./scripts/connect_nodes.sh`).")
    print("============================================================")


if __name__ == "__main__":
    setup_chain()
