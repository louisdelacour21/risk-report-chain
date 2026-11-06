"""Traceability: run id, SHA-256 manifest of the inputs, JSON Lines journal, archive of one run, replay with comparison, notification mail (.eml).

Archive layout: runs/<date>[_v2..]/ with inputs/ (copy of the extractions), report.xlsx, results.json (numbers a replay must reproduce),
manifest.json (input hashes, config hash, versions), journal.jsonl, mail.eml."""
import hashlib
import json
import platform
import shutil
import time
import uuid
from datetime import date, datetime, timezone
from email.message import EmailMessage
from importlib import metadata
from pathlib import Path

from riskreport import config, pipeline

TOL = 1e-9


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(folder, cfg_sha):
    files = {f.name: sha256(f) for f in sorted(Path(folder).glob("*.csv"))}
    ver = {p: metadata.version(p) for p in ("pandas", "numpy", "riskhub-engine", "XlsxWriter", "openpyxl", "pandera")}
    return {"inputs": files, "config_sha256": cfg_sha, "python": platform.python_version(), "versions": ver}


def numbers(run):
    """Everything a replay must reproduce, flat and JSON-safe."""
    if not run.computed:
        return {"status": run.status}
    out = {"status": run.status, "var99": float(run.res["var"]), "es975": float(run.res["es"])}
    for d in run.desks.index:
        out[f"pnl_fo.{d}"] = float(run.desks.pnl_fo[d])
        out[f"unexplained.{d}"] = float(run.desks.unexplained[d])
        out[f"var99.{d}"] = float(run.res["desk"].VAR99[d])
        out[f"es975.{d}"] = float(run.res["desk"].ES975[d])
    out.update({f"metric.{d}.{k}": float(v) for (d, k), v in run.metrics.items()})
    return out


def run_dir(runs, asof):
    base = Path(runs) / asof.isoformat()
    d, n = base, 1
    while d.exists():
        n += 1
        d = base.with_name(f"{base.name}_v{n}")
    return d


class Journal:
    def __init__(self, path, run_id):
        self.path, self.run_id = Path(path), run_id

    def log(self, event, **kw):
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": self.run_id, "event": event, **kw}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")


def mail(run, rid, to="risk-team@example.com"):
    from riskreport.report import BANNER, commentary

    m = EmailMessage()
    m["Subject"] = f"[Market risk] Daily report {run.asof.isoformat()} - {BANNER[run.status]}"
    m["From"], m["To"] = "riskreport@example.com", to
    m.set_content("\n".join([f"Run {rid}", ""] + commentary(run) + ["", "Workbook attached in the archive folder."]))
    return m


def execute(folder, asof, runs, cfg_path=config.DEFAULT):
    """Full traced run. Returns (run, directory)."""
    t0 = time.time()
    d = run_dir(runs, asof)
    d.mkdir(parents=True)
    _cfg, sha = config.load(cfg_path)
    rid = f"{asof.isoformat()}-{sha[:6]}-{uuid.uuid4().hex[:4]}"
    j = Journal(d / "journal.jsonl", rid)
    j.log("start", folder=str(folder), asof=asof.isoformat())
    inp = d / "inputs" / asof.isoformat()  # C01 expects the folder to be named after the as-of date
    shutil.copytree(folder, inp)
    man = manifest(inp, sha)
    (d / "manifest.json").write_text(json.dumps(man, indent=1))
    j.log("manifest", n_files=len(man["inputs"]))
    run, path = pipeline.execute(inp, asof, d, cfg_path, meta={"run_id": rid, **{k: v for k, v in man.items() if k != "inputs"}})
    path.replace(d / "report.xlsx")
    for c in run.controls:
        j.log("control", id=c.id, ok=c.ok, severity=c.severity, n=c.n)
    res = numbers(run)
    (d / "results.json").write_text(json.dumps(res, indent=1))
    m = mail(run, rid)
    (d / "mail.eml").write_bytes(bytes(m))
    j.log("end", status=run.status, seconds=round(time.time() - t0, 2))
    return run, d


def rerun(folder_run):
    """Replays an archived run from its archived inputs and compares with results.json at 1e-9 relative. Returns a list of differences."""
    d = Path(folder_run)
    man = json.loads((d / "manifest.json").read_text())
    diffs = [f"input {n} changed since archiving" for n, h in man["inputs"].items() if sha256(d / "inputs" / d.name[:10] / n) != h]
    asof = date.fromisoformat(d.name[:10])
    tmp = d / "_replay"
    run, _ = pipeline.execute(d / "inputs" / asof.isoformat(), asof, tmp, reread=False)
    shutil.rmtree(tmp)
    old, new = json.loads((d / "results.json").read_text()), numbers(run)
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if isinstance(a, str) or isinstance(b, str) or a is None or b is None:
            if a != b:
                diffs.append(f"{k}: {a} -> {b}")
        elif abs(a - b) > TOL * max(1.0, abs(a)):
            diffs.append(f"{k}: {a} -> {b}")
    return diffs
