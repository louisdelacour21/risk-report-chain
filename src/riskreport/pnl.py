"""Hypothetical P&L (today's book, T-1 -> T market, one calendar step of ageing), P&L explain by risk factor, and the gap to the FO P&L.

Explain per position (greeks taken at the T-1 state, so the explain is a genuine start-of-day attribution):
  delta*dS + 1/2 gamma*dS^2 + vega*dIV + theta*dt  (options, equities, futures)   |   -dv01*d(yield, bp) + theta*dt (bonds)   |   FX effect (cash)
Unexplained = PnL_FO - PnL_explain. Cross terms and higher orders (O(dS^3), gamma-vega, ...) stay in it by construction."""
import numpy as np

from riskreport import valuation as V
from riskreport.factors import kind

COLS = ["desk", "book", "instrument", "type"]


def hypothetical(book, mk, cfg):
    """Per-position hypothetical P&L in EUR and its explain components."""
    dt = (mk.asof - mk.prev).days / V.DAYS
    v1 = V.value(book, mk.lev, mk.fx, mk.asof, 0.0, cfg)[0]
    v0 = V.value(book, mk.lev_prev, mk.fx_prev, mk.asof, -dt, cfg)[0]
    s = V.sensitivities(book, mk.lev_prev, mk.fx_prev, mk.asof, -dt, cfg)
    dS = np.array([mk.lev[f] - mk.lev_prev[f] if kind(f) == "logret" else 0.0 for f in book.factor])
    dIV = np.array([mk.lev[i] - mk.lev_prev[i] if isinstance(i, str) else 0.0 for i in book.iv.where(book.iv.notna(), None)])
    dy = np.array([(mk.lev[f] - mk.lev_prev[f]) * 100 if t == "BOND" else 0.0 for f, t in zip(book.factor, book.type)])  # bp (levels in %)
    is_fx = (book.type == "FXCASH").to_numpy()
    out = book[COLS].copy()
    out["pnl_hypo"] = v1 - v0
    out["delta"] = s.delta * dS
    out["gamma"] = 0.5 * s.gamma * dS**2
    out["vega"] = s.vega * dIV
    out["theta"] = s.theta * dt
    out["rates"] = -s.dv01 * dy
    out["fx"] = np.where(is_fx, v1 - v0, 0.0)  # exact for cash: q (1/fx_T - 1/fx_T-1)
    out["explained"] = out[["delta", "gamma", "vega", "theta", "rates", "fx"]].sum(axis=1)
    return out


def by_desk(pos, fo):
    """pos: per-position frame from `hypothetical`; fo: positions' FO P&L (desk, book, instrument, pnl)."""
    m = pos.merge(fo.drop_duplicates(["book", "instrument"])[["book", "instrument", "pnl"]].rename(columns={"pnl": "pnl_fo"}),
                  on=["book", "instrument"], how="left")
    m["pnl_fo"] = m.pnl_fo.fillna(0.0)
    g = m.groupby("desk")[["pnl_fo", "pnl_hypo", "delta", "gamma", "vega", "theta", "rates", "fx", "explained"]].sum()
    g["unexplained"] = g.pnl_fo - g.explained
    g["fo_vs_hypo"] = g.pnl_fo - g.pnl_hypo
    g["model_residual"] = g.pnl_hypo - g.explained
    return g.reindex(["EQUITY", "RATES", "FX"]).fillna(0.0)


def threshold(pnl, cfg):
    c = cfg["controls"]
    return np.maximum(c["explain_rel"] * np.abs(pnl), c["explain_abs_eur"])
