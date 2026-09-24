"""
LogChain - SHA-256 Hashing Engine
Provider-independent event hashing based on canonical serialization.
"""
import hashlib
from backend.canonical import canonicalize_event


def hash_event(event: dict) -> str:
    """
    Compute SHA-256 hash of a normalized event.

    Input:  normalized event dict
    Output: 64-character lowercase hexadecimal SHA-256 string

    The hash is based on canonical serialization - NOT on raw line content,
    str(dict), or any non-deterministic representation.
    """
    canonical_bytes = canonicalize_event(event)
    return hashlib.sha256(canonical_bytes).hexdigest()


def hash_bytes(data: bytes) -> str:
    """SHA-256 of arbitrary bytes. Returns 64-char hex string."""
    return hashlib.sha256(data).hexdigest()


def hash_pair(left: str, right: str) -> str:
    """
    SHA-256 of concatenated hex strings.
    Used in Merkle tree pair hashing.
    Both inputs must be 64-char hex strings.
    """
    combined = (left + right).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()
