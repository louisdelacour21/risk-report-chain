import hashlib

import numpy as np
from synth import generate as g
from synth import market as M


def sha(d):
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.glob("*"))}


def test_seed_stability(tmp_path):
    assert sha(g.write_day(tmp_path / "a")) == sha(g.write_day(tmp_path / "b"))


def test_book_size_and_desks():
    st, pos = g.build_book()
    assert 50 <= len(pos) <= 70 and set(st.desk) == {"EQUITY", "RATES", "FX"}


def test_market_shape_and_moments():
    lev, sig = M.simulate()
    assert lev.shape == (750, len(M.FACTORS)) and np.isfinite(lev.values).all() and (lev[M.IV] >= 0.01).all().all()
    r = np.log(lev["EQ1"]).diff().dropna()
    assert 0.12 < r.std() * np.sqrt(252) < 0.30 and (r / sig["EQ1"].iloc[1:]).kurt() > 0.5  # fat tails survive standardisation by sigma_t


def test_correlation_psd_unit_diag():
    C = M.correlation()
    assert np.allclose(np.diag(C), 1) and np.linalg.eigvalsh(C).min() > 0


def test_defects_touch_single_files(tmp_path):
    clean = sha(g.write_day(tmp_path / "c", defects=()))
    for d, f in [("missing_price", "prices.csv"), ("qty_break", "positions_bo.csv"), ("duplicate", "positions_fo.csv"), ("missing_fx", "fx.csv")]:
        out = sha(g.write_day(tmp_path / d, defects=[d]))
        changed = {k for k in out if out[k] != clean[k]} - {"truth.json"}
        assert changed == {f}, (d, changed)
