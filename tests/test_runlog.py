"""Archive, journal, replay and CLI exit codes."""
import json
from datetime import date

from synth import generate as g

from riskreport import cli, runlog

ASOF = date(2026, 10, 30)


def test_run_archives_and_replays_identically(tmp_path):
    folder = g.write_day(tmp_path / "in", ASOF)
    run, d = runlog.execute(folder, ASOF, tmp_path / "runs")
    assert {p.name for p in d.iterdir()} >= {"inputs", "report.xlsx", "results.json", "manifest.json", "journal.jsonl", "mail.eml"}
    events = [json.loads(x)["event"] for x in (d / "journal.jsonl").read_text().splitlines()]
    assert events[0] == "start" and events[-1] == "end" and events.count("control") == len(run.controls)
    assert runlog.rerun(d) == []


def test_second_run_of_the_day_gets_v2(tmp_path):
    folder = g.write_day(tmp_path / "in", ASOF)
    _, d1 = runlog.execute(folder, ASOF, tmp_path / "runs")
    _, d2 = runlog.execute(folder, ASOF, tmp_path / "runs")
    assert d2.name == d1.name + "_v2"


def test_replay_detects_tampered_input(tmp_path):
    folder = g.write_day(tmp_path / "in", ASOF)
    _, d = runlog.execute(folder, ASOF, tmp_path / "runs")
    f = d / "inputs" / ASOF.isoformat() / "positions_fo.csv"
    f.write_text(f.read_text().replace(",EQ1,", ",EQ1,9", 1))
    diffs = runlog.rerun(d)
    assert any("positions_fo.csv changed" in x for x in diffs)


def test_cli_exit_codes(tmp_path):
    base = ["--inbox", str(tmp_path / "in"), "--date", "2026-10-30"]
    assert cli.main(["generate-demo", *base]) == 0
    assert cli.main(["run", *base, "--runs", str(tmp_path / "runs")]) == 0
    assert cli.main(["check", *base]) == 0
    assert cli.main(["run", "--inbox", str(tmp_path / "nothing"), "--date", "2026-10-30", "--runs", str(tmp_path / "r2")]) == 3
