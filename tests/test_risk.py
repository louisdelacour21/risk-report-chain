"""VaR/ES by full revaluation: analytic quantile checks, additivity of contributions, limit statuses on the planted breaches."""
from datetime import date

import numpy as np
import pytest
from riskhub_engine import market
from synth import generate as g

from riskreport import config, ingest, risk
from riskreport import controls as C
from riskreport import valuation as V

CFG = config.load()[0]
ASOF = date(2026, 10, 30)


def state(tmp_path, defects=()):
    inp = ingest.load(g.write_day(tmp_path, ASOF, defects=defects), ASOF, CFG)
    book, mk = V.build_book(inp), V.market(inp)
    res = risk.run(book, inp.tables["factor_history"], mk, CFG)
    return inp, res, risk.metrics(res, risk.exposures(book, mk, CFG))


def test_known_truth_quantiles():
    """Losses 1..500: VaR99 = 496 (5th worst), ES97.5 = mean of 13 worst = 494, as the spec fixes."""
    L = -np.arange(1, 501.0)
    assert market.historical(L, 0.99)["var"] == 496 and market.historical(L, 0.975)["es"] == 494


def test_tail_has_13_scenarios_and_contributions_add_up(tmp_path):
    _, res, _ = state(tmp_path)
    assert len(res["tail"]) == 13
    assert res["desk"].ES975_contribution.sum() == pytest.approx(res["es"], rel=1e-12)


def test_diversification_and_orders(tmp_path):
    _, res, _ = state(tmp_path)
    assert res["var"] < res["desk"].VAR99.sum() and res["es"] > 0


def test_clean_limits_ok(tmp_path):
    inp, _, m = state(tmp_path)
    st = risk.limits_status(m, inp.tables["limits"], CFG)
    assert set(st.status) == {"OK"} and st.usage.max() < 0.85


@pytest.mark.parametrize("defect,key", [("var_limit_breach", ("EQUITY", "VAR99")), ("dv01_breach", ("RATES", "DV01"))])
def test_planted_breach(tmp_path, defect, key):
    inp, _, m = state(tmp_path, [defect])
    st = risk.limits_status(m, inp.tables["limits"], CFG)
    bad = st[st.status != "OK"]
    assert list(zip(bad.desk, bad.metric)) == [key] and bad.status.iloc[0] == "BREACH"
    assert all(r.ok for r in C.run_input_controls(inp))


def test_unknown_metric_reported():
    import pandas as pd
    st = risk.limits_status({}, pd.DataFrame([{"desk": "FX", "metric": "FOO", "limit": 1.0}]), CFG)
    assert st.status.iloc[0] == "NO METRIC"


def test_kupiec_known_values():
    """Zero exceptions: LR = -2 n ln(1-p); exactly the expected rate: LR = 0 and p-value 1."""
    assert risk.kupiec(0, 250, 0.01)[0] == pytest.approx(-2 * 250 * np.log(0.99))
    lr, p = risk.kupiec(5, 500, 0.01)
    assert lr == pytest.approx(0.0, abs=1e-12) and p == pytest.approx(1.0)


def test_backtest_shape_and_zone(tmp_path):
    inp = ingest.load(g.write_day(tmp_path, ASOF), ASOF, CFG)
    b = risk.backtest(V.build_book(inp), inp.tables["factor_history"], V.market(inp), CFG)
    assert b["days"] == 249 and len(b["var"]) == 249 and b["exceptions"] == int(b["exc"].sum())
    assert b["zone"] == ("GREEN" if b["exceptions"] <= 4 else "YELLOW" if b["exceptions"] <= 9 else "RED")
