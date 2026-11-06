# Example post-mortem: a day the chain refuses to validate

Synthetic data. Reproduce with `python -m riskreport.cli showcase`, then open `docs/demo/bad.html` (or `bad.xlsx`).

## What happened
Three defects were injected into the 2026-10-30 extractions: a duplicated position line, a price that did not move for three days, and an equity P&L from the front office that does not match the positions.

## What the chain said
Status **NOT_VALIDATED** (exit code 2), red banner "do not circulate" on every sheet, and a notification mail with the same subject. The workbook is still produced, because a risk manager who sees nothing at 08:00 learns less than one who sees the numbers with a warning.

| Control | Severity | Finding | Consequence |
|---------|----------|---------|-------------|
| C03 | blocking | `positions_fo`: the line EQ_CASH/EQ4 appears twice | The position would be counted twice: status NOT_VALIDATED |
| C06 | alert | EQ5 price unchanged for 3+ observations | Possible stale feed |
| C12 | alert | EQUITY: front-office P&L minus explained P&L is 126,243 EUR (threshold 10,000) | The desk P&L cannot be explained by its sensitivities |

The VaR backtest, the limits and the VaR/ES numbers are still computed. Limit breaches and backtest results are results, not data-quality failures, so they never change the status.

## What a human does next
1. Read the three lines above. C03 and C12 point at the same desk (EQUITY), which is a hint that they are linked.
2. Ask the data owner for a corrected `positions_fo` extraction (a real desk would know whether the duplicate is a booking error or an export bug).
3. Re-run the chain. The first run is kept in `runs/2026-10-30`; the corrected one goes to `runs/2026-10-30_v2`. Nothing is overwritten, and `manifest.json` records the SHA-256 of both input sets, so the difference between the two runs is provable.
4. `riskreport rerun runs/2026-10-30_v2` replays the run from the archive and compares every number at relative 1e-9.

## What this example does not show
The chain only knows the defects its controls were written for. A defect nobody thought of passes silently (see the benchmark caveat in the README). Here the three defects are known because I injected them.
