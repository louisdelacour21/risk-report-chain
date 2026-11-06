"""Static HTML view of a report workbook (one self-contained file, no script needed), so the report can be read without Excel."""
import html
from pathlib import Path

import openpyxl

CELL = {"OK": "ok", "PASS": "ok", "ALERT": "warn", "BREACH": "bad", "FAIL": "bad", "NO METRIC": "bad", "GREEN": "ok", "YELLOW": "warn", "RED": "bad"}
CSS = """
:root{--bg:#fff;--fg:#1b1f23;--mut:#586069;--line:#d0d7de;--head:#37474F;--ok:#C8E6C9;--warn:#FFE0B2;--bad:#FFCDD2}
@media(prefers-color-scheme:dark){:root{--bg:#14181c;--fg:#e6e9ec;--mut:#9aa5b1;--line:#2d343b;--head:#37474F;--ok:#1f4a2a;--warn:#5a3d12;--bad:#5c1f1f}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}
.banner{padding:14px 16px;color:#fff;font-weight:700;font-size:18px;border-radius:4px}
h2{font-size:16px;margin:28px 0 8px}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{background:var(--head);color:#fff;text-align:left;padding:5px 8px}
td{border-bottom:1px solid var(--line);padding:4px 8px;white-space:nowrap}
td.ok{background:var(--ok)}td.warn{background:var(--warn)}td.bad{background:var(--bad)}
p.note{color:var(--mut);font-size:13px}
"""
BANNER = {"VALIDATED": "#2E7D32", "WITH_RESERVATIONS": "#E69F00", "NOT_VALIDATED": "#C62828"}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 10 or v == 0 else f"{v:.3f}"
    return str(v)


def _table(rows):
    if not rows:
        return "<p class=note>(empty)</p>"
    head, body = rows[0], rows[1:]
    out = ["<div class=wrap><table><tr>" + "".join(f"<th>{html.escape(_fmt(c))}</th>" for c in head) + "</tr>"]
    for r in body:
        out.append("<tr>" + "".join(f"<td class='{CELL.get(str(c), '')}'>{html.escape(_fmt(c))}</td>" for c in r) + "</tr>")
    return "".join(out) + "</table></div>"


def render(xlsx, out):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    s = wb["Summary"]
    status = s["B3"].value
    parts = [f"<div class=banner style='background:{BANNER.get(status, '#C62828')}'>{html.escape(str(s['A1'].value))}</div>"]
    lines = [r[0] for r in s.iter_rows(min_row=6, max_col=1, values_only=True)]
    block = []
    for v in lines:  # commentary lines come first, then a blank row, then the desk table
        if v is None:
            break
        block.append(v)
    parts.append("<h2>Commentary</h2>" + "".join(f"<p>{html.escape(str(x))}</p>" for x in block))
    for name in wb.sheetnames[0:]:
        rows = [list(r) for r in wb[name].iter_rows(values_only=True)]
        if name == "Summary":
            rows = [r for r in rows[6 + len(block):] if any(c is not None for c in r)]
        else:
            rows = [r for r in rows if any(c is not None for c in r)]
        parts.append(f"<h2>{html.escape(name)}</h2>" + _table(rows))
    page = (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Risk report {html.escape(str(status))}</title><style>{CSS}</style></head><body><main>{''.join(parts)}"
            "<p class=note>Synthetic data. Static view of the Excel workbook produced by risk-report-chain.</p></main></body></html>")
    Path(out).write_text(page, encoding="utf-8")
    return Path(out)
