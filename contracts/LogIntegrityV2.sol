// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * LogIntegrityV2
 * ─────────────────────────────────────────────────────────────────
 * Adds PER-ENTRY SHA-256 hash storage (indexed by line number)
 * on top of the original whole-file Merkle-root approach.
 *
 * Legacy API (addLog / getLog) is kept IDENTICAL to the deployed V1
 * ABI so existing Python scripts need zero changes.
 * ─────────────────────────────────────────────────────────────────
 */
contract LogIntegrityV2 {

    // ── Access control ────────────────────────────────────────────
    address public owner;
    mapping(address => bool) public writers;

    modifier onlyOwner()  { require(msg.sender == owner,  "Not owner");  _; }
    modifier onlyWriter() { require(writers[msg.sender],  "Not writer"); _; }

    constructor() {
        owner = msg.sender;
        writers[msg.sender] = true;
    }

    function setWriter(address w, bool allowed) external onlyOwner {
        writers[w] = allowed;
    }

    // ── Legacy whole-file structure (V1 compatible) ───────────────
    struct LegacyLog {
        string  merkleRoot;      // Merkle root of all log lines (hex string)
        string  investigatorId;
        uint256 entryCount;
        uint256 timestamp;
        bool    exists;
    }

    mapping(bytes32 => LegacyLog) private legacyLogs;
    string[] public caseIds;
    mapping(bytes32 => bool) private knownCase;

    event LogAdded(
        string  caseId,
        string  merkleRoot,
        uint256 entryCount,
        uint256 timestamp
    );

    /**
     * Legacy addLog — signature matches deployed V1 ABI exactly.
     * Stores the Merkle root + entry count for the whole file.
     */
    function addLog(
        string calldata caseId,
        string calldata merkleRoot,
        string calldata investigatorId,
        uint256         entryCount
    ) external onlyWriter {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        legacyLogs[key] = LegacyLog(
            merkleRoot,
            investigatorId,
            entryCount,
            block.timestamp,
            true
        );
        if (!knownCase[key]) {
            knownCase[key] = true;
            caseIds.push(caseId);
        }
        emit LogAdded(caseId, merkleRoot, entryCount, block.timestamp);
    }

    /**
     * Legacy getLog — returns (merkleRoot, investigatorId, entryCount, timestamp).
     * Matches deployed V1 ABI exactly.
     */
    function getLog(string calldata caseId)
        external view
        returns (string memory merkleRoot,
                 string memory investigatorId,
                 uint256 entryCount,
                 uint256 timestamp)
    {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        LegacyLog storage e = legacyLogs[key];
        return (e.merkleRoot, e.investigatorId, e.entryCount, e.timestamp);
    }

    function entryExists(string calldata caseId) external view returns (bool) {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        return legacyLogs[key].exists;
    }

    function getCaseCount() external view returns (uint256) {
        return caseIds.length;
    }

    // ── NEW: Per-entry hash storage ───────────────────────────────
    // caseId → lineIndex → sha256_hex_string
    mapping(bytes32 => mapping(uint256 => string)) private entryHashes;
    // caseId → number of entries stored
    mapping(bytes32 => uint256) private entryCounts;

    event EntryHashAdded(
        string  indexed caseId,
        uint256 indexed lineIndex,
        string  entryHash
    );

    /**
     * Store the SHA-256 hash of a single log line.
     * @param caseId    Identifies the log file / investigation case.
     * @param lineIndex 0-based line number in the log file.
     * @param entryHash hex-encoded SHA-256 of the trimmed log line.
     */
    function appendEntryHash(
        string  calldata caseId,
        uint256          lineIndex,
        string  calldata entryHash
    ) external onlyWriter {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        entryHashes[key][lineIndex] = entryHash;

        // Keep entryCounts as the high-water mark
        if (lineIndex + 1 > entryCounts[key]) {
            entryCounts[key] = lineIndex + 1;
        }
        emit EntryHashAdded(caseId, lineIndex, entryHash);
    }

    /**
     * Retrieve the stored hash for a specific line.
     * Returns empty string if not yet submitted.
     */
    function getEntryHash(string calldata caseId, uint256 lineIndex)
        external view
        returns (string memory)
    {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        return entryHashes[key][lineIndex];
    }

    /**
     * How many per-entry hashes have been submitted for a case.
     */
    function getEntryCount(string calldata caseId)
        external view
        returns (uint256)
    {
        bytes32 key = keccak256(abi.encodePacked(caseId));
        return entryCounts[key];
    }
}
