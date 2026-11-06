"""Excel workbook (XlsxWriter, 8 sheets) with template-based commentary, and the C14 re-read check (openpyxl)."""
import json
from pathlib import Path

import numpy as np
import openpyxl
import xlsxwriter

from riskreport import controls as C

SHEETS = ["Summary", "PnL_Explain", "VaR_ES", "Sensitivities", "Limits", "Quality_Controls", "DQ_Exceptions", "Journal"]
BANNER = {"VALIDATED": "VALIDATED", "WITH_RESERVATIONS": "VALIDATED WITH RESERVATIONS - see Quality_Controls",
          "NOT_VALIDATED": "NOT VALIDATED - do not circulate"}
COLOR = {"VALIDATED": "#2E7D32", "WITH_RESERVATIONS": "#E69F00", "NOT_VALIDATED": "#C62828"}
ST_COLOR = {"OK": "#C8E6C9", "ALERT": "#FFE0B2", "BREACH": "#FFCDD2", "NO METRIC": "#FFCDD2"}
VAR_CELL, ES_CELL = "B24", "B25"  # fixed cells read back by C14


def commentary(run):
    """Template sentences built from the numbers. No model, no free text."""
    if not run.computed:
        return ["Numbers not computed: blocking data-quality failure (see Quality_Controls)."]
    d, r = run.desks, run.res
    out = [f"Total P&L (FO) {d.pnl_fo.sum():,.0f} EUR; explained {d.explained.sum():,.0f} EUR; unexplained {d.unexplained.sum():,.0f} EUR.",
           f"VaR 99% {r['var']:,.0f} EUR, ES 97.5% {r['es']:,.0f} EUR (500 historical scenarios, full revaluation, 1 business day)."]
    top = r["desk"].ES975_contribution.idxmax()
    out.append(f"Largest ES contributor: {top} ({r['desk'].ES975_contribution[top]:,.0f} EUR, "
               f"{r['desk'].ES975_contribution[top] / r['es']:.0%} of ES).")
    b = r["backtest"]
    out.append(f"VaR backtest: {b['exceptions']} exceptions in {b['days']} days (expected {b['expected']:.1f}), "
               f"Kupiec p = {b['kupiec_p']:.2f}, Basel zone {b['zone']}.")
    bad = run.limits[run.limits.status != "OK"]
    out.append("All limits OK." if bad.empty else "Limits: " + "; ".join(f"{x.desk} {x.metric} {x.status} ({x.usage:.0%})" for x in bad.itertuples()) + ".")
    fails = [c for c in run.controls if not c.ok]
    out.append("All data-quality controls passed." if not fails else "Controls failed: " + ", ".join(f"{c.id} ({c.n})" for c in fails) + ".")
    return out


def _table(ws, r0, header, rows, fmt):
    for j, h in enumerate(header):
        ws.write(r0, j, h, fmt["h"])
    for i, row in enumerate(rows, r0 + 1):
        for j, v in enumerate(row):
            if isinstance(v, (float, np.floating)):
                ws.write_number(i, j, 0.0 if np.isnan(v) else float(v), fmt["n"])
            else:
                ws.write(i, j, str(v))
    return r0 + 1 + len(rows)


def write(run, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"risk_report_{run.asof.isoformat()}.xlsx"
    wb = xlsxwriter.Workbook(str(path))
    fmt = {"h": wb.add_format({"bold": True, "bg_color": "#37474F", "font_color": "white"}), "n": wb.add_format({"num_format": "#,##0.00"}),
           "t": wb.add_format({"bold": True, "font_size": 14}),
           "b": wb.add_format({"bold": True, "font_color": "white", "font_size": 13, "bg_color": COLOR[run.status]}),
           "p": wb.add_format({"num_format": "0.0%"})}
    ws = {n: wb.add_worksheet(n) for n in SHEETS}
    for w in ws.values():
        w.set_column(0, 0, 34)
        w.set_column(1, 12, 18)
    s = ws["Summary"]
    s.merge_range(0, 0, 0, 5, f"{BANNER[run.status]}  -  as of {run.asof.isoformat()}", fmt["b"])
    s.write(2, 0, "Status", fmt["t"])
    s.write(2, 1, run.status)
    s.write(3, 0, "Config SHA-256")
    s.write(3, 1, run.cfg_sha)
    lines = commentary(run)
    for i, line in enumerate(lines):
        s.write(5 + i, 0, line)
    if run.computed:
        d, r = run.desks, run.res
        _table(s, 5 + len(lines) + 1, ["Desk", "P&L FO", "VaR 99%", "ES 97.5%", "ES contribution"],
               [[k, d.pnl_fo[k], r["desk"].VAR99[k], r["desk"].ES975[k], r["desk"].ES975_contribution[k]] for k in d.index]
               + [["TOTAL", d.pnl_fo.sum(), r["var"], r["es"], r["es"]]], fmt)
        cols = ["pnl_fo", "pnl_hypo", "delta", "gamma", "vega", "theta", "rates", "fx", "explained", "unexplained", "model_residual"]
        _table(ws["PnL_Explain"], 0, ["Desk"] + cols, [[k] + [d.loc[k, c] for c in cols] for k in d.index], fmt)
        v = ws["VaR_ES"]
        v.write(0, 0, "Worst 20 scenario P&L (EUR)", fmt["h"])
        for j, k in enumerate(d.index, 1):
            v.write(0, j, f"{k} P&L", fmt["h"])
        for i, k in enumerate(np.argsort(r["scenario_pnl"])[:20], 1):
            v.write_number(i, 0, float(r["scenario_pnl"][k]), fmt["n"])
            for j, dk in enumerate(d.index, 1):
                v.write_number(i, j, float(r["desk_pnl"][dk][k]), fmt["n"])
        v.write(23, 0, "VaR 99%")
        v.write_number(23, 1, float(r["var"]), fmt["n"])
        v.write(24, 0, "ES 97.5%")
        v.write_number(24, 1, float(r["es"]), fmt["n"])
        b = r["backtest"]
        v.write(27, 0, "VaR backtest (book held fixed)", fmt["h"])
        for i, (k, val) in enumerate([("Days tested", b["days"]), ("Exceptions", b["exceptions"]), ("Expected", b["expected"]),
                                      ("Kupiec LR", b["kupiec_lr"]), ("Kupiec p-value", b["kupiec_p"]), ("Basel traffic light", b["zone"])], 28):
            v.write(i, 0, k)
            v.write(i, 1, val, fmt["n"] if isinstance(val, float) else None)
        g = run.expo.groupby(["desk", "factor"])[["delta_eur", "gamma_eur", "vega_eur", "dv01", "fx_eur"]].sum().reset_index()
        _table(ws["Sensitivities"], 0, ["Desk / factor", "Delta EUR", "Gamma EUR (1%)", "Vega EUR (1 pt)", "DV01 EUR", "FX EUR"],
               [[f"{x.desk} / {x.factor}", x.delta_eur, x.gamma_eur, x.vega_eur, x.dv01, x.fx_eur] for x in g.itertuples()], fmt)
        lim = ws["Limits"]
        for j, h in enumerate(["Limit", "Value", "Limit amount", "Usage", "Status"]):
            lim.write(0, j, h, fmt["h"])
        for i, x in enumerate(run.limits.itertuples(), 1):
            lim.write(i, 0, f"{x.desk} {x.metric}")
            lim.write_number(i, 1, 0.0 if x.value is None else float(x.value), fmt["n"])
            lim.write_number(i, 2, float(x.limit), fmt["n"])
            lim.write_number(i, 3, 0.0 if np.isnan(x.usage) else float(x.usage), fmt["p"])
            lim.write(i, 4, x.status, wb.add_format({"bg_color": ST_COLOR[x.status]}))
    _table(ws["Quality_Controls"], 0, ["Control", "Severity", "Result", "Exceptions"],
           [[f"{c.id} {c.name}", "blocking" if c.severity == "B" else "alert", "PASS" if c.ok else "FAIL", float(c.n)] for c in run.controls], fmt)
    _table(ws["DQ_Exceptions"], 0, ["Control", "Exception"], [[c.id, x] for c in run.controls for x in c.exceptions], fmt)
    ws["DQ_Exceptions"].set_column(1, 1, 90)
    _table(ws["Journal"], 0, ["Item", "Value"], [[k, json.dumps(v) if isinstance(v, dict) else v] for k, v in run.meta.items()], fmt)
    ws["Journal"].write(len(run.meta) + 2, 0, "Full journal: journal.jsonl in the archive folder.")
    wb.close()
    return path


def c14(run, path):
    """Re-reads the workbook that was just written and compares its key numbers with the computed ones."""
    exc = []
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
        if wb.sheetnames != SHEETS:
            exc.append(f"sheets {wb.sheetnames}")
        v = wb["VaR_ES"]
        for name, cell, ref in (("VaR", VAR_CELL, run.res["var"]), ("ES", ES_CELL, run.res["es"])):
            if v[cell].value is None or abs(v[cell].value - ref) > 1e-6 * max(1, abs(ref)):
                exc.append(f"{name} in workbook {v[cell].value} vs computed {ref}")
        e = wb["PnL_Explain"]
        tot = sum(e.cell(row=i, column=2).value for i in range(2, 2 + len(run.desks)))
        if abs(tot - run.desks.pnl_fo.sum()) > 0.01 * len(run.desks):
            exc.append(f"P&L FO in workbook {tot} vs computed {run.desks.pnl_fo.sum()}")
    except Exception as err:  # noqa: BLE001 - an unreadable file is itself the finding
        exc.append(f"cannot re-read workbook: {err}")
    return C.Result("C14", "Workbook re-read matches computed numbers", "B", not exc, exc)
