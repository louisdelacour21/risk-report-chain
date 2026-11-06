# Controls and the BCBS 239 principles

BCBS 239 ("Principles for effective risk data aggregation and risk reporting", Basel Committee, 2013) is the vocabulary banks use for the quality of risk data and reports. This table maps each part of the chain to the principle it is closest to. It is a reading aid, not a compliance claim: BCBS 239 applies to banks' governance and architecture, which a demo project cannot demonstrate.

| Part of the chain | Closest BCBS 239 principle |
|-------------------|----------------------------|
| C02 schema and bounds, C03 duplicates, C07 jumps, C11 option inputs | 3 Accuracy and integrity |
| C01 files and dates, C04 static data, C05 missing prices, C09 missing FX, C10 scenario history | 4 Completeness |
| Run at 07:30 on weekdays, `run_id` and timestamps in the journal | 5 Timeliness |
| C08 FO/BO reconciliation, C12-C13 P&L explain, C14 workbook re-read | 7 Accuracy (of the report) |
| Desks, limits, VaR and ES, sensitivities in one workbook | 8 Comprehensiveness |
| Status banner, template commentary, e-mail subject | 9 Clarity and usefulness |
| Weekday schedule | 10 Frequency |
| .eml notification, archive folder | 11 Distribution |
| Weekly demo workflow, benchmark with known truth | 12 Review (of the process, not an independent one) |

Backtest vocabulary: the traffic light is the 1996 Basel market-risk amendment for a 99% one-day VaR over 250 days (green up to 4 exceptions, yellow 5 to 9, red 10 or more); Kupiec's proportion-of-failures test is the standard likelihood-ratio test of the exception rate. The ES at 97.5% is the measure of the FRTB internal-model approach. The chain does not implement the FRTB capital rules.
