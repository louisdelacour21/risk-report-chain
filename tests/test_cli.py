import pytest

from riskreport.cli import main


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0 and "generate-demo" in capsys.readouterr().out
