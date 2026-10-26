# GenLayer Parametric Payout

A GenLayer Intelligent Contract for **web-verified parametric payouts**: pay a policy holder when a real-world number read from a web page crosses a threshold (flight delay minutes, rainfall, price floor, uptime percentage, etc.).

## How it works

A policy says: *"Read `<metric>` from `<url>`. If it is `>=` (or `<=`) `<threshold>`, pay `<amount>` to the holder."*

1. The **leader** validator fetches the page and asks an LLM to extract **one integer** (or report `found: false`).
2. Each **validator** independently repeats the fetch + extraction.
3. A validator accepts the leader's result only if **all** are true:
   - both found the metric, or both did not;
   - the two values differ by at most the policy's `tolerance`;
   - both values fall on the **same side of the threshold**.
4. The contract then applies a plain deterministic rule (`decide`) to the agreed value. **The LLM never decides the payout.**

### Why this equivalence rule

| Situation | `strict_eq` | free-text comparison | This contract |
|---|---|---|---|
| Page says 40, validator reads 38 (threshold 30, tol 5) | rejects (needless failure) | unpredictable | accepts |
| Leader 31, validator 29 (threshold 30, tol 5) | rejects | may accept | **rejects**: they disagree on whether to pay |
| Metric not on page | n/a | LLM may guess | `UNRESOLVED`, never a guess |

Tolerance absorbs harmless drift (rounding, cache differences). The same-side rule guarantees tolerance can never flip a payout decision.

## State design

| Field | Type | Purpose |
|---|---|---|
| `policies` | `TreeMap[str, str]` | policy_id -> JSON record (holder, url, metric, comparator, threshold, tolerance, amount, status, counters) |
| `check_logs` | `TreeMap[str, str]` | policy_id -> JSON list of every check (outcome, value, reason) |
| `policy_ids` | `DynArray[str]` | enumeration of policies |
| `total_paid` | `u256` | cumulative payouts recorded |

Policy lifecycle: `ACTIVE -> PAID` (trigger met) or `ACTIVE -> EXPIRED` (all checks used without a trigger). `PAID` and `EXPIRED` are terminal, so a policy cannot be claimed twice.

Per-check outcomes: `TRIGGERED`, `NOT_TRIGGERED`, `UNRESOLVED` (source unreachable, metric absent, or unusable LLM output). Every check consumes one of the policy's `max_checks` (1-5), so attempts are bounded.

## Methods

| Method | Type | Notes |
|---|---|---|
| `create_policy(policy_id, source_url, metric_prompt, comparator, threshold, tolerance, payout_amount, max_checks)` | write | comparator is `GTE` or `LTE`; integers only; creator becomes holder |
| `check_policy(policy_id)` | write | holder only; runs the consensus check; returns the outcome |
| `get_policy(policy_id)` | view | JSON |
| `get_check_log(policy_id)` | view | JSON list |
| `get_policy_ids()` | view | JSON list |
| `get_total_paid()` | view | integer |

## Safety properties

- Only the holder can run checks (no griefing by burning someone's attempts).
- Page text is treated as untrusted; the prompt tells the model to ignore instructions inside it.
- Malformed, boolean, non-finite or missing numbers become `found: false`.
- The leader's result is type-checked by validators before comparison.
- A rejected check changes no state.

## Settlement

Payouts are recorded in contract state (`status = PAID`, `total_paid`). Token or native transfers are intentionally left as a plug-in point in `_settle`.

## Local tests

```bash
python3 -m unittest discover -s tests -v
```

26 tests cover creation validation, every outcome, the double-claim lock, access control, expiry, and each validator-equivalence case. They run against a small SDK stub (`tests/genlayer_stub.py`), which checks the contract logic but is **not** a consensus simulator.

## Live Studio results

Deployed on GenLayer Studio and run through full consensus.

**Contract:** [0x3a3627505a5839402A6d8CE7C2499Ad1854d705b](https://explorer-studio.genlayer.com/address/0x3a3627505a5839402A6d8CE7C2499Ad1854d705b)

All three policies below were created and checked on this one contract, using the Eiffel Tower Wikipedia page (`https://en.wikipedia.org/wiki/Eiffel_Tower`) and `example.com`.

| Scenario | Policy ID | Rule | Validators read | Outcome | Final status |
|---|---|---|---|---|---|
| Triggered | `eiffel-1` | height in metres `GTE 300`, tolerance 10 | 330 | `TRIGGERED` | `PAID` |
| Not triggered | `eiffel-2` | height in metres `GTE 500`, tolerance 10 | 330 | `NOT_TRIGGERED` | `ACTIVE` |
| Unresolved | `missing-1` | flight AB123 delay `GTE 30`, source `example.com` | metric not on page | `UNRESOLVED` | `ACTIVE` (1 check used) |

Reproduce with `create_policy` then `check_policy` using the parameters in the table. Use `get_policy` and `get_check_log` to read results.

## Deploying

The first line of the contract pins the GenLayer runner version:

```
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

If Studio reports "Could not load contract schema", copy the current header from one of Studio's example contracts.

## Limitations

- Integer values only; pick units precise enough for your use case.
- Quality depends on the source page being stable and clearly stating the metric.
- Accounting-only settlement (see above).
