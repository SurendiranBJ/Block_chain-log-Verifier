# LogChain — Private blockchain audit-log integrity

Connect an existing application's logs to a local integrity dashboard backed by a private Ethereum blockchain. LogChain preserves original log contents, anchors SHA-256 commitments, detects observed edits/deletions, and keeps an incident timeline even when a log is restored.

**Create account → connect a log source → forward live logs → verify → retain tamper/restoration history.**

The default network has one Clique validator. Optional observer nodes replicate the ledger; they are not additional validators. Python, SQLite and the included dashboard provide the local workflow without MongoDB or cloud accounts.

## Start

On Ubuntu, install Python 3.12 and its venv support. From a clone of this repository:

```bash
bash scripts/start_local.sh
```

The launcher installs Python dependencies, downloads pinned Geth 1.13.15, creates fresh private-network keys on first use, deploys the existing Solidity V3 contract, and starts the dashboard:

**http://127.0.0.1:8080**

Open **Create account**, enter your name/email/password, then configure your application's log source during registration. Email identifies a local account; there is no email verification or delivery service.

Choose **Watch an existing log file** for the full external tamper-monitoring flow. Enter its absolute path and select plain text, JSON Lines or a structured JSON event array. Download the supplied agent and source-specific connection config, then run the exact command shown in setup. Keep your application, agent and LogChain running.

The agent forwards snapshots every two seconds; the dashboard refreshes automatically and the verifier runs on a one-second schedule. Blockchain confirmation and processing backlog add latency. Changes and restorations appear without clicking Verify now.

See [the account/source guide](ACCOUNT_SOURCE_GUIDE.md) for formats, direct API integration, reconnecting and limits.

Press Ctrl+C in the launcher terminal to stop. Subsequent starts preserve evidence and blockchain data. Do not run multiple launchers against one runtime directory or delete runtime data to troubleshoot.

## Accounts and sources

- Password authentication with salted scrypt hashes and expiring HttpOnly sessions.
- Separate evidence/log directories and blockchain namespaces for each account.
- Source-specific tokens for file agents or application backend API calls.
- File snapshots preserve first commitments and reveal observed modifications, deletions, reordering and restorations.
- Offline/missing/malformed sources appear unavailable, rather than verified from stale external contents.
- Search, filters, before/after inspection, permanent incident timeline and evidence export.
- Durable blockchain outbox and safe unchanged-event retries.
- Background verification continues when the dashboard is closed.

Existing pre-account records are available through **Open an existing token workspace**, using the token in `runtime/admin.token`. They are not automatically assigned to a new account.

The optional Northstar test application is available explicitly:

```bash
bash scripts/start_local.sh --demo
```

It runs on http://127.0.0.1:8081 and sends records to the existing token workspace.

## API integration

Choose API mode when your application's backend can send structured events:

```text
POST /api/sources/SOURCE_ID/events
Authorization: Bearer SOURCE_TOKEN
Content-Type: application/json

{"events":[{"event_id":"login-001","sequence":1,"timestamp":"2026-11-04T12:00:00Z","actor":"user-42","action":"login","message":"User signed in"}]}
```

Send stable IDs and increasing sequences. Unchanged retries are safe. Direct event ingestion protects the copy received by LogChain; use the file agent to detect later changes to the application's original file.

## Verify the implementation

```bash
python3 -m unittest discover -s tests/local -v
node tests/local/check_ui.js
node --check localchain/static/app.js
bash -n scripts/start_local.sh
```

For an explicitly labeled offline test ledger:

```bash
bash scripts/start_local.sh --simulate
```

Simulation uses a separate runtime directory and is not blockchain verification.

After starting and deploying a real node, run:

```bash
.venv/bin/python -m localchain.setup smoke
```

The GitHub Actions workflow exercises core tests and real-node smoke/observer replication. Local validation covers 39 Python tests and JavaScript flow/syntax checks. Real browser rendering and real Ethereum execution were not verified in the restricted build session; see [validation details](docs/VALIDATION.md).

## Project layout

| Location | Purpose |
| --- | --- |
| `localchain/accounts.py` | Password accounts and workspace isolation |
| `localchain/agent.py` | Downloadable standalone log-file forwarder |
| `localchain/core.py` | Evidence, original comparisons, durable outbox and incident history |
| `localchain/ledger.py` | Shared Ethereum writer and explicit simulation adapter |
| `localchain/server.py` | Dashboard API, sessions and background monitoring |
| `localchain/static/` | Account setup and integrity dashboard |
| `localchain/setup.py` | Validator initialization, deployment, observers and smoke test |
| `contracts/LogIntegrityV3.sol` | Append-only commitment contract |
| `tests/local/` | Local account, agent, integrity and HTTP regression checks |

The earlier cloud implementation remains for reference, with its former README in [docs/LEGACY_CLOUD_README.md](docs/LEGACY_CLOUD_README.md). Use the local launcher for this account/source workflow.

## Boundaries

Original log contents live in local evidence storage; cryptographic commitments and incident proofs are anchored on-chain. Blockchain provides tamper evidence relative to first received input, not proof that the input was truthful.

This version runs on one computer and binds to loopback. File snapshots target small log files under 900 KB and under the serialized request limit. Register a new source when rotating files. Plain-text identity uses physical line numbers; structured stable IDs give more precise deletion tracking. Keep each agent's state file across restarts. A change made and restored entirely between agent reads may be missed.

One validator depends on its signing key and chain data remaining trusted. The pinned legacy Geth/Clique setup is an educational private network. Review [multi-node instructions](docs/MULTI_NODE.md) and [local architecture](docs/LOCAL_ARCHITECTURE.md) for its trust and expansion model. Runtime data, keys, credentials and agent connection configs must remain outside version control.
