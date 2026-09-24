"""
LogChain - Blockchain Interface
Connects to private Geth network, anchors Merkle batches via V3 contract.
All credentials from environment. No hard-coded keys.
"""
import json
import time
import logging
from pathlib import Path
from typing import Optional
from web3 import Web3
from web3.exceptions import ContractLogicError

from backend.config import (
    DEVICE1_RPC, DEVICE2_RPC, CHAIN_ID,
    BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT,
    CONTRACT_ADDRESS, ABI_V3_PATH, DEPLOYMENT_PATH,
)

logger = logging.getLogger(__name__)

_w3_device1: Optional[Web3] = None
_w3_device2: Optional[Web3] = None
_contract   = None
_abi        = None


def _load_abi() -> list:
    global _abi
    if _abi is None:
        path = Path(ABI_V3_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"V3 ABI not found at {ABI_V3_PATH}. "
                "Deploy the contract first: ./scripts/deploy_contract.sh"
            )
        with open(path) as f:
            _abi = json.load(f)
    return _abi


def get_w3(device: int = 1) -> Web3:
    """Get connected Web3 instance for device 1 or 2."""
    global _w3_device1, _w3_device2
    if device == 1:
        if _w3_device1 is None or not _w3_device1.is_connected():
            _w3_device1 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
        return _w3_device1
    else:
        if _w3_device2 is None or not _w3_device2.is_connected():
            _w3_device2 = Web3(Web3.HTTPProvider(DEVICE2_RPC))
        return _w3_device2


def get_contract(w3: Optional[Web3] = None):
    """Get V3 contract instance."""
    global _contract
    if w3 is None:
        w3 = get_w3(1)
    abi = _load_abi()
    if not CONTRACT_ADDRESS:
        raise RuntimeError(
            "CONTRACT_ADDRESS not set in environment. "
            "Deploy the contract first."
        )
    addr = Web3.to_checksum_address(CONTRACT_ADDRESS)
    return w3.eth.contract(address=addr, abi=abi)


def blockchain_status() -> dict:
    """Return status of both blockchain nodes."""
    status = {
        "device1": {"connected": False, "block": 0, "peer_count": 0, "chain_id": None},
        "device2": {"connected": False, "block": 0, "peer_count": 0, "chain_id": None},
        "contract_address": CONTRACT_ADDRESS,
    }
    for dev in [1, 2]:
        try:
            w3 = get_w3(dev)
            if w3.is_connected():
                key = f"device{dev}"
                status[key]["connected"] = True
                status[key]["block"]     = w3.eth.block_number
                status[key]["chain_id"]  = w3.eth.chain_id
                try:
                    status[key]["peer_count"] = w3.net.peer_count
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Device {dev} status error: {e}")
    return status


def anchor_batch(
    case_id: str,
    batch_id: str,
    merkle_root: str,
    entry_count: int,
    event_ids: list[str],
    event_sequences: list[int],
    event_hashes: list[str],
    gas: int = 3500000,
) -> dict:
    """
    Anchor a Merkle batch to the blockchain via V3 contract.

    Returns:
        {
            "tx_hash": "0x...",
            "block_number": N,
            "gas_used": N,
            "status": "ANCHORED"
        }
    """
    if not BLOCKCHAIN_PRIVATE_KEY:
        raise RuntimeError("BLOCKCHAIN_PRIVATE_KEY not set in environment.")
    if not BLOCKCHAIN_ACCOUNT:
        raise RuntimeError("BLOCKCHAIN_ACCOUNT not set in environment.")

    w3 = get_w3(1)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Device 1 at {DEVICE1_RPC}")

    contract = get_contract(w3)
    account  = Web3.to_checksum_address(BLOCKCHAIN_ACCOUNT)
    nonce    = w3.eth.get_transaction_count(account)

    tx = contract.functions.anchorBatch(
        case_id,
        batch_id,
        merkle_root,
        entry_count,
        event_ids,
        event_sequences,
        event_hashes,
    ).build_transaction({
        "chainId":  CHAIN_ID,
        "gas":      gas,
        "gasPrice": w3.to_wei("1", "gwei"),
        "nonce":    nonce,
    })

    signed  = w3.eth.account.sign_transaction(tx, BLOCKCHAIN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"Batch anchor tx sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if not receipt or receipt.get("status") != 1:
        raise RuntimeError(
            f"Transaction failed or reverted: {tx_hash.hex()} (receipt status: {receipt.get('status') if receipt else 'None'})"
        )

    logger.info(
        f"Batch {batch_id} anchored at block {receipt['blockNumber']}"
    )
    return {
        "tx_hash":     tx_hash.hex(),
        "block_number": receipt["blockNumber"],
        "gas_used":    receipt["gasUsed"],
        "status":      "ANCHORED",
    }


def get_batch_on_chain(case_id: str, batch_id: str) -> Optional[dict]:
    """
    Retrieve an anchored batch from the blockchain.
    Returns None if not found on chain (exists == False).
    Raises ConnectionError if blockchain is unreachable.
    Raises Exception on contract/RPC call failure.
    """
    w3 = get_w3(1)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Device 1 at {DEVICE1_RPC}")

    contract = get_contract(w3)
    result = contract.functions.getBatch(case_id, batch_id).call()
    # Returns: (merkleRoot, entryCount, timestamp, exists, eventIds, eventSequences, eventHashes)
    if not result[3]:  # exists == False
        return None
    return {
        "merkle_root":     result[0],
        "entry_count":     result[1],
        "timestamp":       result[2],
        "exists":          result[3],
        "event_ids":       list(result[4]),
        "event_sequences": [int(s) for s in result[5]],
        "event_hashes":    list(result[6]),
    }


def get_event_identity_on_chain(case_id: str, batch_id: str, index: int) -> Optional[dict]:
    """Retrieve event identity from chain by index."""
    w3 = get_w3(1)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Device 1 at {DEVICE1_RPC}")

    contract = get_contract(w3)
    eid, seq, h = contract.functions.getEventIdentity(case_id, batch_id, index).call()
    return {
        "event_id": eid,
        "sequence": int(seq),
        "event_hash": h,
    }


def get_case_batches(case_id: str) -> list[str]:
    """Get list of all batch IDs for a case directly from blockchain."""
    w3 = get_w3(1)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Device 1 at {DEVICE1_RPC}")

    contract = get_contract(w3)
    return list(contract.functions.getCaseBatches(case_id).call())


def batch_exists(case_id: str, batch_id: str) -> bool:
    """Check if a batch ID already exists on chain."""
    result = get_batch_on_chain(case_id, batch_id)
    return result is not None


def load_deployment_info() -> dict:
    """Load deployment info (non-secret values only)."""
    path = Path(DEPLOYMENT_PATH)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}
