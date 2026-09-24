import hashlib

def hash_entry(entry):
    return hashlib.sha256(entry.strip().encode()).hexdigest()

def hash_pair(left, right):
    return hashlib.sha256((left + right).encode()).hexdigest()

def build_merkle_tree(entries):
    if not entries:
        return None, [], []
    entries = [e for e in entries if e.strip()]
    if not entries:
        return None, [], []
    leaves = [hash_entry(e) for e in entries]
    tree = [leaves]
    current_level = leaves[:]
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
            next_level.append(hash_pair(left, right))
        tree.append(next_level)
        current_level = next_level
    root = current_level[0]
    return root, leaves, tree

def print_tree(tree, entries):
    print("\n" + "="*60)
    print("MERKLE TREE")
    print("="*60)
    print(f"Total entries: {len(entries)}")
    print(f"Merkle Root: {tree[-1][0]}")
    print("\nLeaf hashes (per line):")
    for i, (entry, leaf) in enumerate(zip(entries, tree[0])):
        preview = entry.strip()[:40] + "..." if len(entry.strip()) > 40 else entry.strip()
        print(f"  [{i}] {leaf[:16]}... → \"{preview}\"")
    print("="*60 + "\n")
