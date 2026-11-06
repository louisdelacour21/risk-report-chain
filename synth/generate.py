"""Writes the morning extractions for one reporting date into <out>/<date>/: positions_fo, positions_bo, statics, prices, fx, limits,
factor_history (6 CSV + history). Defects are injected after the clean files exist, each one touching a single file."""
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import tomllib

from riskreport import calendar as cal
from riskreport import config, pnl
from riskreport import valuation as V
from synth import market as M

DEFECTS = ["missing_price", "stale_price", "duplicate", "qty_break", "jump_9sigma", "missing_fx", "var_limit_breach", "dv01_breach", "pnl_gap"]


def build_book(seed=42, asof=date(2026, 10, 30)):
    """Static data + positions for 3 desks, ~60 lines. Options expire after asof; bonds keep an annual coupon."""
    rng = np.random.default_rng(seed + 1)
    st, pos = [], []

    def add(iid, typ, desk, book, qty, **kw):
        st.append({"instrument": iid, "type": typ, "desk": desk, **kw})
        pos.append({"desk": desk, "book": book, "instrument": iid, "quantity": qty})

    for k, e in enumerate(M.EQ):  # 8 stocks, long and short books
        add(e, "EQUITY", "EQUITY", "EQ_CASH", int(rng.choice([-1, 1]) * rng.integers(2, 12) * 1000), factor=e, ccy="EUR", multiplier=1.0)
    for name, q in [("FUT_IDX_DEC", 40), ("FUT_IDX_MAR", -25)]:
        add(name, "FUTURE", "EQUITY", "EQ_DELTA1", q, factor="IDX", ccy="EUR", multiplier=10.0)
    for u in M.OPT_UND:  # 6 options per underlying
        s0 = float(M.START[u])
        for j in range(6):
            right = "C" if j % 2 == 0 else "P"
            K = round(s0 * [1.0, 0.95, 1.05, 0.9, 1.1, 1.0][j] * 1.1, 0)  # strikes around the end-of-sample level
            exp = asof + timedelta(int(rng.choice([45, 90, 180, 270, 365])))
            add(f"OPT_{u}_{right}{int(K)}_{exp:%y%m%d}", "OPTION", "EQUITY", "EQ_OPT", int(rng.choice([-1, 1]) * rng.integers(5, 40) * 10), factor=u,
                iv=f"IV_{u}", ccy="EUR", multiplier=100.0, strike=float(K), expiry=exp.isoformat(), right=right)
    for ctry, pil, cpn, yrs, q in [("DE", "DE2Y", 2.0, 2, 8), ("DE", "DE5Y", 2.5, 5, 10), ("DE", "DE10Y", 2.5, 10, 12), ("DE", "DE10Y", 2.8, 9, -6),
                                    ("FR", "FR10Y", 3.0, 10, 9), ("FR", "FR10Y", 3.4, 8, -5), ("IT", "IT10Y", 3.8, 10, 7), ("IT", "IT10Y", 4.2, 7, -4),
                                    ("DE", "DE2Y", 1.5, 3, -5), ("DE", "DE5Y", 2.2, 4, 6), ("FR", "FR10Y", 2.9, 9, 5), ("IT", "IT10Y", 3.5, 8, -3)]:
        add(f"BOND_{ctry}_{cpn}_{yrs}Y", "BOND", "RATES", "RATES_GOV", q * 1_000_000, factor=pil, ccy="EUR", multiplier=1.0, coupon=cpn, maturity_years=float(yrs), country=ctry)
    for ccy, pair, q in [("USD", "EURUSD", 15_000_000), ("USD", "EURUSD", -4_000_000), ("GBP", "EURGBP", -9_000_000), ("GBP", "EURGBP", 3_000_000),
                         ("JPY", "EURJPY", 1_200_000_000), ("JPY", "EURJPY", -500_000_000)]:
        add(f"CASH_{ccy}_{len([s for s in st if s['instrument'].startswith('CASH_' + ccy)]) + 1}", "FXCASH", "FX", "FX_SPOT", q, factor=pair, ccy=ccy, multiplier=1.0)
    return pd.DataFrame(st), pd.DataFrame(pos)


def fo_pnl(st, pos, lev, asof, seed):
    """FO P&L = true hypothetical P&L + intraday new-trade effect on a few lines + fees + 1% noise (all independent of the explain model)."""
    book = pos.merge(st.drop(columns=["desk"]), on="instrument", how="left")
    lv = lev.iloc[-1].to_dict()
    mk = V.Mkt(asof, cal.previous(asof), lev.iloc[-2].to_dict(), lv, {p: lev.iloc[-2][p] for p in M.FX}, {p: lv[p] for p in M.FX}, [])
    h = pnl.hypothetical(book, mk, config.load()[0])
    rng = np.random.default_rng(seed + 7)
    fo = h.pnl_hypo * (1 + 0.01 * rng.standard_normal(len(h))) - 0.00002 * np.abs(book.quantity * book.multiplier) * (book.type != "FXCASH")  # fees
    fo = fo + np.where(book.instrument.isin(["EQ1", "EQ2"]), 1500.0, 0.0)  # new trades done after the position snapshot
    return pd.DataFrame({"desk": pos.desk, "book": pos.book, "instrument": pos.instrument, "pnl": fo.round(2)})


def write_day(out, asof=date(2026, 10, 30), seed=42, n_days=750, defects=()):
    out = Path(out) / asof.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    lev, sig = M.simulate(seed, n_days, asof)
    st, pos = build_book(seed, asof)
    fo, bo = pos.copy(), pos.copy()
    prc_inst = st[st.type.isin(["EQUITY", "FUTURE"])]
    last6 = lev.index[-6:]
    prices = pd.DataFrame([{"date": d.date().isoformat(), "instrument": r.instrument, "price": float(lev.loc[d, r.factor])} for d in last6 for r in prc_inst.itertuples()])
    fx = pd.DataFrame([{"date": d.date().isoformat(), "pair": p, "rate": float(lev.loc[d, p])} for d in last6 for p in M.FX])
    limits = pd.DataFrame(columns=["desk", "metric", "limit"])  # filled by the limits step once the metrics exist
    pnl_fo = fo_pnl(st, pos, lev, asof, seed)
    hist = lev.copy()
    hist.index = [d.date().isoformat() for d in hist.index]
    used = set(defects)
    if "missing_price" in used:
        prices = prices[~((prices.instrument == "EQ3") & (prices.date == asof.isoformat()))]
    if "stale_price" in used:
        m = prices.instrument == "EQ5"
        prices.loc[m & (prices.date >= last6[-4].date().isoformat()), "price"] = float(prices[m & (prices.date == last6[-4].date().isoformat())].price.iloc[0])
    if "duplicate" in used:
        fo = pd.concat([fo, fo.iloc[[3]]], ignore_index=True)
    if "qty_break" in used:
        bo.loc[bo.instrument == "EQ2", "quantity"] += 500
    if "jump_9sigma" in used:
        i = (prices.instrument == "EQ7") & (prices.date == asof.isoformat())
        prev = prices[(prices.instrument == "EQ7") & (prices.date == last6[-2].date().isoformat())].price.iloc[0]
        new = prev * np.exp(9 * sig["EQ7"].iloc[-1])
        prices.loc[i, "price"] = new
        hist.iloc[-1, hist.columns.get_loc("EQ7")] = new
    if "missing_fx" in used:
        fx = fx[~((fx.pair == "EURGBP") & (fx.date == asof.isoformat()))]
    if "pnl_gap" in used:
        pnl_fo.loc[pnl_fo.instrument == "EQ8", "pnl"] += 90_000.0
    files = {"positions_fo": fo, "positions_bo": bo, "statics": st, "prices": prices, "fx": fx, "limits": limits, "pnl_fo": pnl_fo}
    src = config.load()[0]["sources"]
    for k, df in files.items():
        df.to_csv(out / f"{k}.csv", index=False, sep=src[k]["sep"], decimal=src[k]["decimal"])
    hist.to_csv(out / "factor_history.csv", index_label="date", sep=src["factor_history"]["sep"], decimal=src["factor_history"]["decimal"])
    (out / "truth.json").write_text(json.dumps({"seed": seed, "nu": M.NU, "alpha": M.ALPHA, "beta": M.BETA, "defects": sorted(used)}))
    sig.tail(500).to_csv(out / "true_sigma.csv", index_label="date")
    return out


def main(out="data/inbox", asof=None, defects_file=None, seed=42):
    d = []
    if defects_file:
        d = tomllib.loads(Path(defects_file).read_text())["defects"]
    return write_day(out, asof or cal.asof_auto(date(2026, 11, 2)), seed, defects=d)
