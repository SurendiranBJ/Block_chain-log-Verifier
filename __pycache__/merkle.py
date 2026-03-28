import hashlib
import math

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def build_merkle_tree(entries: list[str]) -> dict:
    """
    Build a Merkle tree from a list of log entries.
    Returns: {
        'root': str,
        'leaves': [str],   # hashes of each entry
        'tree': [[str]],   # all levels, bottom-up
    }
    """
    if not entries:
        return {'root': sha256(''), 'leaves': [], 'tree': []}

    leaves = [sha256(e) for e in entries]
    tree = [leaves[:]]
    current = leaves[:]

    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])   # duplicate last node if odd
        parent = []
        for i in range(0, len(current), 2):
            parent.append(sha256(current[i] + current[i+1]))
        tree.append(parent)
        current = parent

    return {
        'root': current[0],
        'leaves': leaves,
        'tree': tree,
    }

def get_proof(tree_data: dict, entry_index: int) -> list[dict]:
    """
    Returns the Merkle proof path for a single entry index.
    Each step: {'hash': str, 'direction': 'left'|'right'}
    """
    tree = tree_data['tree']
    proof = []
    idx = entry_index

    for level in tree[:-1]:  # skip root level
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        sibling_idx = idx ^ 1  # XOR to get sibling
        direction = 'right' if idx % 2 == 0 else 'left'
        proof.append({'hash': level[sibling_idx], 'direction': direction})
        idx //= 2

    return proof

def verify_proof(entry: str, proof: list[dict], root: str) -> bool:
    """
    Verify a single log entry against a stored Merkle root using its proof path.
    """
    computed = sha256(entry)
    for step in proof:
        if step['direction'] == 'right':
            computed = sha256(computed + step['hash'])
        else:
            computed = sha256(step['hash'] + computed)
    return computed == root

def entries_from_logfile(path: str) -> list[str]:
    """Read non-empty lines from a log file."""
    with open(path, 'r') as f:
        return [line.rstrip('\n') for line in f if line.strip()]

def find_tampered_lines(path: str, stored_root: str) -> dict:
    """
    Compare current file against stored Merkle root.
    Returns: {
        'tampered': bool,
        'current_root': str,
        'stored_root': str,
        'changed_lines': [int],   # 0-based indices of changed lines
        'total_lines': int,
    }
    """
    entries = entries_from_logfile(path)
    tree_data = build_merkle_tree(entries)
    current_root = tree_data['root']

    # Naive per-line tamper scan (only runs when roots differ)
    changed = []
    if current_root != stored_root:
        leaf_hashes = tree_data['leaves']
        # We can't know original leaves from chain, so we report line count delta
        # Full per-line detection requires storing leaf hashes alongside root
        changed = list(range(len(entries)))  # flag all as suspect

    return {
        'tampered': current_root != stored_root,
        'current_root': current_root,
        'stored_root': stored_root,
        'changed_lines': changed,
        'total_lines': len(entries),
    }