"""El test de regressió que mana la spec §8.1: el pla REAL de Fornells
ha de passar el validador sencer. Si un canvi el trenca, el canvi és sospitós.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Athlete, History
from coach.plan_loader import plan_from_yaml
from coach.rules import validate_plan

SEED = Path(__file__).parent.parent / "seeds" / "fornells-2026.yaml"


def test_fornells_plan_passes_all_14_rules():
    plan, goal = plan_from_yaml(SEED)
    athlete = Athlete(name="Roger", max_hr=211)  # sense FTP/CSS/llindar, com a la realitat
    plan_start = min(s.local_date for s in plan)
    # les ~4 setmanes prèvies reals: unes 5 h/setmana (athlete_context del seed)
    history = History(weekly_hours={
        plan_start - timedelta(days=plan_start.weekday()) - timedelta(weeks=i): 5.0
        for i in range(1, 5)})

    violations = validate_plan(plan, athlete, history, [goal],
                               reference_date=plan_start)

    # 29/08: les 5×1000 del 29/08 es van substituir per rodatge (proposta del
    # coach aprovada per l'atleta) i el pla va quedar amb DOS avisos R9
    # coneguts i acceptats: run/intervals reapareix al taper sense haver-se
    # practicat dins del pla. Cap violació bloquejant, i cap avís NOU.
    blocking = [v for v in violations if v.severity == "blocking"]
    assert blocking == [], "\n".join(f"{v.rule}: {v.message}" for v in blocking)
    # 10/09: Roger és a Barcelona 15-18/09 sense bici (docs/decisions.md). La
    # bici del 16 s'absorbeix a la del 19 i el 16 passa a natació + rodatge:
    # la setmana del 14 queda amb bici al 19% i natació al 44%. Dos avisos R13
    # correctes i acceptats: no hi ha bici possible aquells dies.
    assert sorted(v.message for v in violations) == [
        "2026-09-18: 'run/intervals' mai practicat abans, a 9 dies de la cursa",
        "2026-09-23: 'run/intervals' mai practicat abans, a 4 dies de la cursa",
        "setmana 2026-09-14: bike al 19% del temps, fora de [35, 55]% (perfil triathlon)",
        "setmana 2026-09-14: swim al 44% del temps, fora de [2, 42]% (perfil triathlon)",
    ]


def test_fornells_loads_expected_shape():
    plan, goal = plan_from_yaml(SEED)
    assert len(plan) == 44
    assert goal.event_date == date(2026, 9, 27)
    assert sum(1 for s in plan if s.is_goal_event) == 1
    assert sum(1 for s in plan if s.chained) == 6


# ─── plan_from_db: objectius com a llista, mai sys.exit ────────────────

class _DbConn:
    """Respon per fragment de SQL; prou per a plan_from_db."""

    def __init__(self, goals):
        self.goals = goals

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        if "from goal" in s:
            rows = self.goals
        elif "from athlete" in s:
            rows = [("Roger", 211, None, None, None)]
        else:
            rows = []
        class R:
            def fetchone(self_inner):
                return rows[0] if rows else None
            def fetchall(self_inner):
                return rows
            def __iter__(self_inner):
                return iter(rows)
        return R()


def test_plan_from_db_returns_all_active_goals_as_a_list():
    from coach.plan_loader import plan_from_db
    conn = _DbConn([("Fornells", "triathlon", date(2026, 9, 27), "A", {}),
                    ("Transpirinenca", "ultra_endurance", date(2027, 7, 15), "A", None)])
    plan, goals, history, athlete = plan_from_db(conn)
    assert [g.name for g in goals] == ["Fornells", "Transpirinenca"]
    assert goals[1].profile == {}
    assert athlete.name == "Roger"


def test_plan_from_db_without_active_goal_does_not_exit():
    # Després de la cursa Fornells passa a completed: el coach ha de seguir
    # funcionant (bloc de recuperació) encara que no hi hagi cap objectiu actiu.
    from coach.plan_loader import plan_from_db
    plan, goals, history, athlete = plan_from_db(_DbConn([]))
    assert goals == [] and plan == []
