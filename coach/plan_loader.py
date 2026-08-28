"""Constructors del pla per al validador: des del YAML seed o des de la DB.

CLI (valida el pla actiu de la base de dades):
    .venv/bin/python -m coach.plan_loader
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import yaml

from coach.models import Athlete, Block, DailyMetric, Goal, History, Session
from coach.rules import validate_plan

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ingest.seed import session_row, split_entries  # noqa: E402


def plan_from_yaml(path: Path) -> tuple[list[Session], Goal]:
    """El pla del seed com a objectes del validador (sense tocar la DB)."""
    data = yaml.safe_load(Path(path).read_text())
    g = data["goal"]
    goal = Goal(name=g["name"], discipline=g["discipline"],
                event_date=g["event_date"], priority=g["priority"],
                profile=g.get("profile") or {})
    plan: list[Session] = []
    for i, b in enumerate(data["blocks"]):
        block = Block(id=i + 1, phase=b["phase"], start_date=b["start_date"],
                      end_date=b["end_date"],
                      target_weekly_hours=b.get("target_weekly_hours"),
                      return_from_layoff=bool(b.get("return_from_layoff")))
        sessions, _ = split_entries(b.get("sessions", []))
        for s in sessions:
            row = session_row(s)
            plan.append(Session(
                local_date=row["local_date"], sport=row["sport"],
                session_type=row["session_type"], title=row["title"],
                structure=row["structure"], block=block,
                duration_sec_target=row["duration_sec_target"],
                priority=row["priority"], is_test=row["is_test"],
                rehearses_goal=row["rehearses_goal"],
                is_goal_event=row["is_goal_event"],
                chained=row["_parent_of_day"] is not None))
    return plan, goal


def plan_from_db(conn) -> tuple[list[Session], Goal, History, Athlete]:
    """El pla viu de la DB + context (historial real, atleta) per validar-lo."""
    g = conn.execute("""select name, discipline, event_date, priority, profile
                        from goal where status='active' order by event_date limit 1""").fetchone()
    if not g:
        sys.exit("Cap objectiu actiu a la base de dades.")
    goal = Goal(name=g[0], discipline=g[1], event_date=g[2], priority=g[3],
                profile=g[4] or {})

    blocks = {r[0]: Block(id=r[0], phase=r[1], start_date=r[2], end_date=r[3],
                          target_weekly_hours=float(r[4]) if r[4] else None,
                          return_from_layoff=r[5])
              for r in conn.execute("""select id, phase, start_date, end_date,
                                       target_weekly_hours, return_from_layoff
                                       from plan_block""")}
    plan = [Session(local_date=r[0], sport=r[1], session_type=r[2], title=r[3],
                    structure=r[4], block=blocks.get(r[5]),
                    duration_sec_target=r[6], priority=r[7], status=r[8],
                    is_test=r[9], rehearses_goal=r[10], is_goal_event=r[11],
                    chained=r[12] is not None)
            for r in conn.execute("""select local_date, sport, session_type, title,
                                     structure, block_id, duration_sec_target,
                                     priority, status, is_test, rehearses_goal,
                                     is_goal_event, chained_after
                                     from plan_session where superseded_by is null""")]

    plan_start = min(s.local_date for s in plan)
    weekly = {}
    for r in conn.execute("""
            select date_trunc('week', local_date)::date, sum(duration_sec)/3600.0
            from activity where local_date < %s and local_date >= %s
            group by 1""", (plan_start, plan_start - timedelta(weeks=5))):
        weekly[r[0]] = float(r[1])
    metrics = [DailyMetric(r[0], r[1], r[2])
               for r in conn.execute("""select local_date, hrv_status, training_readiness
                                        from daily_metric where local_date >= %s""",
                                     (plan_start,))]
    a = conn.execute("""select name, max_hr, ftp_watts, css_sec_per_100m,
                        threshold_pace_sec_km from athlete where id=1""").fetchone()
    athlete = Athlete(name=a[0], max_hr=a[1], ftp_watts=a[2],
                      css_sec_per_100m=float(a[3]) if a[3] else None,
                      threshold_pace_sec_km=float(a[4]) if a[4] else None)
    return plan, goal, History(weekly_hours=weekly, daily_metrics=metrics), athlete


def main() -> None:
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    with psycopg.connect(url) as conn:
        plan, goal, history, athlete = plan_from_db(conn)

    reference = min(s.local_date for s in plan)
    violations = validate_plan(plan, athlete, history, [goal], reference_date=reference)
    print(f"pla '{goal.name}': {len(plan)} sessions validades (referència {reference})")
    if not violations:
        print("CAP VIOLACIÓ: el pla passa les 14 regles.")
        return
    for v in violations:
        print(f"  {v.rule} [{v.severity}]: {v.message}")
    if any(v.blocking for v in violations):
        sys.exit(1)


if __name__ == "__main__":
    main()
