"""
LogChain - Contract Deployment Script (Python)
Compiles, deploys V3 contract, saves deployment.json and ABI.

Usage:
    python scripts/deploy_contract.py

Requirements:
    pip install web3 py-solc-x python-dotenv
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import (
    DEVICE1_RPC, CHAIN_ID,
    BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT,
    ABI_V3_PATH, DEPLOYMENT_PATH,
)

try:
    from web3 import Web3
    from solcx import compile_source, install_solc
except ImportError:
    print("[ERROR] Missing dependencies. Run: pip install web3 py-solc-x")
    sys.exit(1)


CONTRACT_SOL = Path(__file__).parent.parent / "contracts" / "LogIntegrityV3.sol"


def main():
    print("============================================================")
    print(" LogChain - V3 Contract Deployment")
    print("============================================================")

    if not BLOCKCHAIN_PRIVATE_KEY:
        print("[ERROR] BLOCKCHAIN_PRIVATE_KEY not set in .env")
        sys.exit(1)
    if not BLOCKCHAIN_ACCOUNT:
        print("[ERROR] BLOCKCHAIN_ACCOUNT not set in .env")
        sys.exit(1)
    if not CONTRACT_SOL.exists():
        print(f"[ERROR] Contract not found: {CONTRACT_SOL}")
        sys.exit(1)

    # 1. Connect
    print(f"\n[1] Connecting to {DEVICE1_RPC}...")
    w3 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
    if not w3.is_connected():
        print(f"[ERROR] Cannot connect to {DEVICE1_RPC}")
        sys.exit(1)

    actual_chain = w3.eth.chain_id
    print(f"    Block:    {w3.eth.block_number}")
    print(f"    Chain ID: {actual_chain}")

    if actual_chain != CHAIN_ID:
        print(f"[ERROR] Chain ID mismatch. Expected {CHAIN_ID}, got {actual_chain}")
        sys.exit(1)
    print("[PASS] Chain ID correct")

    # 2. Account
    account = Web3.to_checksum_address(BLOCKCHAIN_ACCOUNT)
    balance = w3.eth.get_balance(account)
    print(f"\n[2] Account: {account}")
    print(f"    Balance: {w3.from_wei(balance, 'ether')} ETH")
    if balance == 0:
        print("[WARN] Account has zero balance. Mining/funding may be needed.")

    # 3. Compile
    print(f"\n[3] Compiling {CONTRACT_SOL.name}...")
    try:
        install_solc("0.8.19", show_progress=False)
    except Exception as e:
        print(f"[WARN] solc installation check: {e}")

    with open(CONTRACT_SOL) as f:
        source = f.read()

    try:
        input_json = {
            "language": "Solidity",
            "sources": {"LogIntegrityV3.sol": {"content": source}},
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "viaIR": True,
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode"]}},
            },
        }
        compiled = solcx.compile_standard(input_json, solc_version="0.8.19")
        cdata = compiled["contracts"]["LogIntegrityV3.sol"]["LogIntegrityV3"]
        abi = cdata["abi"]
        bytecode = cdata["evm"]["bytecode"]["object"]
        print(f"[PASS] Compiled with viaIR: {len(abi)} ABI entries")
    except Exception as e:
        print(f"[ERROR] Failed to compile contract: {e}")
        print("Ensure solc 0.8.19 is available. You can run: python -c 'import solcx; solcx.install_solc(\"0.8.19\")'")
        sys.exit(1)

    # 4. Deploy
    print(f"\n[4] Deploying V3 contract...")
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account)
    tx = Contract.constructor().build_transaction({
        "chainId":  CHAIN_ID,
        "gas":      3000000,
        "gasPrice": w3.to_wei("1", "gwei"),
        "nonce":    nonce,
    })
    signed  = w3.eth.account.sign_transaction(tx, BLOCKCHAIN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"    Tx:    {tx_hash.hex()}")
    print(f"    Waiting for receipt...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        print(f"[ERROR] Deployment transaction failed")
        sys.exit(1)

    contract_address = receipt["contractAddress"]
    print(f"\n[PASS] V3 deployed at: {contract_address}")
    print(f"       Block:         {receipt['blockNumber']}")
    print(f"       Gas used:      {receipt['gasUsed']}")

    # 5. Save ABI
    abi_path = Path(ABI_V3_PATH)
    abi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(abi_path, "w") as f:
        json.dump(abi, f, indent=2)
    print(f"\n[5] ABI saved: {abi_path}")

    # 6. Save deployment.json (non-secret)
    deployment = {
        "chain_id":        CHAIN_ID,
        "contract_address": contract_address,
        "deployed_block":  receipt["blockNumber"],
        "network_name":    "logchain",
        "contract_version": "LogIntegrityV3",
        "tx_hash":         tx_hash.hex(),
    }
    with open(DEPLOYMENT_PATH, "w") as f:
        json.dump(deployment, f, indent=2)
    print(f"[6] Deployment info saved: {DEPLOYMENT_PATH}")

    # 7. Read test
    print(f"\n[7] Performing read test...")
    contract = w3.eth.contract(address=contract_address, abi=abi)
    owner = contract.functions.owner().call()
    print(f"    Owner: {owner}")
    is_writer = contract.functions.writers(account).call()
    print(f"    Is writer: {is_writer}")

    # 8. Test anchor
    print(f"\n[8] Performing test anchor...")
    test_tx = contract.functions.anchorBatch(
        "TEST-CASE",
        "batch-TEST-CASE-000001",
        "a" * 64,
        1,
        ["evt-001"],
        [1],
        ["b" * 64],
    ).build_transaction({
        "chainId":  CHAIN_ID,
        "gas":      500000,
        "gasPrice": w3.to_wei("1", "gwei"),
        "nonce":    w3.eth.get_transaction_count(account),
    })
    signed_test  = w3.eth.account.sign_transaction(test_tx, BLOCKCHAIN_PRIVATE_KEY)
    test_tx_hash = w3.eth.send_raw_transaction(signed_test.raw_transaction)
    test_receipt = w3.eth.wait_for_transaction_receipt(test_tx_hash)
    assert test_receipt["status"] == 1, "Test anchor failed"
    print(f"    [PASS] Test anchor succeeded")

    # 9. Verify test anchor
    batch_data = contract.functions.getBatch("TEST-CASE", "batch-TEST-CASE-000001").call()
    assert batch_data[3] == True, "getBatch returned exists=False"
    print(f"    [PASS] getBatch retrieval succeeded")

    # 10. Duplicate rejection test
    try:
        dup_tx = contract.functions.anchorBatch(
            "TEST-CASE",
            "batch-TEST-CASE-000001",
            "a" * 64,
            1,
            ["evt-001"],
            [1],
            ["b" * 64],
        ).build_transaction({
            "chainId": CHAIN_ID, "gas": 200000,
            "gasPrice": w3.to_wei("1", "gwei"),
            "nonce": w3.eth.get_transaction_count(account),
        })
        signed_dup = w3.eth.account.sign_transaction(dup_tx, BLOCKCHAIN_PRIVATE_KEY)
        w3.eth.send_raw_transaction(signed_dup.raw_transaction)
        print("    [WARN] Duplicate was accepted (unexpected)")
    except Exception as e:
        print(f"    [PASS] Duplicate batch correctly rejected")

    print("\n============================================================")
    print(f" DEPLOYMENT COMPLETE")
    print(f" Contract: {contract_address}")
    print(f"")
    print(f" Next step: Update .env with:")
    print(f" CONTRACT_ADDRESS={contract_address}")
    print("============================================================")


if __name__ == "__main__":
    main()
