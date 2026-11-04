# Account and live-source setup

## Install the upgrade

Stop LogChain in its terminal with Ctrl+C. Extract this upgrade ZIP and run:

```bash
python3 ~/Downloads/LogChain-account-source-upgrade/apply_upgrade.py \
  --project ~/Downloads/LogChain-local
cd ~/Downloads/LogChain-local
bash scripts/start_local.sh
```

Open http://127.0.0.1:8080 and hard-refresh with Ctrl+Shift+R.
The updater backs up the changed source files, checks their versions before writing,
and leaves runtime data, account databases, keys and blockchain directories alone.
Do not apply the earlier live-monitor patch after this upgrade; it is included here.

## Create an account and connect your real application

1. Choose **Create account**. Enter your name, email and a password of at least 12 characters.
   Accounts are local; email is a login identifier, not a verified email or mail delivery feature.
2. Choose a project/application name and a connection method.
3. For an existing log file, enter its absolute path and select plain text, JSON Lines or
   a structured JSON array. The application keeps writing to its normal file.
4. Create the account. Download both the connection JSON and `logchain-agent.py`.
   The screen supplies a command with the exact downloaded config filename.
5. Run that command in the folder containing those two downloads and leave it running.
6. Open the dashboard. The source switches from waiting to connected. New records are
   anchored and verified automatically. No Verify now click is required.
7. Edit a complete log entry, leave it changed until it appears in the dashboard, then
   restore it. Both observations remain in the incident timeline.

Example (use the actual config name shown in the app):

```bash
cd ~/Downloads
python3 logchain-agent.py --config logchain-SOURCEID-TIMESTAMP.json
```

For a changed location, supply `--file /absolute/path/to/app.log`.
Keep the config and `logchain-SOURCEID.state.json` together. Do not discard the state file:
it preserves the timestamps used to identify plain-text lines across agent restarts.
Each config is source-specific; separate application streams need separate sources.
Downloaded configs include secrets. Passwords and source tokens are never written to console logs.

The dashboard scans automatically on a one-second schedule; the agent samples every two seconds.
These are schedules, not latency guarantees: blockchain confirmation and backlog add delay.
If the agent stops, external contents become unavailable after 15 seconds once the verifier
processes the source. Reconnection resumes scanning. A missing or malformed file is unavailable,
not an empty verified file. If the agent disconnects during an entire edit-and-restore cycle,
that unobserved change cannot be reconstructed later.

## Choose a format

- **Plain text**: one event per complete newline-terminated line. A partial final line is
  ignored until its newline arrives. Physical line numbers identify records. Appending works
  naturally; inserting/deleting lines can flag multiple shifted entries. This is expected.
- **JSON Lines**: one complete JSON value per line. Generic application records are wrapped
  as audit events; the original JSON is retained in `data`. Fully structured audit events
  keep their event IDs, timestamps, sequences and other fields.
- **Structured JSON array**: the whole file must be an array of audit event objects with
  stable IDs and increasing sequence numbers. This gives precise deletion/reordering tracking.

Structured event example:

```json
{
  "event_id": "login-001",
  "sequence": 1,
  "timestamp": "2026-11-04T12:00:00Z",
  "actor": "student-42",
  "action": "login",
  "message": "User signed in"
}
```

A new, valid event receives a first commitment. Later contents with the same ID are compared
against that commitment; restoring them never erases incident history. Unknown invalid records
are reported as untrusted rather than accepted as originals.

This version mirrors snapshots of small local files (under 900 KB, and under a 1 MB serialized
request, at most 10000 records; individual new messages must be at most 10000 characters).
Register a new source for a rotated file and retain the old evidence. Do not silently replace
or truncate an existing stream as normal rotation. Large production streams need a separate
segmented ingestion design rather than repeatedly shipping a full large log.

## Direct application API

Choose **Application API integration** if you can add an HTTP call in your backend.
The setup screen shows the URL, token and config. Send 1–100 structured events per request:

```text
POST http://127.0.0.1:8080/api/sources/SOURCE_ID/events
Authorization: Bearer SOURCE_TOKEN
Content-Type: application/json

{"events":[{"event_id":"login-001","sequence":1,"timestamp":"2026-11-04T12:00:00Z","actor":"user-42","action":"login","message":"User signed in"}]}
```

Keep sequence numbers increasing per source and IDs stable. Unchanged retries are safe.
API ingestion protects the copy received by LogChain. It cannot discover later changes
in your original project file; select the file agent for that requirement.
The snapshot `/sync` endpoint is restricted to file-agent sources.

## Accounts, reconnecting and existing data

Each account has an isolated evidence database and log directory, with a separate namespace
on the same private blockchain. Account sessions expire after 12 hours or a server restart.
A source token authorizes that one source only, never dashboard access or another account.
Passwords use salted scrypt hashes; signing in does not require the old administrator token.
There is no password reset or email delivery in this local version.

Under Connected sources, **New connection token** revokes the previous token and opens setup
again. Reconfigure the agent/application with the new config. When reconnecting a file agent,
select the original log path and format. Keep its state file in the same download folder.
You can connect more sources from this page.

Existing pre-account logs remain accessible through **Open an existing token workspace** on
the sign-in page, using runtime/admin.token. They are not silently assigned to a new account.
The existing writer account, contract and chain are retained. A shared writer lock serializes
transaction submission across workspaces.

The standard launcher opens the dashboard without a demo. To explicitly start the old demo:

```bash
bash scripts/start_local.sh --demo
```

Demo records belong to the existing token workspace. Your account uses its chosen source.
This version stays bound to loopback: both your application/agent and LogChain run on the
same computer. Forwarding from other machines needs a separate authenticated HTTPS setup.
Optional blockchain peer configuration continues to use the existing chain settings.

## Validation

39 Python tests cover authentication, workspace isolation, source token revocation, persistent
identity, agent delivery, automatic monitoring, tampering/restoration, missing files, and prior
integrity guarantees. JavaScript checks exercise the signup/source/config/dashboard flow and
automatic display updates using DOM stubs. Syntax checks cover the UI and launcher.
Real browser rendering and real Ethereum execution have not been verified in this restricted
session; the integration tests use the explicitly labeled simulation ledger and in-memory HTTP.

Run the checks from your project:

```bash
python3 -m unittest discover -s tests/local -v
node tests/local/check_ui.js
```
