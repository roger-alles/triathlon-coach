"""Configuració del coach que viu a la BD (app_setting) i l'app pot canviar.

coach_apply_mode: 'dry_run' (cicle sencer, cap canvi al pla) o 'hybrid' (canvis
petits aplicats sols, estructurals com a proposta). Qualsevol altre valor, o
cap fila, és dry_run: el mode segur és el que no toca res.
"""

APPLY_MODES = ("dry_run", "hybrid")


def apply_mode(conn) -> str:
    row = conn.execute(
        "select value from app_setting where key = 'coach_apply_mode'").fetchone()
    value = row[0] if row else None
    return value if value in APPLY_MODES else "dry_run"
