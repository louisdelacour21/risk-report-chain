"""Historical VaR 99 % / ES 97.5 % by full revaluation, desk contributions, aggregated sensitivities and limit usage.

Scenario k applies the k-th historical one-day change of each factor to today's levels (log return for equities/fx, level change for yields in %
and implied vols, vol floored at `vol_min`) and revalues every position one business day later. Quantiles come from riskhub-engine."""
import numpy as np
import pandas as pd
from riskhub_engine import market

from riskreport import calendar as cal
from riskreport import valuation as V
from riskreport.factors import FACTORS, kind

DESKS = ["EQUITY", "RATES", "FX"]


def scenarios(hist, mk, cfg):
    """(lev, fx) dicts of arrays (n,), from the last n+1 history rows."""
    n = cfg["run"]["n_scenarios"]
    h = hist[FACTORS].iloc[-(n + 1):]
    lev = {}
    for f in FACTORS:
        x = h[f].to_numpy()
        d = np.log(x[1:] / x[:-1]) if kind(f) == "logret" else x[1:] - x[:-1]
        lev[f] = mk.lev[f] * np.exp(d) if kind(f) == "logret" else mk.lev[f] + d
        if kind(f) == "volpt":
            lev[f] = np.maximum(lev[f], cfg["controls"]["vol_min"])
    return lev, {p: lev[p] for p in ("EURUSD", "EURGBP", "EURJPY")}


def run(book, hist, mk, cfg):
    lev, fx = scenarios(hist, mk, cfg)
    age = (cal.next_(mk.asof) - mk.asof).days / V.DAYS
    base = V.value(book, mk.lev, mk.fx, mk.asof, 0.0, cfg)[0]
    pl = V.value(book, lev, fx, mk.asof, age, cfg) - base  # (n, positions)
    tot = pl.sum(axis=1)
    r = cfg["run"]
    var = market.historical(tot, r["var_conf"])
    es = market.historical(tot, r["es_conf"])
    k = int(np.ceil(len(tot) * (1 - r["es_conf"]) - 1e-9))
    worst = np.argsort(tot)[:k]  # the k scenarios that make up the ES tail
    desk_pl = {d: pl[:, (book.desk == d).to_numpy()].sum(axis=1) for d in DESKS}
    out = {"scenario_pnl": tot, "desk_pnl": desk_pl, "var": var["var"], "es_var": var["es"], "es": es["es"], "var_es": es["var"], "tail": worst}
    out["desk"] = pd.DataFrame({
        "VAR99": [market.historical(desk_pl[d], r["var_conf"])["var"] for d in DESKS],
        "ES975": [market.historical(desk_pl[d], r["es_conf"])["es"] for d in DESKS],
        "ES975_contribution": [-desk_pl[d][worst].mean() for d in DESKS]}, index=DESKS)  # additive: sums to the portfolio ES
    return out


def exposures(book, mk, cfg):
    s = V.sensitivities(book, mk.lev, mk.fx, mk.asof, 0.0, cfg)
    S = np.array([mk.lev[f] if t in ("EQUITY", "FUTURE", "OPTION") else 1.0 for f, t in zip(book.factor, book.type)])
    x = pd.DataFrame({"desk": book.desk, "factor": book.factor, "delta_eur": s.delta * S, "gamma_eur": s.gamma * S**2 * 0.01,
                      "vega_eur": s.vega * 0.01, "dv01": s.dv01, "fx_eur": np.where(book.type == "FXCASH", book.quantity / np.array(
                          [mk.fx.get(f, 1.0) for f in book.factor]), 0.0)})
    return x


def metrics(res, expo):
    """Desk and TOTAL metric table used by the limits: (desk, metric) -> value."""
    m = {}
    for d in DESKS:
        m[(d, "VAR99")], m[(d, "ES975")] = res["desk"].loc[d, "VAR99"], res["desk"].loc[d, "ES975"]
    m[("TOTAL", "VAR99")], m[("TOTAL", "ES975")] = res["var"], res["es"]
    m[("EQUITY", "DELTA_EUR")] = abs(expo[expo.desk == "EQUITY"].delta_eur.sum())
    m[("RATES", "DV01")] = abs(expo[expo.desk == "RATES"].dv01.sum())
    m[("FX", "FX_EXPOSURE")] = expo[expo.desk == "FX"].fx_eur.abs().sum()
    return m


def limits_status(m, limits, cfg):
    """One row per limit line. OK < warn_at, ALERT up to 100 %, BREACH above. A limit with no computed metric is reported, not dropped."""
    w = cfg["limits_status"]["warn_at"]
    rows = []
    for r in limits.itertuples():
        v = m.get((r.desk, r.metric))
        u = np.nan if v is None else v / r.limit
        st = "NO METRIC" if v is None else "BREACH" if u > 1 else "ALERT" if u >= w else "OK"
        rows.append({"desk": r.desk, "metric": r.metric, "value": v, "limit": r.limit, "usage": u, "status": st})
    return pd.DataFrame(rows)
