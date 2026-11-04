# Validation record — 29 October 2026

## Executed successfully

- `python3 -m unittest discover -s tests/local -v`: **27 tests passed**, Python 3.12.
- `node --check localchain/static/app.js`: passed, Node 22.
- `bash -n scripts/start_local.sh`: passed.
- `python3 -m compileall -q localchain`: passed.
- `git diff --check`: passed.

Tests cover repeated modification/restoration, exact changed fields, nested data changes, deletion without false reorder cascades, duplication, unexpected records, reordering, unreadable files, restart persistence, outage recovery/outbox retry, immutable history guards, metadata deletion detection, evidence tampering, input validation and source isolation. HTTP handlers are exercised with in-memory request/response streams for authentication, sign-out, CSRF/Host checks, request limits, ingestion, export, CSP and static file access. Setup tests cover preservation of existing chain data, version checks, explicit peering and observer operation without signing keys.

## Not verified in this workspace

- Real Geth startup, Solidity compilation/deployment, transaction receipts and observer replication.
- Live HTTP/browser rendering, responsive visual QA and interactive browser tests.
- The previous cloud/MongoDB test suite (the old runtime is not used by this release).

The executor denies socket creation, cannot resolve external hosts and cannot access the Docker daemon. The bundled runtime dependency tool was also unavailable. These are environment limitations, not passing test results. The offline simulator is explicitly labeled and is never used as an automatic blockchain fallback.

## Verification provided for an unrestricted host

- `.github/workflows/local-integrity.yml` runs the core suite and a separate real Ethereum job: download pinned Geth → generate single validator → deploy Solidity V3 → lifecycle smoke test → start observer → compare all committed batches across nodes.
- `python -m localchain.setup smoke` performs the real-node lifecycle test locally after deployment.
- `bash scripts/start_local.sh` launches the real stack; `--simulate` launches the explicitly labeled offline workflow.

Do not interpret the existence of the CI workflow as a successful CI run. Check the actual run status before claiming the network has passed end-to-end verification.

## Account/source upgrade

The current local suite contains 39 passing Python tests, including isolated accounts,
password login, source token revocation, persistent identities, external file delivery,
automatic tamper/restoration detection, offline sources and the previous integrity regressions.
`node tests/local/check_ui.js` checks the signup → source → config → dashboard flow and
automatic change display with DOM stubs. JavaScript and launcher syntax checks pass.
These checks do not constitute browser rendering or real Ethereum validation.
