# State-Machine and Representation-Consistency Investigation

Treat each contract as a state machine whose security depends on valid transitions and consistent representations.

## Enumerate transitions

- Identify lifecycle states for initialization, pause, queues, auctions, claims, disputes, withdrawals, upgrades, ownership transfer, messages, nonces, and replay markers.
- List which callers may enter, repeat, cancel, finalize, or reverse every transition and which time/ledger conditions apply.
- Test repeated calls, calls in the wrong order, skipped phases, completion more than once, recreation after expiration, and operations at exact boundaries.

## Aliasing and duplicate identities

- Test when the same address, asset, pool, identifier, or key appears in two roles that code assumes are independent: liquidated user and filler, sender and receiver, primary and secondary validator, debtor and liquidator, input and output asset.
- Check duplicate entries in vectors or batched inputs and whether one logical object is updated more than once or its result is overwritten/discarded.

## Cached versus persisted state

- Find flows holding multiple mutable in-memory copies of the same logical object or loading storage after an earlier in-memory update.
- Track which copy is saved last. Look for stale reads, lost updates, double application, and divergence between aggregate and per-user state.
- Include cross-contract state, lazy defaults, storage caches, and helper functions that load their own copy instead of receiving the caller's current state.

## Replay and lifetime

- Verify nonces, hashes, processed markers, and one-time permissions are unique, domain-separated, persisted for the required lifetime, and consumed atomically.
- Evaluate whether TTL expiry or cleanup makes a completed transition executable again.

## Required transition trace

For each candidate, show the pre-state, entry point and caller, guards, every in-memory and persisted representation touched, external calls, post-state, broken transition invariant, and counterevidence from rollback or later validation.
