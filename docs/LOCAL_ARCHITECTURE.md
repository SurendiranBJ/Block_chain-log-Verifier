# Local integrity architecture

The active implementation lives in `localchain/`. It replaces the cloud-oriented runtime as the default entry point. Older `backend/app.py`, cloud adapters, old environment examples, and two-device scripts remain in the repository for reference; they are not imported by the new application.

## Data flow

1. An administrator registers a source. The application receives a random source-scoped bearer token.
2. The application sends an audit event to `POST /api/sources/{id}/events`. The event has a stable ID, increasing integer sequence, timezone-aware timestamp, actor, action and message. Additional JSON fields are protected too.
3. The service validates the complete request before writing. SQLite stores the original event, full SHA-256 digest and deterministic commitment key. An atomic JSON source file contains the current log records.
4. A background worker sends queued commitments to the existing `LogIntegrityV3` Solidity contract. Each event is a one-leaf batch; its Merkle root equals its event hash. This deliberately trades batch efficiency for precise, simple recovery in a small local project.
5. The worker reads the chain as the reference, verifies local original evidence against it, and compares current source records. The browser reads cached results; closing it does not stop monitoring.
6. Every observed transition appends an observation containing source, event, timestamp, expected/observed digest, changed fields, observed content and the previous observation digest. Each observation receives its own on-chain commitment. A durable outbox retries interruptions.

## Storage and trust

| Component | Purpose | Trust boundary |
| --- | --- | --- |
| `sources/{id}.json` | Current, intentionally mutable local audit stream | Changes are expected to be detectable |
| `audit.sqlite3` | Original evidence, source registrations, states, observation history, write outbox | Original content and history are checked against chain commitments |
| `workspace.id` | Stable namespace for chain inventory | Must be retained with backups |
| `chain.json` | RPC, chain ID, genesis pin, writer key, contract and observer endpoints | Secret configuration; owner-only permissions |
| Geth data | Ethereum chain and validator keystore | A single operator controls the single-node trust boundary |
| Solidity V3 contract | Append-only event and observation commitments | Authorized writers only; existing commitment keys cannot be overwritten |

The worker compares on-chain key inventory with local inventory so deleting a local row cannot silently remove it from verification. A missing source registration also fails closed. Source files that disappear or cannot be parsed produce source-level incidents. No log deletion/reset API is exposed. SQLite triggers reject ordinary history edits/deletions; a root administrator can still bypass SQLite and alter the underlying storage. The blockchain comparison is the tamper-evidence mechanism, not those triggers.

## State machine

- `VERIFIED`: current JSON content matches the original chain commitment.
- `MODIFIED`: any field differs, including nested or additional fields.
- `DELETED`: a committed event ID is absent from a readable source.
- `REORDERED`: surviving committed IDs have changed their relative order.
- `DUPLICATE`: a committed event ID appears more than once.
- `UNEXPECTED`: a source contains a record that was never ingested/committed.
- `SOURCE_UNREADABLE`: a missing, invalid, oversized or symlinked source file.
- `RESTORED`: a history event when a previously violating record/source returns to its expected state. Removing an unexpected record is also a restoration.
- `UNAVAILABLE`: chain, evidence, or history integrity cannot be verified. Last results are explicitly stale; no false restoration is emitted.

Repeated unchanged scans do not create duplicate incidents. Changing a modified log to a different modified value creates another observation. Modification, restoration, and later modification create three independent records.

When an event has multiple simultaneous problems, display precedence is deletion → duplication → content modification → reorder. The current snapshot and history preserve the observed evidence; they do not claim that only one underlying attack occurred.

## Scope and limits

- This is a local, small-volume audit integrity project, not a production SIEM or hardened enterprise blockchain deployment.
- Monitoring operates on the platform's local source files. Merely POSTing a copy of an application's separate file does **not** monitor subsequent edits to that separate file. Use the returned source path as the application's monitored stream, as the demo does, or build an authenticated snapshot/file collector before claiming remote-source coverage.
- Source files use JSON arrays. Content canonicalization ignores whitespace and JSON object key order, preserves array order and value types, and hashes all event fields. It is an application-specific canonical format, not RFC 8785/JCS interoperability.
- Polling interval is two seconds **plus scan and transaction time**. An edit restored entirely between scans cannot be detected. Durable change-data capture or an OS audit agent is needed to observe every filesystem write. Never claim otherwise in a project presentation.
- Before a commitment is mined, the event is pending. An outage queues work and fails closed. It does not produce a simulated blockchain fallback.
- Single-node PoA does not resist compromise of the validator host/key or deliberate chain replacement by its sole operator. Peers on independent machines and independently retained checkpoints improve detectability. Even multiple peers do not automatically imply Byzantine fault tolerance.
- Geth 1.13.15 is a pinned **legacy lab dependency** because newer Geth releases removed Clique sealing. Keep the lab isolated. Plan a tested migration to a maintained permissioned client/consensus stack before real deployment.
- The local HTTP service binds only to loopback. It uses HTTP-only, same-site session cookies, origin/host checks, source-scoped tokens, body limits and a restrictive dashboard CSP. It is not a public internet deployment, TLS gateway or multi-user RBAC service.
- Keep volume small (hundreds of records). Verification scans all commitments and history. Batching, incremental indexing, checkpoint verification and bounded history retrieval are future scale work.

## Recovery

Stop all processes before making a consistent full backup of `runtime/` and the Geth data directory. Preserve genesis, workspace identity, original SQLite evidence, source files, writer configuration, keystore and password; encrypt backups and restrict access. Evidence export is a report, **not** a complete backup.

On restart, unreceipted outbox entries are retried with the same immutable keys. If the transaction succeeded before local receipt storage, an identical on-chain commitment is recovered instead of being overwritten. `recovered-on-chain` denotes this reconciliation; it does not invent a transaction hash. A different on-chain value is an error.

Missing local evidence must be restored from backup. Hashes alone cannot reconstruct original log contents. The service will not regenerate a baseline from modified current records.
