"""Defect matrix: a clean set passes C01-C11, and each injected defect makes exactly the expected control fail. Fixed before running."""
from datetime import date

import pytest
from synth import generate as g

from riskreport import config, ingest
from riskreport.controls import run_input_controls

ASOF = date(2026, 10, 30)
CFG = config.load()[0]
EXPECT = {"missing_price": "C05", "stale_price": "C06", "duplicate": "C03", "qty_break": "C08", "jump_9sigma": "C07", "missing_fx": "C09"}


def results(tmp_path, defects):
    folder = g.write_day(tmp_path, ASOF, defects=defects)
    return run_input_controls(ingest.load(folder, ASOF, CFG))


def test_clean_set_passes_all_eleven(tmp_path):
    assert {r.id for r in results(tmp_path, ()) if not r.ok} == set()


@pytest.mark.parametrize("defect,control", list(EXPECT.items()))
def test_each_defect_fails_exactly_its_control(tmp_path, defect, control):
    assert {r.id for r in results(tmp_path, [defect]) if not r.ok} == {control}


def test_missing_price_one_day_is_alert(tmp_path):
    assert next(r for r in results(tmp_path, ["missing_price"]) if r.id == "C05").severity == "A"


def test_schema_and_missing_file(tmp_path):
    folder = g.write_day(tmp_path, ASOF)
    (folder / "limits.csv").unlink()
    (folder / "prices.csv").write_text("date,instrument,price\n2026-10-30,EQ1,-5\n")
    res = {r.id: r for r in run_input_controls(ingest.load(folder, ASOF, CFG))}
    assert not res["C01"].ok and not res["C02"].ok and res["C01"].severity == "B"
