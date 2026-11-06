"""P&L explain: exact where it must be, O(dS^3) residual on a lone option, FO gap catches a planted error."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from synth import generate as g

from riskreport import config, ingest, pnl
from riskreport import controls as C
from riskreport import valuation as V

CFG = config.load()[0]
ASOF = date(2026, 10, 30)


def desks(tmp_path, defects=()):
    inp = ingest.load(g.write_day(tmp_path, ASOF, defects=defects), ASOF, CFG)
    book, mk = V.build_book(inp), V.market(inp)
    pos = pnl.hypothetical(book, mk, CFG)
    return pnl.by_desk(pos, inp.tables["pnl_fo"]), pos


def test_clean_day_within_tolerance(tmp_path):
    d, _ = desks(tmp_path)
    assert C.c12(d, CFG).ok and C.c13(d, CFG).ok, d.round(0)


def test_planted_fo_error_fails_c12_only(tmp_path):
    d, _ = desks(tmp_path, ["pnl_gap"])
    assert not C.c12(d, CFG).ok and C.c13(d, CFG).ok


def test_linear_positions_residual_is_zero(tmp_path):
    _, pos = desks(tmp_path)
    lin = pos[pos.type.isin(["EQUITY", "FUTURE", "FXCASH"])]
    assert (lin.pnl_hypo - lin.explained).abs().max() < 1e-6


def _one_option(shock):
    b = pd.DataFrame([{"desk": "EQUITY", "book": "B", "instrument": "O", "type": "OPTION", "quantity": 100.0, "multiplier": 100.0, "factor": "EQ1",
                       "iv": "IV_EQ1", "strike": 100.0, "expiry": "2027-10-29", "right": "C", "coupon": np.nan, "maturity_years": np.nan}])
    lv0, lv1 = {"EQ1": 100.0, "IV_EQ1": 0.25}, {"EQ1": 100.0 * (1 + shock), "IV_EQ1": 0.25}
    mk = V.Mkt(ASOF, ASOF, lv0, lv1, {}, {}, [])
    p = pnl.hypothetical(b, mk, CFG).iloc[0]
    return p.pnl_hypo - p.explained


def test_option_residual_scales_with_cube_of_move():
    r1, r2 = _one_option(0.005), _one_option(0.01)
    assert r2 / r1 == pytest.approx(8, rel=0.1)  # same-day shock so no dS*dt cross term; O(dS^3): doubling the move multiplies the residual by about 8
