"""Known-truth benchmark: for each seed, one clean day and one day per injected defect; the chain must reach the expected status.
Detection = status is the expected one (or worse) on a defective day; false alarm = status other than VALIDATED on a clean day.
Rule fixed before the run. Wilson 95% intervals. Usage: python -m bench.benchmark N_SEEDS [OUT.json] [FIRST_SEED]"""
import json
import math
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from synth import generate as g

from riskreport import pipeline

ASOF = date(2026, 10, 30)
RANK = {"VALIDATED": 0, "WITH_RESERVATIONS": 1, "NOT_VALIDATED": 2}
EXPECT = {"missing_price": "WITH_RESERVATIONS", "stale_price": "WITH_RESERVATIONS", "duplicate": "NOT_VALIDATED", "qty_break": "WITH_RESERVATIONS",
          "jump_9sigma": "WITH_RESERVATIONS", "missing_fx": "NOT_VALIDATED", "pnl_gap": "WITH_RESERVATIONS"}
# var_limit_breach / dv01_breach are results, not data defects: the expected status stays VALIDATED and the limit must show BREACH.


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def one(tmp, seed, defect):
    folder = g.write_day(Path(tmp) / f"{seed}_{defect}", ASOF, seed, defects=[defect] if defect else [])
    run, _ = pipeline.execute(folder, ASOF, Path(tmp) / "out", reread=False)
    return run


def main(n, out=None, start=1):
    hits = {k: 0 for k in [*EXPECT, "var_limit_breach", "dv01_breach", "clean"]}
    missed = {k: [] for k in hits}  # seeds where the case did not behave as expected
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        for seed in range(start, start + n):
            r = one(tmp, seed, None)
            hit = {"clean": r.status != "VALIDATED"}  # false alarm
            for dft, want in EXPECT.items():
                hit[dft] = RANK[one(tmp, seed, dft).status] >= RANK[want]
            for dft in ("var_limit_breach", "dv01_breach"):
                r = one(tmp, seed, dft)
                hit[dft] = bool(r.status == "VALIDATED" and (r.limits.status == "BREACH").any())
            for k, v in hit.items():
                hits[k] += v
                if v if k == "clean" else not v:  # a false alarm on a clean day, or a defect not caught
                    missed[k].append(seed)
    res = {k: {"hits": int(v), "n": n, "wilson95": wilson(int(v), n), "seeds": missed[k]} for k, v in hits.items()}
    res["clean"]["meaning"] = "false alarms on clean days"
    res["seconds"] = round(time.time() - t0)
    text = json.dumps(res, indent=1)
    print(text)
    if out:
        Path(out).write_text(text)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
