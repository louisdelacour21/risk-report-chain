# What would change with real data

The demo proves the mechanics. Here is what I would have to learn from a real desk before trusting any of it.

## Assumptions that are synthetic
- Prices, positions and the 750-day history come from a random simulator. Real tails are heavier and move together in crises.
- The extractions are clean files with fixed names. Real feeds arrive late, partly, and with changing columns.
- The three desks have 52 positions. A real book has thousands, and the full revaluation would need caching and vectorisation by instrument.

## Questions I would ask the desk
1. Which price is "the" close for each instrument, and who owns it?
2. Is the front-office P&L clean or hypothetical, and how are fees and carry treated? C12 compares like with like only if this is known.
3. What does a "stale" price mean per asset class (a bond can legitimately not trade for three days)?
4. Which limits are hard and which are indicative? A breach is reported here but triggers nothing.
5. What is the cut-off time, and what happens to a report that is late?

## What the chain does not cover
- Intraday risk, stressed VaR, multi-day horizons, netting, collateral, credit and liquidity risk.
- Independent validation: C01-C14 are the chain checking itself.
- Access control, segregation of duties and change management around the config file (it is hashed, not protected).
- Backtest: the one in the workbook holds today's book fixed (a hypothetical backtest). A production backtest compares each day's VaR with the next day's actual and hypothetical P&L of the book as it was.

## Thresholds
Every threshold lives in `config/default.toml` and is hashed into each run. The C07 jump threshold was examined on simulated data (see `bench/c07_calibration.json` and the README), and a real feed would need its own calibration.
