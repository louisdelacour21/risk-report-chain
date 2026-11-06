"""End-to-end statuses on the clean day and on blocking / alert defects."""
from datetime import date

import openpyxl
import pytest
from synth import generate as g

from riskreport import pipeline, report

ASOF = date(2026, 10, 30)


def go(tmp_path, defects=()):
    folder = g.write_day(tmp_path / "in", ASOF, defects=defects)
    return pipeline.execute(folder, ASOF, tmp_path / "out")


def test_clean_day_validated(tmp_path):
    run, path = go(tmp_path)
    assert run.status == "VALIDATED" and run.computed
    assert openpyxl.load_workbook(path).sheetnames == report.SHEETS
    assert [c.id for c in run.controls][-3:] == ["C12", "C13", "C14"]


@pytest.mark.parametrize("defect,status", [("missing_price", "WITH_RESERVATIONS"), ("qty_break", "WITH_RESERVATIONS"),
                                           ("duplicate", "NOT_VALIDATED"), ("missing_fx", "NOT_VALIDATED"), ("pnl_gap", "WITH_RESERVATIONS")])
def test_defect_status(tmp_path, defect, status):
    run, path = go(tmp_path, [defect])
    assert run.status == status and path.exists()


def test_missing_fx_still_produces_flagged_workbook(tmp_path):
    _run, path = go(tmp_path, ["missing_fx"])
    assert openpyxl.load_workbook(path)["Summary"]["A1"].value.startswith("NOT VALIDATED")


def test_limit_breach_is_reported_not_a_status_change(tmp_path):
    run, _ = go(tmp_path, ["var_limit_breach"])
    assert run.status == "VALIDATED" and (run.limits.status == "BREACH").sum() == 1
    assert "BREACH" in " ".join(report.commentary(run))
