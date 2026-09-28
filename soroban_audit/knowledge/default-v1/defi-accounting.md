# DeFi Accounting and Economic Manipulation Investigation

Model assets and claims across transaction sequences. A single-function review is insufficient for economic vulnerabilities.

## Core invariants

- Reconcile raw token balances, internal reserves, total assets, total liabilities, total shares, user shares, fees, rewards, collateral, and debt after every operation.
- Identify which quantities represent actual custody and which are cached accounting. Test unsolicited token transfers and donations that change custody without changing accounting.
- Confirm conservation: value entering, leaving, reserved, claimable, or charged as fees must be accounted exactly once.

## Share and first-participant attacks

- Analyze the empty and near-empty states for vaults, pools, backstops, reward systems, and markets.
- Test an attacker sequence of minimal initial deposit, direct donation or balance inflation, victim deposit, attacker withdrawal, and reinitialization after supply returns to zero.
- Verify positive deposits cannot mint zero shares and positive redemptions cannot burn claims for zero assets unless the caller explicitly accepts that outcome.
- Check whether share price can be manipulated by raw balances, donations, unaccrued interest, fee reserves, rounding direction, or stale totals.

## User protection and market manipulation

- Trace minimum output, maximum input, deadlines, belief prices, slippage, and price bounds from entry point to final transfer.
- Test transaction ordering, front-running, sandwiching, temporary liquidity, flash liquidity, and donation-based manipulation.
- Evaluate whether the attacker can profit or force victim loss after accounting for fees, rollback, locked capital, authorization, and Soroban resource limits.

## Debt, collateral, liquidation, and rewards

- Reconcile debt and collateral before and after borrow, repay, withdraw, liquidation, bad-debt coverage, auction fill, and self-interaction.
- Check accrual ordering and stale totals before limits or exchange rates are computed.
- Ensure rewards and fees cannot be claimed twice, discarded by duplicate identifiers, redirected, unlocked with negative values, or calculated from manipulable snapshots.

## Required attack narrative

For a candidate, provide the initial state, ordered attacker and victim transactions, state after each transaction, final extraction or loss, required capital/privilege, and strongest reason the sequence might fail.
