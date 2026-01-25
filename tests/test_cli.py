from __future__ import annotations

from mediacopier.ui.cli import run_cli


def test_run_cli_outputs_hello_cli(capsys) -> None:
    run_cli()
    captured = capsys.readouterr()
    assert "Hello CLI" in captured.out
