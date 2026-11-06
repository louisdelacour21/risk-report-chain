"""One run end to end: ingest -> input controls -> P&L / explain -> VaR/ES -> limits -> controls C12-C13 -> workbook -> C14 re-read.
Status: any failed blocking control = NOT_VALIDATED (the workbook is still produced, with a red banner); else any failed alert control =
WITH_RESERVATIONS; else VALIDATED. Limit breaches are results, not data-quality failures: they are reported but do not change the status."""
from dataclasses import dataclass, field

from riskreport import config, ingest, pnl, report, risk
from riskreport import controls as C
from riskreport import valuation as V

NEEDED = ("C01", "C02", "C04", "C09", "C10")  # without these the numbers cannot be computed


@dataclass
class Run:
    asof: object
    cfg_sha: str
    inp: object
    controls: list
    status: str = "NOT_VALIDATED"
    computed: bool = False
    pos: object = None
    desks: object = None
    res: dict = field(default_factory=dict)
    expo: object = None
    limits: object = None
    metrics: dict = field(default_factory=dict)
    market: object = None
    book: object = None
    meta: dict = field(default_factory=dict)


def status_of(controls):
    if any(not c.ok and c.severity == "B" for c in controls):
        return "NOT_VALIDATED"
    return "WITH_RESERVATIONS" if any(not c.ok for c in controls) else "VALIDATED"


def compute(run):
    cfg, inp = run.inp.cfg, run.inp
    run.book, run.market = V.build_book(inp), V.market(inp)
    run.pos = pnl.hypothetical(run.book, run.market, cfg)
    run.desks = pnl.by_desk(run.pos, inp.tables["pnl_fo"])
    run.res = risk.run(run.book, inp.tables["factor_history"], run.market, cfg)
    run.expo = risk.exposures(run.book, run.market, cfg)
    run.metrics = risk.metrics(run.res, run.expo)
    run.limits = risk.limits_status(run.metrics, inp.tables["limits"], cfg)
    run.controls += [C.c12(run.desks, cfg), C.c13(run.desks, cfg)]
    run.computed = True


def execute(folder, asof, out_dir, cfg_path=config.DEFAULT, reread=True, meta=None):
    cfg, sha = config.load(cfg_path)
    inp = ingest.load(folder, asof, cfg)
    run = Run(asof, sha, inp, C.run_input_controls(inp), meta=meta or {})
    blocking_failed = {c.id for c in run.controls if not c.ok and c.severity == "B"}
    if not blocking_failed & set(NEEDED):
        compute(run)
    run.status = status_of(run.controls)
    path = report.write(run, out_dir)
    if run.computed and reread:
        c14 = report.c14(run, path)
        run.controls.append(c14)
        if not c14.ok:
            run.status = "NOT_VALIDATED"
        path = report.write(run, out_dir)
    return run, path
