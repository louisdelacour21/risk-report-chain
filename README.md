# risk-report-chain

A daily market-risk reporting chain: CSV extractions in, a controlled Excel report out (P&L explain, historical VaR 99% / ES 97.5% with full revaluation, limits, 14 data-quality controls), with a validation status, a full audit trail and an exact replay.

**All data is synthetic.** The chain is a self-review, not an independent validation (see [methodology](docs/methodologie.md)).

## What it does
1. Ingests 8 CSV extractions (strict schemas, mixed CSV dialects) for 3 desks and about 52 positions.
2. Runs controls C01-C11 on the inputs, then computes hypothetical P&L, the explain by factor, VaR/ES and limit usage.
3. Runs C12-C13 on the P&L explain, writes an 8-sheet workbook, then re-reads it (C14) to check it matches the computed numbers.
4. Sets a status: `VALIDATED` (exit 0), `WITH_RESERVATIONS` (1), `NOT_VALIDATED` (2, the workbook is still produced with a red banner), `CRASH` (3).
5. Archives inputs, outputs, SHA-256 manifest and a JSON Lines journal; `rerun` replays a run and compares every number at 1e-9.

## Quick start
```bash
pip install -e ".[dev]"
python -m riskreport.cli generate-demo --date 2026-10-30
python -m riskreport.cli run --date 2026-10-30
python -m riskreport.cli rerun runs/2026-10-30
```
Inject defects with `generate-demo --defects defects/demo.toml`. A run takes about 10-20 s on a laptop. `scheduler/install_task.ps1` registers a weekday 07:30 Windows task.

## Benchmark with known truth
For each of 200 seeds, one clean day and one day per injected defect. Detection = the expected status or worse; false alarm = clean day not `VALIDATED`. Wilson 95% intervals.

| Case | Hits / 200 | 95% interval |
|------|-----------|--------------|
| missing price, stale price, qty break, jump 9 sigma, P&L gap | 200 each | 98.1-100% |
| duplicate, missing FX (blocking) | 200 each | 98.1-100% |
| limit breach (VaR, DV01) reported as BREACH without changing status | 197 each | 95.7-99.5% |
| **False alarms on clean days** | **3** | **0.5-4.3%** |

The 3 false alarms (seeds 41, 88, 190) are all control C07 (jump above 6 EWMA volatilities) firing on random synthetic noise, about 1.5% of days. The 3 missed limit cases are, most likely, the same seeds (the status was not `VALIDATED`); I did not check this seed by seed.

Limits of the benchmark: it injects only the defects the controls were designed for, so detection rates are an upper bound for unseen defects. Run it with `python -m bench.benchmark 200 out.json`.

## Layout
`src/riskreport` (ingest, controls, valuation, pnl, risk, report, pipeline, runlog, cli) · `synth` (synthetic market and defects) · `bench` · `scheduler` · `docs/methodologie.md` · `tests` (50 tests).

MIT licence.
