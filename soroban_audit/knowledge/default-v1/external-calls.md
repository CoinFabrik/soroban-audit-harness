# External Call and Integration Safety Investigation

Analyze cross-contract calls as trust-boundary transitions.

## Address and interface trust

- Determine the origin of every invoked address: immutable configuration, authenticated administration, derived deployment, registry lookup, user input, token parameter, router path, or callback.
- Validate association and allowlisting before invocation. A syntactically valid contract address is not evidence that it is the intended token, pool, oracle, bridge, or adapter.
- Check that returned values, result types, decimals, and error behavior match the assumptions made by the caller.

## Ordering and state

- Trace checks, internal state changes, external calls, and final persistence in exact order.
- Identify controls performed only after a user-controlled call and determine what the callee can accomplish before the check. Account for Soroban rollback rather than assuming EVM behavior.
- Check whether callbacks or nested authorized calls can observe or influence partially updated state, exhaust resources, or invoke another permitted entry point.

## Token behavior

- Inspect signed amount conversions, zero values, balance-delta assumptions, authorization, fee-on-transfer behavior, rebasing, callbacks, and tokens that return unexpected values or errors.
- Reconcile requested transfer amounts with actual balance changes when the protocol relies on exact receipt.
- Test identical input/output tokens and malicious token contracts when addresses are caller-controlled.

## Failure propagation

- Verify external failures cannot be silently replaced with zero/default/success values that corrupt control flow or accounting.
- Distinguish safe transaction rollback from liveness failures that let an attacker block other users or poison persistent queues.

## Investigation procedure

For each public path with an external call, identify the caller-controlled inputs, address provenance, pre-call validation, pre-call state, callee capabilities, return-value validation, post-call state, rollback behavior, resource-growth risk, and concrete impact.
