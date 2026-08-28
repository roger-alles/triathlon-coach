"""El servidor MCP exposa les 4 eines de lectura de la spec §10 F2."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server.server as server


def test_exposes_the_four_read_tools():
    for name in ("get_recent_activities", "get_form_curve", "get_week",
                 "get_compliance"):
        fn = getattr(server, name)
        assert callable(fn)
        assert fn.__doc__  # la descripció de l'eina surt del docstring
