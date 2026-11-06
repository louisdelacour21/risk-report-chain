"""Prices and sensitivities, vectorised over scenarios. EUR throughout.

Conventions: fx[pair] = units of foreign currency per 1 EUR. Equities V = q*P; futures V = q*P*multiplier (exposure); options
V = q*multiplier*BS(S,K,T,sigma,r,q_div) with T in ACT/365; bonds are priced by discounting annual-coupon cash flows at the pillar yield
(coupons fall at maturity minus whole years); foreign cash V = amount / fx.
`age` is the time in years elapsed since the as-of date (negative for T-1), so every position ages with the calendar, exactly as in the
hypothetical P&L and in the VaR scenarios."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import ndtr

from riskreport import calendar as cal
from riskreport.factors import FX as FXPAIRS

DAYS = 365.0


@dataclass
class Mkt:
    asof: object
    prev: object
    lev_prev: dict
    lev: dict
    fx_prev: dict
    fx: dict
    stale_prices: list  # instruments valued with the T-1 price because T is missing


def build_book(inp):
    fo = inp.tables["positions_fo"].drop_duplicates(["book", "instrument"])
    return fo.merge(inp.tables["statics"].drop(columns=["desk"]), on="instrument", how="left").reset_index(drop=True)


def market(inp):
    """Factor levels at T-1 and T. History gives the base; the price and fx files override equities, futures and fx at both dates;
    an equity price missing at T falls back to T-1 (control C05 reports it)."""
    h = inp.tables["factor_history"]
    asof, prev = inp.asof, cal.previous(inp.asof)
    lev_prev, lev = h.iloc[-2].to_dict(), h.iloc[-1].to_dict()
    p = inp.tables["prices"].merge(inp.tables["statics"][["instrument", "factor", "type"]], on="instrument")
    stale = []
    for r in p.itertuples():
        if r.type == "EQUITY" or r.type == "FUTURE":
            if r.date == prev.isoformat():
                lev_prev[r.factor] = r.price
            elif r.date == asof.isoformat():
                lev[r.factor] = r.price
    have_t = set(p[p.date == asof.isoformat()].factor)
    for r in inp.tables["statics"][inp.tables["statics"].type.isin(["EQUITY", "FUTURE"])].itertuples():
        if r.factor not in have_t and r.instrument in set(inp.tables["positions_fo"].instrument):
            lev[r.factor] = lev_prev[r.factor]
            stale.append(r.instrument)
    fxd = inp.tables["fx"]
    fx_prev = {x: float(v) for x, v in fxd[fxd.date == prev.isoformat()].set_index("pair")["rate"].items()}
    fx = {x: float(v) for x, v in fxd[fxd.date == asof.isoformat()].set_index("pair")["rate"].items()}
    for x in FXPAIRS:  # missing rate: carried from the other date; C09 flags it
        fx.setdefault(x, fx_prev.get(x, lev[x]))
        fx_prev.setdefault(x, fx[x])
    return Mkt(asof, prev, lev_prev, lev, fx_prev, fx, stale)


def bs_vec(S, K, T, v, r, q, right):
    """Black-Scholes price, arrays broadcast; T <= 0 gives intrinsic value."""
    S, T, v = np.broadcast_arrays(np.asarray(S, float), np.asarray(T, float), np.asarray(v, float))
    Ts = np.maximum(T, 1e-12)
    sq = v * np.sqrt(Ts)
    d1 = (np.log(S / K) + (r - q + v * v / 2) * Ts) / sq
    d2 = d1 - sq
    call = S * np.exp(-q * Ts) * ndtr(d1) - K * np.exp(-r * Ts) * ndtr(d2)
    put = K * np.exp(-r * Ts) * ndtr(-d2) - S * np.exp(-q * Ts) * ndtr(-d1)
    out = call if right == "C" else put
    intr = np.maximum(S - K, 0) if right == "C" else np.maximum(K - S, 0)
    return np.where(T > 0, out, intr)


def bond_price(face, coupon, T, y):
    """Value of `face` nominal: sum of annual coupons at T, T-1, ... (> 0) plus redemption at T, discounted at yield y (decimal, annual)."""
    y = np.asarray(y, float)
    n = int(np.ceil(T - 1e-12))
    t = T - np.arange(n)
    pv = sum(coupon / 100 / (1 + y) ** tk for tk in t if tk > 0)
    return face * (pv + 1 / (1 + y) ** T)


def value(book, lev, fx, asof, age, cfg):
    """(n, n_positions) EUR values. lev: factor -> array (n,) or scalar; fx: pair -> array or scalar. `age` in years since as-of."""
    n = max([np.size(v) for v in list(lev.values()) + list(fx.values())] + [1])
    r, qd = cfg["valuation"]["r"], cfg["valuation"]["q"]
    out = np.zeros((n, len(book)))
    for j, p in enumerate(book.itertuples()):
        q = p.quantity
        if p.type == "EQUITY":
            out[:, j] = q * lev[p.factor]
        elif p.type == "FUTURE":
            out[:, j] = q * lev[p.factor] * p.multiplier
        elif p.type == "OPTION":
            T = (pd.to_datetime(p.expiry).date() - asof).days / DAYS - age
            out[:, j] = q * p.multiplier * bs_vec(lev[p.factor], p.strike, T, lev[p.iv], r, qd, p.right)
        elif p.type == "BOND":
            out[:, j] = bond_price(q, p.coupon, p.maturity_years - age, np.asarray(lev[p.factor]) / 100)
        elif p.type == "FXCASH":
            out[:, j] = q / fx[p.factor]
    return out


def point(book, lev, fx, asof, age, cfg):
    return value(book, lev, fx, asof, age, cfg)[0]


def sensitivities(book, lev, fx, asof, age, cfg):
    """Per-position sensitivities in EUR at one state: delta (EUR per unit of the factor), gamma, vega (per 1.00 of vol), theta (EUR per year),
    dv01 (EUR lost for +1 bp: V(y) - V(y+1bp)). Option greeks come from riskhub-engine's scalar Black-Scholes."""
    from riskhub_engine import options

    r, qd = cfg["valuation"]["r"], cfg["valuation"]["q"]
    cols = {k: np.zeros(len(book)) for k in ("delta", "gamma", "vega", "theta", "dv01", "fx_amount")}
    for j, p in enumerate(book.itertuples()):
        q = p.quantity
        if p.type == "EQUITY":
            cols["delta"][j] = q
        elif p.type == "FUTURE":
            cols["delta"][j] = q * p.multiplier
        elif p.type == "OPTION":
            T = (pd.to_datetime(p.expiry).date() - asof).days / DAYS - age
            g = options.bs(lev[p.factor], p.strike, T, lev[p.iv], r, qd, p.right)
            k = q * p.multiplier
            cols["delta"][j], cols["gamma"][j], cols["vega"][j], cols["theta"][j] = k * g["delta"], k * g["gamma"], k * g["vega"], k * g["theta"]
        elif p.type == "BOND":
            y, T = lev[p.factor] / 100, p.maturity_years - age
            cols["dv01"][j] = bond_price(q, p.coupon, T, y) - bond_price(q, p.coupon, T, y + 1e-4)
            cols["theta"][j] = (bond_price(q, p.coupon, T - 1 / DAYS, y) - bond_price(q, p.coupon, T, y)) * DAYS  # roll-down at constant yield
        elif p.type == "FXCASH":
            cols["fx_amount"][j] = q
    return pd.DataFrame(cols, index=book.index)
