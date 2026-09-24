"""
LogChain - Merkle Tree Engine
Deterministic binary Merkle tree for batch integrity.
"""
from typing import Optional
from backend.hashing import hash_pair


def build_merkle_tree(leaf_hashes: list[str]) -> dict:
    """
    Build a Merkle tree from a list of leaf hashes.

    Rules:
    - Deterministic ordering: input order is preserved.
    - Odd count: last node is duplicated (standard Bitcoin-style Merkle).
    - SHA-256 used for pair hashing.
    - Single-leaf tree: root == that leaf hash.
    - Empty list: root is None.

    Args:
        leaf_hashes: List of 64-char hex SHA-256 strings (in sequence order).

    Returns:
        {
            "root": "...",            # Merkle root hex string (or None if empty)
            "leaf_hashes": [...],     # Input leaf hashes (unchanged)
            "entry_count": N,         # Number of leaves
            "tree_levels": [...]      # All levels for debugging
        }
    """
    if not leaf_hashes:
        return {
            "root": None,
            "leaf_hashes": [],
            "entry_count": 0,
            "tree_levels": [],
        }

    leaves = list(leaf_hashes)  # copy to avoid mutation
    tree_levels = [leaves[:]]

    current_level = leaves[:]
    while len(current_level) > 1:
        next_level = []
        # Process pairs
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            # Duplicate last node if odd count
            right = current_level[i + 1] if (i + 1) < len(current_level) else current_level[i]
            next_level.append(hash_pair(left, right))
        tree_levels.append(next_level[:])
        current_level = next_level

    root = current_level[0]
    return {
        "root": root,
        "leaf_hashes": leaves,
        "entry_count": len(leaves),
        "tree_levels": tree_levels,
    }


def compute_merkle_root(leaf_hashes: list[str]) -> Optional[str]:
    """Convenience wrapper returning just the root."""
    return build_merkle_tree(leaf_hashes)["root"]


def make_batch_id(case_id: str, sequence_start: int) -> str:
    """
    Generate a deterministic batch ID.
    Format: batch-CASE-001-000001
    """
    return f"batch-{case_id}-{sequence_start:06d}"


def verify_root(leaf_hashes: list[str], expected_root: str) -> bool:
    """Recompute the Merkle root and compare to expected."""
    computed = compute_merkle_root(leaf_hashes)
    return computed == expected_root
