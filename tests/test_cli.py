import pytest

from riskreport.cli import main


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0 and "generate-demo" in capsys.readouterr().out


def test_showcase_writes_both_reports(tmp_path, capsys):
    assert main(["showcase", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "ok: VALIDATED" in out and "bad: NOT_VALIDATED" in out and "identical" in out
    ok, bad = [(tmp_path / f"{n}.html").read_text(encoding="utf-8") for n in ("ok", "bad")]
    assert "#2E7D32" in ok and "do not circulate" in bad and "VaR backtest" in ok
