"""The 14 data-quality controls as pure functions: Inputs -> Result. Severity B = blocking, A = alert. C12-C14 need computed results
and are added by the pipeline stages that produce them."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from riskreport import calendar as cal
from riskreport import factors as F
from riskreport import pnl as pnl_mod


@dataclass
class Result:
    id: str
    name: str
    severity: str  # "B" or "A"
    ok: bool
    exceptions: list = field(default_factory=list)  # one short string per offending line

    @property
    def n(self):
        return len(self.exceptions)


def _res(cid, name, sev, exc):
    return Result(cid, name, sev, not exc, list(exc))


def _asof(inp):
    return inp.asof.isoformat()


def c01(inp):
    exc = [f"missing file: {m}" for m in inp.missing]
    if inp.folder.name != _asof(inp):
        exc.append(f"folder {inp.folder.name} does not match as-of {_asof(inp)}")
    for k in ("prices", "fx"):
        t = inp.tables.get(k)
        if t is not None and _asof(inp) not in set(t["date"]):
            exc.append(f"{k}: no row dated {_asof(inp)}")
    h = inp.tables.get("factor_history")
    if h is not None and h.index[-1] != _asof(inp):
        exc.append(f"factor_history ends {h.index[-1]}")
    return _res("C01", "Extraction present, internal date = as-of", "B", exc)


def c02(inp):
    return _res("C02", "Schema: columns, types, bounds", "B", [f"{s}.{c}: {k} ({v})" for s, c, k, v in inp.schema_errors])


def c03(inp):
    exc = []
    for k in ("positions_fo", "positions_bo"):
        t = inp.tables.get(k)
        if t is not None:
            d = t[t.duplicated(["book", "instrument"], keep=False)]
            exc += [f"{k}: {r.book}/{r.instrument}" for r in d.drop_duplicates(["book", "instrument"]).itertuples()]
    return _res("C03", "Duplicate (book, instrument)", "B", exc)


def c04(inp):
    st, exc = inp.tables.get("statics"), []
    if st is not None:
        known = set(st["instrument"])
        for k in ("positions_fo", "positions_bo"):
            t = inp.tables.get(k)
            if t is not None:
                exc += [f"{k}: {i}" for i in sorted(set(t["instrument"]) - known)]
    return _res("C04", "Position without static data", "B", exc)


def _price_series(inp):
    """instrument -> price rows ordered by date, only dates up to as-of."""
    p = inp.tables.get("prices")
    return {} if p is None else {i: g.sort_values("date") for i, g in p[p["date"] <= _asof(inp)].groupby("instrument")}


def _priced(inp):
    st, fo = inp.tables.get("statics"), inp.tables.get("positions_fo")
    if st is None or fo is None:
        return []
    return sorted(set(fo["instrument"]) & set(st[st["type"].isin(["EQUITY", "FUTURE"])]["instrument"]))


def c05(inp):
    """Missing price at as-of. One day missing: alert (T-1 used). More than one day, or no price at all: blocking."""
    ser, exc, blocking = _price_series(inp), [], False
    days = [d.isoformat() for d in cal.business_days(inp.asof, 2)]
    for i in _priced(inp):
        have = set(ser[i]["date"]) if i in ser else set()
        if days[-1] not in have:
            gap = days[-2] not in have
            exc.append(f"{i}: no price at {days[-1]}" + (" and none at T-1" if gap else " (T-1 used)"))
            blocking |= gap
    return _res("C05", "Missing price (T-1 used); more than one day is blocking", "B" if blocking else "A", exc)


def c06(inp):
    n, ser, exc = inp.cfg["controls"]["stale_days"], _price_series(inp), []
    for i in _priced(inp):
        v = ser[i]["price"].to_numpy() if i in ser else np.array([])
        if len(v) >= n and np.all(v[-n:] == v[-1]):
            exc.append(f"{i}: price unchanged for {n}+ observations")
    return _res("C06", "Stale price (unchanged >= 3 days)", "A", exc)


def _ewma_var(x, lam):
    v = x[0] ** 2
    for r in x[1:]:
        v = lam * v + (1 - lam) * r**2
    return v


def c07(inp):
    """Jump: |move at as-of| > k x EWMA vol estimated up to T-1. The price file overrides the history for equities at as-of."""
    h, c = inp.tables.get("factor_history"), inp.cfg["controls"]
    if h is None or len(h) < 30:
        return _res("C07", "Jump > 6 x EWMA vol", "A", [])
    hist = h.copy()
    ser, st = _price_series(inp), inp.tables.get("statics")
    if st is not None:
        for r in st[st["type"] == "EQUITY"].itertuples():
            if r.instrument in ser and _asof(inp) in set(ser[r.instrument]["date"]) and r.factor in hist:
                px = ser[r.instrument].set_index("date")["price"][_asof(inp)]
                if px > 0:  # a non-positive price is C02's business
                    hist.loc[_asof(inp), r.factor] = px
    exc = []
    for f in hist.columns:
        k = F.kind(f)
        x = np.log(hist[f]).diff().dropna() if k == "logret" else hist[f].diff().dropna()
        if k == "bp":
            x = x * 100
        past, last = x.to_numpy()[:-1], x.to_numpy()[-1]
        s = np.sqrt(_ewma_var(past, c["ewma_lambda"]))
        if s > 0 and abs(last) > c["jump_sigmas"] * s:
            exc.append(f"{f}: move {last / s:+.1f} x EWMA vol")
    return _res("C07", "Jump > 6 x EWMA vol", "A", exc)


def c08(inp):
    fo, bo, st = inp.tables.get("positions_fo"), inp.tables.get("positions_bo"), inp.tables.get("statics")
    if fo is None or bo is None or st is None:
        return _res("C08", "FO / BO reconciliation", "A", [])
    key = ["book", "instrument"]
    m = fo.drop_duplicates(key).merge(bo.drop_duplicates(key), on=key, how="outer", suffixes=("_fo", "_bo"), indicator=True)
    m = m.merge(st[["instrument", "type", "ccy"]], on="instrument", how="left")
    fx = inp.tables.get("fx")
    last = {} if fx is None else fx[fx["date"] == _asof(inp)].set_index("pair")["rate"].to_dict()
    tol, exc = inp.cfg["controls"]["nominal_tol_eur"], []
    for r in m.to_dict("records"):
        name = f"{r['book']}/{r['instrument']}"
        if r["_merge"] != "both":
            exc.append(f"{name}: present on one side only")
            continue
        d = abs(r["quantity_fo"] - r["quantity_bo"])
        if r["type"] in ("BOND", "FXCASH"):  # amounts: tolerance in EUR
            rate = last.get("EUR" + r["ccy"], 1.0) if r["type"] == "FXCASH" else 1.0
            if d / rate > tol:
                exc.append(f"{name}: amount gap {d:,.0f}")
        elif d > 0:
            exc.append(f"{name}: quantity FO {r['quantity_fo']:,.0f} vs BO {r['quantity_bo']:,.0f}")
    return _res("C08", "FO / BO reconciliation (exact quantity, nominal within 1,000 EUR)", "A", exc)


def c09(inp):
    st, fx, fo = inp.tables.get("statics"), inp.tables.get("fx"), inp.tables.get("positions_fo")
    if st is None or fx is None or fo is None:
        return _res("C09", "Missing FX rate", "B", [])
    need = sorted({"EUR" + c for c in st[st["instrument"].isin(fo["instrument"])]["ccy"] if c != "EUR"})
    prev = cal.previous(inp.asof).isoformat()
    exc = [f"{p}: no rate at {d}" for p in need for d in (prev, _asof(inp)) if not ((fx["pair"] == p) & (fx["date"] == d)).any()]
    return _res("C09", "Missing FX rate", "B", exc)


def c10(inp):
    h, n = inp.tables.get("factor_history"), inp.cfg["run"]["n_scenarios"]
    if h is None:
        return _res("C10", "History complete: scenarios without gaps", "B", [])
    exc = []
    if len(h) < n + 1:
        exc.append(f"{len(h)} rows, {n + 1} needed")
    if h.isna().any().any():
        exc.append("NaN in history")
    tail = list(h.index[-(n + 1):])
    expect = [d.isoformat() for d in cal.business_days(inp.asof, len(tail))]
    if tail != expect:
        exc.append(f"calendar gaps in last {len(tail)} dates: {sorted(set(expect) - set(tail))[:5]}")
    return _res("C10", "History complete: 500 scenarios without gaps", "B", exc)


def c11(inp):
    st, h, c = inp.tables.get("statics"), inp.tables.get("factor_history"), inp.cfg["controls"]
    if st is None or h is None:
        return _res("C11", "Option inputs plausible", "A", [])
    exc = []
    for r in st[st["type"] == "OPTION"].itertuples():
        iv = h[r.iv].iloc[-1] if r.iv in h else np.nan
        if not (c["vol_min"] <= iv <= c["vol_max"]):
            exc.append(f"{r.instrument}: implied vol {iv:.3f} outside [{c['vol_min']}, {c['vol_max']}]")
        if pd.to_datetime(r.expiry).date() <= inp.asof:
            exc.append(f"{r.instrument}: expiry {r.expiry} not after as-of")
    return _res("C11", "Option inputs plausible (vol in [1%, 300%], T > 0)", "A", exc)


INPUT_CONTROLS = [c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11]


def run_input_controls(inp):
    return [c(inp) for c in INPUT_CONTROLS]


def _explain_ctl(cid, name, col, desks, cfg):
    thr = pnl_mod.threshold(desks["pnl_fo" if col == "unexplained" else "pnl_hypo"], cfg)
    exc = [f"{d}: {col} {r[col]:,.0f} EUR (threshold {thr[d]:,.0f})" for d, r in desks.iterrows() if abs(r[col]) > thr[d]]
    return _res(cid, name, "A", exc)


def c12(desks, cfg):
    """FO P&L against the explained P&L, per desk: |FO - explained| <= max(5% of |FO P&L|, 10,000 EUR)."""
    return _explain_ctl("C12", "P&L explain: FO gap within tolerance", "unexplained", desks, cfg)


def c13(desks, cfg):
    """The explain model against our own full revaluation: |hypothetical - explained| <= max(5% of |hypothetical|, 10,000 EUR)."""
    return _explain_ctl("C13", "P&L explain: model residual within tolerance", "model_residual", desks, cfg)
