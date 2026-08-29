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
    assert sorted(v.message for v in violations) == [
        "2026-09-18: 'run/intervals' mai practicat abans, a 9 dies de la cursa",
        "2026-09-23: 'run/intervals' mai practicat abans, a 4 dies de la cursa",
    ]


def test_fornells_loads_expected_shape():
    plan, goal = plan_from_yaml(SEED)
    assert len(plan) == 44
    assert goal.event_date == date(2026, 9, 27)
    assert sum(1 for s in plan if s.is_goal_event) == 1
    assert sum(1 for s in plan if s.chained) == 7
