# Soroban Core Security Model

Apply Soroban's actual execution model before deciding that a candidate is exploitable or safe.

## Authorization

- Trace every `require_auth` and `require_auth_for_args` to the identity whose authorization is enforced. Do not assume an address argument is authorized merely because it is named `admin`, `user`, `sender`, or `owner`.
- Compare the authenticated identity with every address installed into privileged storage. Check initialization, role transfer, upgrades, pause controls, recovery, and configurable contract addresses.
- Inspect whether one address can occupy roles that are assumed to be independent.
- Account for authorization propagation across nested contract calls and distinguish the immediate invoker from the ultimately authorized principal.

## Atomicity and cross-contract execution

- Soroban contract invocation is atomic when a call fails. Do not report intermediate state corruption when the entire transaction rolls back.
- Still inspect checks performed after external calls: an attacker-controlled callee may consume resources, return adversarial values, invoke permitted callbacks, or violate assumptions before a later check.
- Establish whether external contract addresses are fixed, authenticated, allowlisted, derived from trusted state, or supplied by an untrusted caller.

## Storage and lifetime

- Identify whether security-critical values use instance, persistent, or temporary storage.
- Trace TTL extension on every live path, not just initialization. Test what happens when values expire independently or can be recreated.
- Look for unbounded vectors, maps, or per-user state placed in one ledger entry and for loops whose cost grows with attacker-controlled state.
- Treat expired replay markers, roles, nonces, price records, and configuration as state transitions with security consequences.

## Time and environment

- Verify units and normalization for ledger timestamps, ledger sequence numbers, TTLs, cooldowns, oracle timestamps, and retention periods.
- Check conversions between time units and integer widths and whether future, zero, stale, or off-grid timestamps are accepted.

## Token interactions

- Trace authorization, signed amount conversions, zero amounts, token address trust, and balance/accounting assumptions around every token client call.
- Distinguish raw token balances from internal accounting. Direct transfers can change the former without updating the latter.

## Evidence standard

For every candidate, cite the reachable entry point, effective authorization, relevant storage type and lifetime, complete call/state sequence, violated invariant, concrete impact, and Soroban-specific counterevidence.
