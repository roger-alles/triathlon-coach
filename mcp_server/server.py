"""Servidor MCP de l'entrenador (spec §10 F2) — eines de lectura sobre la DB.

Permet consultar les dades reals conversant amb Claude, abans que existeixi
cap app. Les eines d'escriptura del pla (propose_sessions, update_session)
arriben amb les taules del pla a la F3.

Execució (stdio, el llança el client MCP):
    .venv/bin/python mcp_server/server.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # executable com a fitxer solt des de qualsevol cwd

import psycopg
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from mcp_server import queries

mcp = MCPServer(
    "entrenador-triatlo",
    instructions="Dades reals d'entrenament de Roger (Garmin -> Postgres). "
                 "Càrrega en unitats TRIMP; ctl/atl/tsb = forma/fatiga/frescor.",
)


def _conn():
    load_dotenv(ROOT / ".env")
    return psycopg.connect(os.getenv("DATABASE_URL"))


@mcp.tool()
def get_recent_activities(days: int = 14) -> list[dict]:
    """Activitats reals dels últims N dies, amb ritme, FC, càrrega i notes."""
    with _conn() as conn:
        return queries.recent_activities(conn, days)


@mcp.tool()
def get_form_curve(days: int = 90) -> list[dict]:
    """Corba de forma dia a dia: load, ctl (forma), atl (fatiga), tsb (frescor),
    monotonia i strain dels últims N dies."""
    with _conn() as conn:
        return queries.form_curve(conn, days)


@mcp.tool()
def get_week(offset_weeks: int = 0) -> dict:
    """Una setmana (dilluns-diumenge): activitats i totals per esport.
    offset_weeks=0 és l'actual, -1 l'anterior."""
    with _conn() as conn:
        return queries.week(conn, offset_weeks)


@mcp.tool()
def get_compliance() -> dict:
    """Compliment planificat vs real. Fins a la F3 no hi ha pla carregat."""
    with _conn() as conn:
        return queries.compliance(conn)


if __name__ == "__main__":
    mcp.run()
