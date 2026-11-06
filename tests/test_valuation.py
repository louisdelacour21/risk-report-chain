"""Valuation against independent references. Tolerances fixed beforehand."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from riskhub_engine import options
from synth import generate as g

from riskreport import config, ingest
from riskreport import valuation as V

CFG = config.load()[0]
ASOF = date(2026, 10, 30)


def test_bs_vec_matches_riskhub():
    for right in "CP":
        for S, K, T, v in [(100, 100, 1, .2), (80, 100, .25, .4), (130, 100, 2, .15)]:
            ref = options.bs(S, K, T, v, .02, .01, right)["price"]
            assert V.bs_vec(S, K, T, v, .02, .01, right) == pytest.approx(ref, rel=1e-12)


def test_put_call_parity():
    S, K, T, v, r, q = 100., 95., 1.5, .3, .025, .015
    c, p = V.bs_vec(S, K, T, v, r, q, "C"), V.bs_vec(S, K, T, v, r, q, "P")
    assert c - p == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-10)


def test_expired_option_is_intrinsic():
    assert V.bs_vec(110, 100, 0.0, .2, .02, 0, "C") == pytest.approx(10.0)


def test_zero_coupon_dv01_closed_form():
    """12 M, 10 years, 2.5% annual compounding. Finite-difference DV01 equals the closed form; duration approximates it within convexity."""
    N, T, y = 12e6, 10, 0.025
    dv = V.bond_price(N, 0.0, T, y) - V.bond_price(N, 0.0, T, y + 1e-4)
    closed = N * ((1 + y) ** -T - (1 + y + 1e-4) ** -T)
    assert dv == pytest.approx(closed, rel=1e-9)
    assert dv == pytest.approx(9140.83, abs=0.01)
    dur = N * T / (1 + y) * (1 + y) ** -T * 1e-4
    assert dur == pytest.approx(dv, rel=1e-3) and abs(dur - dv) > 1  # the gap is the convexity term


def test_par_bond_prices_at_par():
    assert V.bond_price(100.0, 3.0, 5, 0.03) == pytest.approx(100.0, abs=1e-9)


def test_greeks_match_finite_differences(tmp_path):
    folder = g.write_day(tmp_path, ASOF)
    inp = ingest.load(folder, ASOF, CFG)
    book, mk = V.build_book(inp), V.market(inp)
    sens = V.sensitivities(book, mk.lev, mk.fx, ASOF, 0.0, CFG)
    base = V.point(book, mk.lev, mk.fx, ASOF, 0.0, CFG)
    for fac_up, pick in [({f: (v if f.startswith(('IV_', 'DE', 'FR', 'IT')) else v * 1.0001) for f, v in mk.lev.items()}, "delta")]:
        up = V.point(book, fac_up, mk.fx, ASOF, 0.0, CFG)
        opt = book.type.isin(["OPTION", "EQUITY", "FUTURE"])
        # all spots bumped by 1 bp: dV ~ sum(delta_i * S_i * 1e-4) for same-factor positions
        S = np.array([mk.lev[f] for f in book.factor])
        approx = (sens[pick].to_numpy() * S * 1e-4)[opt.to_numpy()]
        assert (up - base)[opt.to_numpy()] == pytest.approx(approx, rel=2e-3, abs=1e-4)
    vega_up = V.point(book, {**mk.lev, **{f: v + 1e-4 for f, v in mk.lev.items() if f.startswith("IV_")}}, mk.fx, ASOF, 0.0, CFG)
    o = (book.type == "OPTION").to_numpy()
    assert (vega_up - base)[o] == pytest.approx(sens["vega"].to_numpy()[o] * 1e-4, rel=5e-3, abs=1e-4)


def test_aging_one_day_equals_theta(tmp_path):
    inp = ingest.load(g.write_day(tmp_path, ASOF), ASOF, CFG)
    book, mk = V.build_book(inp), V.market(inp)
    s = V.sensitivities(book, mk.lev, mk.fx, ASOF, 0.0, CFG)
    d = 1 / 365
    dv = V.point(book, mk.lev, mk.fx, ASOF, d, CFG) - V.point(book, mk.lev, mk.fx, ASOF, 0.0, CFG)
    m = book.type.isin(["OPTION", "BOND"]).to_numpy()
    assert dv[m] == pytest.approx((s["theta"] * d).to_numpy()[m], rel=2e-2, abs=0.02)  # deep OTM: second-order time curvature


def test_fx_cash_value():
    b = pd.DataFrame([{"type": "FXCASH", "quantity": 1.08e6, "factor": "EURUSD"}])
    assert V.value(b, {}, {"EURUSD": 1.08}, ASOF, 0.0, CFG)[0, 0] == pytest.approx(1e6)
