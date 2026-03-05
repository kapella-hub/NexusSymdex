"""CLI behavior tests."""

import pytest

from nexus_symdex.server import main


def test_main_help_exits_without_starting_server(capsys):
    """`--help` should print usage and exit cleanly."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "nexus-symdex" in out
    assert "Run the NexusSymdex MCP stdio server" in out
