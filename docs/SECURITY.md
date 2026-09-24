# LogChain Security Notes

## Credentials

### Compromised Keys (Legacy Repository)
The original GitHub repository contained the following COMPROMISED credentials:
- Private key `0x9c7bf0754e9b13d38d2b71a69da799f76545991b97918ae1e000f400437d51b2`
- Account `0x8b629ce3BB085B061D95C7f0d14d2BF63ECbA758`
- Hard-coded IP `10.117.95.210`

**These are now public knowledge. NEVER use them for anything.**

Generate fresh credentials:
```bash
python scripts/preflight_check.py --gen-key
```

### Environment Variables
All secrets are loaded from `.env`:
```
BLOCKCHAIN_PRIVATE_KEY=   # NEW key only
BLOCKCHAIN_ACCOUNT=       # NEW account
FLASK_SECRET_KEY=         # generate: python -c "import secrets; print(secrets.token_hex(32))"
MONGODB_URI=              # default local OK
```

## Dashboard Security
- Security headers added (X-Frame-Options, X-Content-Type-Options)
- All state-changing operations use POST
- Templates use `markupsafe.escape()` equivalent (Jinja2 auto-escaping)
- Debug mode defaults to `false`
- Flask secret loaded from environment

## Blockchain Security
- `onlyWriter` modifier on all write functions
- Append-only: no batch overwrites
- Owner manages writer list
- No sensitive log content stored on-chain (only hashes/commitments)

## .gitignore
Critical secrets excluded:
- `.env`
- `*.key`, `*.pem`
- `keystore/`, `node1_data/`, `node2_data/`
- `password.txt`, `jwtsecret`
- `*.log`

## Correct Security Claims
Do NOT claim that blockchain makes log tampering impossible.

**Correct:** "A privileged attacker may modify or delete cloud-side logs,
but the original cryptographic commitment remains independently anchored
on the separate integrity ledger, so later verification can detect changes."

**The system is TAMPER-EVIDENT, not TAMPER-PROOF.**
