// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract LogIntegrity {

    address public owner;
    mapping(address => bool) public writers;

    struct LogEntry {
        bytes32 merkleRoot;      // Merkle root of all log lines
        bytes32 fileHash;        // Full-file SHA-256 (kept for legacy verify)
        uint256 timestamp;
        string  caseId;
        string  fileId;
        bool    exists;
    }

    // key: keccak256(abi.encodePacked(caseId, fileId))
    mapping(bytes32 => LogEntry) public logs;

    // Track all (caseId, fileId) pairs ever registered
    bytes32[]   public logKeys;
    string[]    public caseIds;
    string[]    public fileIds;
    mapping(bytes32 => bool) private knownKey;
    mapping(string  => bool) private knownCase;

    event LogAdded(string indexed caseId, string indexed fileId,
                   bytes32 merkleRoot, bytes32 fileHash, uint256 timestamp);

    modifier onlyOwner()  { require(msg.sender == owner,  "Not owner");  _; }
    modifier onlyWriter() { require(writers[msg.sender],  "Not writer"); _; }

    constructor() { owner = msg.sender; writers[msg.sender] = true; }

    function setWriter(address w, bool allowed) external onlyOwner {
        writers[w] = allowed;
    }

    function addLog(
        string  calldata caseId,
        string  calldata fileId,
        bytes32 merkleRoot,
        bytes32 fileHash
    ) external onlyWriter {
        bytes32 key = keccak256(abi.encodePacked(caseId, fileId));
        logs[key] = LogEntry(merkleRoot, fileHash, block.timestamp, caseId, fileId, true);

        if (!knownKey[key]) {
            knownKey[key] = true;
            logKeys.push(key);
            fileIds.push(fileId);
            if (!knownCase[caseId]) {
                knownCase[caseId] = true;
                caseIds.push(caseId);
            }
        }
        emit LogAdded(caseId, fileId, merkleRoot, fileHash, block.timestamp);
    }

    function getLog(string calldata caseId, string calldata fileId)
        external view returns (bytes32 merkleRoot, bytes32 fileHash,
                               uint256 timestamp, bool exists)
    {
        bytes32 key = keccak256(abi.encodePacked(caseId, fileId));
        LogEntry storage e = logs[key];
        return (e.merkleRoot, e.fileHash, e.timestamp, e.exists);
    }

    function entryExists(string calldata caseId, string calldata fileId)
        external view returns (bool)
    {
        bytes32 key = keccak256(abi.encodePacked(caseId, fileId));
        return logs[key].exists;
    }

    function getCaseCount() external view returns (uint256) { return caseIds.length; }
    function getFileCount() external view returns (uint256) { return fileIds.length; }
}