// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * LogIntegrityV3
 * ==============================================================
 * Zero-Trust Cross-Cloud Log Integrity System
 * Append-Only Merkle Batch Anchoring Contract
 * ==============================================================
 *
 * Security model:
 * - A committed batch CANNOT be overwritten (append-only).
 * - A batch ID CANNOT be reused (duplicate protection).
 * - Only authorized writer accounts can anchor batches.
 * - Owner can add/remove writers (access control).
 * - Event IDs, sequences, and hashes stored on-chain for tamper-evidence.
 * - No sensitive raw log messages stored on-chain.
 *
 * Design principles:
 * - TAMPER-EVIDENT (not tamper-proof)
 * - INDEPENDENT VERIFICATION via event identity & hash retrieval
 * - CRYPTOGRAPHIC COMMITMENT of original log content
 * - DETECTS POST-COMMITMENT MODIFICATIONS, DELETIONS, REORDERING, INSERTIONS
 */
contract LogIntegrityV3 {

    // ── Access Control ────────────────────────────────────────────────────
    address public owner;
    mapping(address => bool) public writers;

    event WriterUpdated(address indexed writer, bool allowed);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner()  { require(msg.sender == owner,          "Not owner");  _; }
    modifier onlyWriter() { require(writers[msg.sender],           "Not writer"); _; }

    constructor() {
        owner = msg.sender;
        writers[msg.sender] = true;
        emit WriterUpdated(msg.sender, true);
    }

    function addWriter(address w) external onlyOwner {
        writers[w] = true;
        emit WriterUpdated(w, true);
    }

    function removeWriter(address w) external onlyOwner {
        require(w != owner, "Cannot remove owner as writer");
        writers[w] = false;
        emit WriterUpdated(w, false);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
        writers[newOwner] = true;
    }

    // ── Batch Data ────────────────────────────────────────────────────────

    struct Batch {
        string    merkleRoot;     // SHA-256 Merkle root (hex string)
        uint256   entryCount;     // Number of events in this batch
        uint256   anchoredAt;     // Block timestamp when anchored
        bool      exists;         // Duplicate protection flag
        string[]  eventIds;       // Event IDs in committed sequence order
        uint256[] eventSequences; // Event sequence numbers in committed order
        string[]  eventHashes;    // Individual event SHA-256 hashes in sequence order
    }

    // caseId → batchId → Batch
    mapping(bytes32 => mapping(bytes32 => Batch)) private _batches;

    // caseId → ordered list of batch IDs
    mapping(bytes32 => string[]) private _caseBatchIds;

    // caseId → known flag
    mapping(bytes32 => bool) private _knownCase;
    string[] public allCaseIds;

    // ── Events ────────────────────────────────────────────────────────────

    event BatchAnchored(
        string  indexed caseId,
        string  indexed batchId,
        string          merkleRoot,
        uint256         entryCount,
        uint256         anchoredAt
    );

    // ── Write ─────────────────────────────────────────────────────────────

    /**
     * Anchor a batch of events to the blockchain.
     *
     * @param caseId         Investigation case identifier
     * @param batchId        Unique batch identifier (append-only: cannot reuse)
     * @param merkleRoot     SHA-256 Merkle root of all event hashes
     * @param entryCount     Number of events in this batch
     * @param eventIds       List of event IDs in sequence order
     * @param eventSequences List of event sequence numbers in sequence order
     * @param eventHashes    SHA-256 hash of each event in sequence order
     *
     * Reverts if:
     * - batchId already exists (append-only, no overwrites)
     * - merkleRoot or batchId or caseId is empty
     * - entryCount == 0
     * - eventIds, eventSequences, or eventHashes length mismatch entryCount
     * - caller is not an authorized writer
     */
    function anchorBatch(
        string   calldata caseId,
        string   calldata batchId,
        string   calldata merkleRoot,
        uint256           entryCount,
        string[] calldata eventIds,
        uint256[] calldata eventSequences,
        string[] calldata eventHashes
    ) external onlyWriter {
        require(bytes(batchId).length > 0,           "batchId cannot be empty");
        require(bytes(merkleRoot).length > 0,        "merkleRoot cannot be empty");
        require(bytes(caseId).length > 0,            "caseId cannot be empty");
        require(entryCount > 0,                      "entryCount must be > 0");
        require(eventIds.length == entryCount,       "eventIds length mismatch");
        require(eventSequences.length == entryCount, "eventSequences length mismatch");
        require(eventHashes.length == entryCount,    "eventHashes length mismatch");

        bytes32 caseKey  = keccak256(abi.encodePacked(caseId));
        bytes32 batchKey = keccak256(abi.encodePacked(batchId));

        // APPEND-ONLY: reject duplicate batch IDs
        require(
            !_batches[caseKey][batchKey].exists,
            "Batch already anchored: append-only contract"
        );

        Batch storage b = _batches[caseKey][batchKey];
        b.merkleRoot  = merkleRoot;
        b.entryCount  = entryCount;
        b.anchoredAt  = block.timestamp;
        b.exists      = true;

        for (uint256 i = 0; i < entryCount; i++) {
            b.eventIds.push(eventIds[i]);
            b.eventSequences.push(eventSequences[i]);
            b.eventHashes.push(eventHashes[i]);
        }

        // Track case and batch ordering
        if (!_knownCase[caseKey]) {
            _knownCase[caseKey] = true;
            allCaseIds.push(caseId);
        }
        _caseBatchIds[caseKey].push(batchId);

        emit BatchAnchored(caseId, batchId, merkleRoot, entryCount, block.timestamp);
    }

    // ── Read ──────────────────────────────────────────────────────────────

    /**
     * Get full batch data including event IDs, sequences, and hashes.
     * Returns (merkleRoot, entryCount, anchoredAt, exists, eventIds, eventSequences, eventHashes)
     */
    function getBatch(string calldata caseId, string calldata batchId)
        external
        view
        returns (
            string   memory merkleRoot,
            uint256         entryCount,
            uint256         anchoredAt,
            bool            exists,
            string[] memory eventIds,
            uint256[] memory eventSequences,
            string[] memory eventHashes
        )
    {
        bytes32 caseKey  = keccak256(abi.encodePacked(caseId));
        bytes32 batchKey = keccak256(abi.encodePacked(batchId));
        Batch storage b  = _batches[caseKey][batchKey];
        return (
            b.merkleRoot,
            b.entryCount,
            b.anchoredAt,
            b.exists,
            b.eventIds,
            b.eventSequences,
            b.eventHashes
        );
    }

    /**
     * Get identity and hash for a specific event within a batch by index (0-based).
     */
    function getEventIdentity(
        string  calldata caseId,
        string  calldata batchId,
        uint256          index
    ) external view returns (string memory eventId, uint256 sequence, string memory eventHash) {
        bytes32 caseKey  = keccak256(abi.encodePacked(caseId));
        bytes32 batchKey = keccak256(abi.encodePacked(batchId));
        Batch storage b  = _batches[caseKey][batchKey];
        require(b.exists,             "Batch not found");
        require(index < b.entryCount, "Index out of range");
        return (b.eventIds[index], b.eventSequences[index], b.eventHashes[index]);
    }

    /**
     * Get the hash of a specific event within a batch by index (0-based).
     */
    function getEventHash(
        string  calldata caseId,
        string  calldata batchId,
        uint256          index
    ) external view returns (string memory) {
        bytes32 caseKey  = keccak256(abi.encodePacked(caseId));
        bytes32 batchKey = keccak256(abi.encodePacked(batchId));
        Batch storage b  = _batches[caseKey][batchKey];
        require(b.exists,             "Batch not found");
        require(index < b.entryCount, "Index out of range");
        return b.eventHashes[index];
    }

    /**
     * Get ordered list of batch IDs for a case.
     */
    function getCaseBatches(string calldata caseId)
        external
        view
        returns (string[] memory)
    {
        bytes32 caseKey = keccak256(abi.encodePacked(caseId));
        return _caseBatchIds[caseKey];
    }

    /**
     * Check if a batch exists (duplicate detection).
     */
    function batchExists(string calldata caseId, string calldata batchId)
        external
        view
        returns (bool)
    {
        bytes32 caseKey  = keccak256(abi.encodePacked(caseId));
        bytes32 batchKey = keccak256(abi.encodePacked(batchId));
        return _batches[caseKey][batchKey].exists;
    }

    /**
     * Total number of unique cases anchored.
     */
    function getCaseCount() external view returns (uint256) {
        return allCaseIds.length;
    }

    /**
     * Total number of batches anchored for a case.
     */
    function getBatchCount(string calldata caseId) external view returns (uint256) {
        bytes32 caseKey = keccak256(abi.encodePacked(caseId));
        return _caseBatchIds[caseKey].length;
    }
}
