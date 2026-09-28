# Numeric Safety Investigation

Investigate numeric operations as protocol controls rather than isolated arithmetic expressions.

## Type boundaries

- Find `as` conversions, especially between `u128`, `i128`, `u64`, `u32`, `u8`, and collection indexes. Determine the reachable source range and whether truncation, wrapping, or sign changes can occur.
- Prefer evidence from the value's origin and all guards, not the cast alone. Confirm whether `TryFrom`, checked helpers, or upstream invariants make the conversion safe.
- Trace negative values through token amounts, fees, allowances, balances, liabilities, prices, square roots, and absolute-value operations.

## Precision and rounding

- Record the scale and unit of every operand before and after multiplication, division, exponentiation, and decimal conversion.
- Check division-before-multiplication, inconsistent scale factors, double conversion, hard-coded decimals, and multiplication overflow before division reduces the value.
- Determine whether each operation must round up or down to preserve the protocol invariant. Test boundary values around zero, one unit, one share, maximum fees, and maximum supported balances.
- Treat a positive input producing zero shares, zero output, zero repayment, or zero fee as a security-relevant boundary when value is still transferred or state is updated.

## Denominators and domains

- Prove denominators cannot be zero and ratios remain in their intended domain.
- Check basis-point, percentage, interest, collateral, utilization, amplification, oracle, and slippage parameters at initialization and every administrative setter.
- Test whether intermediate signed expressions can become negative even when stored inputs are unsigned.

## Investigation procedure

1. Identify attacker-controlled or economically variable inputs.
2. Write the mathematical invariant with units and intended rounding direction.
3. Follow the exact implementation and conversions.
4. Evaluate zero, one, boundary, maximum, and scale-mismatch cases.
5. Establish whether failure rolls back safely or commits an unfavorable transfer/accounting result.
6. Search sibling functions for inconsistent versions of the same formula.

Do not report harmless precision loss without a concrete reachable impact.
