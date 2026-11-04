# Adding observer nodes without replacing your chain

Start with the default **one validator**. Do not run the old two-validator setup against this data directory. A second signer in genesis would change the chain and may stop progress if it is offline.

## Same computer: replicate to a second node

1. Start the primary node with `python -m localchain.setup start` (or the launcher).
2. Obtain its enode through IPC, not public HTTP:

   ```bash
   bin/geth attach --exec 'admin.nodeInfo.enode' runtime/node/geth.ipc
   ```

3. In another terminal, activate `.venv` and start an observer with the printed enode. Replace the enode's advertised IP with `127.0.0.1` if it is not a reachable loopback address:

   ```bash
   source .venv/bin/activate
   python -m localchain.setup observer \
     --enode 'enode://PUBLIC_NODE_ID@127.0.0.1:30303' \
     --observer-name observer1 --port 30304 --rpc-port 8546
   ```

4. Add `"http://127.0.0.1:8546"` to `peer_rpcs` in `runtime/chain.json`, then restart only the monitor. The primary validator and observer keep running. On the Network screen, check the peer connection and growing block height.
5. Confirm replication with `eth_getCode` at the same contract address and `getBatch` via `EthereumLedger` against the observer RPC. The dashboard's node health reports chain/genesis identity and block height; it does **not** claim independent cross-node voting on every log.

For additional observers choose distinct names and ports. Their static peer entry is persisted in a TOML file. They do not need the writer key, validator password, or validator keystore.

## Another machine on a private LAN

- Copy only `runtime/genesis.json` and the project code to that machine. Never copy validator/writer keys to an observer.
- Install the same pinned Geth binary. Create a separate runtime folder with the copied genesis.
- Use a reachable LAN IP in the primary enode and set `--netrestrict` to the actual private LAN CIDR on **both** primary and observer, for example `192.168.1.0/24`. Do not use that example unless it matches your LAN.
- Permit TCP/UDP 30303 (or the chosen P2P port) only between approved machines using your firewall. `--nodiscover` and CIDR restriction reduce exposure but are not a cryptographic peer-identity allowlist.
- Keep observer RPC bound to loopback. Use an SSH tunnel if the monitoring machine needs it:

  ```bash
  ssh -N -L 8546:127.0.0.1:8546 user@OBSERVER_LAN_IP
  ```

- Supply the primary enode when starting the observer. Match genesis exactly, not just chain ID.

## Observer versus validator

An observer independently holds and validates the chain but does not seal blocks. Adding it does not change validator quorum. This is the supported expansion path in this project.

Promoting a new validator requires its own secured signer account and Clique votes from existing signers. Use IPC `clique.propose(address, true)` on authorized validators only after testing a membership plan. Do not add a second validator casually: two-signer Clique requires both online for sustained progress. Never modify genesis after deployment to add a validator; that creates a different blockchain.

## Upstream references

- https://geth.ethereum.org/docs/fundamentals/private-network
- https://geth.ethereum.org/docs/fundamentals/peer-to-peer
- https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-clique

These are reference documentation; the provided launcher deliberately pins the older Clique-capable Geth release rather than assuming current Geth can seal this network.
