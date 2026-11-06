import argparse
import sys
import traceback
from datetime import date
from pathlib import Path

import tomllib

from riskreport import calendar as cal
from riskreport import config, ingest, runlog
from riskreport import controls as C

EXIT = {"VALIDATED": 0, "WITH_RESERVATIONS": 1, "NOT_VALIDATED": 2, "CRASH": 3}


def _asof(a):
    return date.fromisoformat(a.date) if a.date else cal.asof_auto(date.today())


def _run(a):
    asof = _asof(a)
    run, d = runlog.execute(Path(a.inbox) / asof.isoformat(), asof, a.runs)
    print(f"{run.status}  {d / 'report.xlsx'}")
    for c in run.controls:
        if not c.ok:
            print(f"  {c.id} {'BLOCKING' if c.severity == 'B' else 'alert'}: {c.name} ({c.n})")
    return EXIT[run.status]


def _check(a):
    asof = _asof(a)
    inp = ingest.load(Path(a.inbox) / asof.isoformat(), asof, config.load()[0])
    res = C.run_input_controls(inp)
    for c in res:
        print(f"{c.id} {'PASS' if c.ok else 'FAIL'} {c.name}")
        for x in c.exceptions:
            print(f"    {x}")
    return 2 if any(not c.ok and c.severity == "B" for c in res) else 1 if any(not c.ok for c in res) else 0


def _rerun(a):
    diffs = runlog.rerun(a.run_dir)
    print("REPLAY IDENTICAL (1e-9)" if not diffs else "REPLAY DIFFERS:\n  " + "\n  ".join(diffs))
    return 0 if not diffs else 2


def _demo(a):
    from synth import generate

    defects = tomllib.loads(Path(a.defects).read_text())["defects"] if a.defects else []
    print(generate.write_day(a.inbox, _asof(a), a.seed, defects=defects))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="riskreport", description="Daily market-risk reporting chain")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, h, fn in [("run", "produce the report for a date", _run), ("check", "run the input controls only", _check),
                        ("rerun", "replay an archived run and compare", _rerun), ("generate-demo", "write synthetic inputs", _demo)]:
        s = sub.add_parser(name, help=h)
        s.set_defaults(fn=fn)
        if name == "rerun":
            s.add_argument("run_dir")
            continue
        s.add_argument("--date", help="as-of date YYYY-MM-DD (default: last TARGET2 business day)")
        s.add_argument("--inbox", default="data/inbox")
        if name == "run":
            s.add_argument("--runs", default="runs")
        if name == "generate-demo":
            s.add_argument("--defects", help="TOML file with defects = [...]")
            s.add_argument("--seed", type=int, default=42)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except Exception:  # noqa: BLE001 - the scheduler needs a distinct exit code and a traceback
        traceback.print_exc()
        return EXIT["CRASH"]


if __name__ == "__main__":
    sys.exit(main())
