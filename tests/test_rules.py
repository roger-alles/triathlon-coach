"""Un cas que incompleix i un que respecta, per regla (spec §12.1).

Helpers: setmanes sintètiques de dilluns (rest) + sessions senzilles.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Athlete, Block, DailyMetric, Goal, History, Session, Violation
from coach.rules import validate_plan

ATHLETE = Athlete(name="Roger", max_hr=211)
MON = date(2026, 10, 5)  # dilluns, cap cursa a prop


def mk_block(start, weeks=1, phase="build", layoff=False, target=7.0):
    return Block(id=1, phase=phase, start_date=start,
                 end_date=start + timedelta(days=7 * weeks - 1),
                 target_weekly_hours=target, return_from_layoff=layoff)


def easy_session(d, sport="run", hours=1.0, priority="support", block=None, **kw):
    sec = int(hours * 3600)
    return Session(local_date=d, sport=sport, session_type="easy", title=f"{sport}-{d}",
                   structure={"steps": [{"phase": "main", "duration_sec": sec,
                                         "target": {"type": "rpe", "value": 3}}]},
                   duration_sec_target=sec, priority=priority, block=block, **kw)


def rest_session(d, block=None):
    return Session(local_date=d, sport="rest", session_type="full", title="Descans",
                   structure={"steps": []}, priority="key", block=block)


def steady_week(monday, hours, block, n_sessions=4):
    """Dilluns descans + n sessions repartides que sumen `hours` (variades per R12)."""
    weights = [0.31, 0.27, 0.23, 0.19][:n_sessions]
    days = [1, 2, 4, 5][:n_sessions]
    sessions = [rest_session(monday, block)]
    for w, offset in zip(weights, days):
        sessions.append(easy_session(monday + timedelta(days=offset),
                                     hours=hours * w, block=block))
    return sessions


def history_flat(first_monday, hours=7.0, weeks=4):
    return History(weekly_hours={first_monday - timedelta(weeks=i): hours
                                 for i in range(1, weeks + 1)})


def run(plan, history=None, goals=(), reference=None):
    return validate_plan(plan, ATHLETE, history or History(), list(goals),
                         reference_date=reference or min(s.local_date for s in plan))


def rules_of(violations):
    return {v.rule for v in violations}


# ─── R1 rampa ────────────────────────────────────────────────────────

def test_r1_steady_state_30pct_ramp_is_rejected():
    """El criteri d'acceptació de la F3: rampa del 30% en règim estacionari."""
    plan = []
    b = mk_block(MON, weeks=5)
    for i, h in enumerate([7, 7, 7, 7, 9.1]):
        plan += steady_week(MON + timedelta(weeks=i), h, b)
    violations = run(plan, history_flat(MON))
    r1 = [v for v in violations if v.rule == "R1"]
    assert r1 and r1[0].blocking
    assert "9.1" in r1[0].message and "+30" in r1[0].message


def test_r1_flat_plan_passes_and_layoff_base_is_exempt():
    b_layoff = mk_block(MON, phase="base", layoff=True, target=4.5)
    b = mk_block(MON + timedelta(weeks=1), weeks=3)
    plan = steady_week(MON, 4.5, b_layoff)
    for i, h in enumerate([7, 7, 7]):
        plan += steady_week(MON + timedelta(weeks=i + 1), h, b)
    # 4.5h -> 7h seria +55%, però la base és una setmana de represa: exempt
    assert "R1" not in rules_of(run(plan, history_flat(MON, hours=5)))


# ─── R3 separació entre sessions clau ────────────────────────────────

def test_r3_same_sport_keys_too_close():
    b = mk_block(MON)
    plan = steady_week(MON, 6, b)
    plan += [easy_session(MON + timedelta(days=2), priority="key", block=b, hours=0.1),
             easy_session(MON + timedelta(days=3), priority="key", block=b, hours=0.1)]
    v = [v for v in run(plan) if v.rule == "R3"]
    assert v and v[0].blocking


def test_r3_different_sport_key_same_day_blocked_but_consecutive_days_ok():
    b = mk_block(MON)
    plan = steady_week(MON, 6, b)
    plan += [easy_session(MON + timedelta(days=2), sport="run", priority="key", block=b, hours=0.1),
             easy_session(MON + timedelta(days=2), sport="bike", priority="key", block=b, hours=0.1)]
    assert "R3" in rules_of(run(plan))
    plan2 = steady_week(MON, 6, b)
    plan2 += [easy_session(MON + timedelta(days=2), sport="run", priority="key", block=b, hours=0.1),
              easy_session(MON + timedelta(days=3), sport="bike", priority="key", block=b, hours=0.1)]
    assert "R3" not in rules_of(run(plan2))


# ─── R5 descans ──────────────────────────────────────────────────────

def test_r5_week_without_rest_day_is_blocked():
    b = mk_block(MON)
    plan = [easy_session(MON + timedelta(days=i), hours=1, block=b) for i in range(7)]
    v = [v for v in run(plan) if v.rule == "R5"]
    assert v and v[0].blocking


def test_r5_week_with_rest_passes():
    assert "R5" not in rules_of(run(steady_week(MON, 6, mk_block(MON))))


# ─── R4 intensitat per fase ──────────────────────────────────────────

def test_r4_build_week_too_intense_warns():
    b = mk_block(MON)
    plan = [rest_session(MON, b)]
    for i in [1, 2, 4, 5]:
        s = Session(local_date=MON + timedelta(days=i), sport="run",
                    session_type="intervals", title=f"hard-{i}",
                    structure={"steps": [{"phase": "main", "duration_sec": 3600,
                                          "target": {"type": "rpe", "value": 8}}]},
                    duration_sec_target=3600, block=b)
        plan.append(s)
    v = [v for v in run(plan) if v.rule == "R4"]
    assert v and not v[0].blocking


def test_r4_all_easy_build_week_passes():
    assert "R4" not in rules_of(run(steady_week(MON, 6, mk_block(MON))))


# ─── R11 senyals vermells ────────────────────────────────────────────

def test_r11_two_red_days_block_next_key():
    b = mk_block(MON)
    plan = steady_week(MON, 6, b)
    plan.append(easy_session(MON + timedelta(days=3), priority="key", block=b, hours=0.1))
    metrics = [DailyMetric(MON + timedelta(days=1), hrv_status="unbalanced"),
               DailyMetric(MON + timedelta(days=2), hrv_status="unbalanced")]
    v = [v for v in run(plan, History(daily_metrics=metrics)) if v.rule == "R11"]
    assert v and v[0].blocking


def test_r11_null_metrics_never_trigger():
    plan = steady_week(MON, 6, mk_block(MON))
    metrics = [DailyMetric(MON + timedelta(days=i)) for i in range(7)]
    assert "R11" not in rules_of(run(plan, History(daily_metrics=metrics)))


# ─── R12 monotonia ───────────────────────────────────────────────────

def test_r12_identical_days_warn():
    b = mk_block(MON)
    plan = [easy_session(MON + timedelta(days=i), hours=1, block=b) for i in range(7)]
    assert "R12" in rules_of(run(plan))


# ─── R14 integritat ──────────────────────────────────────────────────

def test_r14_invalid_structure_is_blocked():
    b = mk_block(MON)
    plan = steady_week(MON, 6, b)
    plan.append(Session(local_date=MON + timedelta(days=3), sport="bike",
                        session_type="threshold", title="amb FTP inexistent",
                        structure={"steps": [{"duration_sec": 600,
                                              "target": {"type": "ftp_pct", "value": 0.95}}]},
                        block=b))
    v = [v for v in run(plan) if v.rule == "R14"]
    assert v and v[0].blocking and "ftp" in v[0].message.lower()


def test_r14_session_in_the_past_is_blocked():
    b = mk_block(MON)
    plan = steady_week(MON, 6, b)
    v = run(plan, reference=MON + timedelta(days=10))
    assert any(v_.rule == "R14" and "passat" in v_.message for v_ in v)


# ─── R7, R8, R13: es cobreixen amb el pla de Fornells (test_plan_loader) ──
# R2, R6, R9, R10: casos sintètics mínims

def test_r2_five_weeks_without_deload_warn_far_from_race():
    b = mk_block(MON, weeks=5)
    plan = []
    for i in range(5):
        plan += steady_week(MON + timedelta(weeks=i), 7, b)
    assert "R2" in rules_of(run(plan, history_flat(MON)))


def test_r6_long_session_growth_warns():
    b = mk_block(MON, weeks=2)
    plan = steady_week(MON, 6, b) + steady_week(MON + timedelta(weeks=1), 6, b)
    for wk, hours in [(0, 1.0), (1, 1.3)]:  # +30% la llarga
        plan.append(Session(local_date=MON + timedelta(weeks=wk, days=5), sport="bike",
                            session_type="long", title=f"llarga-{wk}",
                            structure={"steps": [{"phase": "main",
                                                  "duration_sec": int(hours * 3600),
                                                  "target": {"type": "rpe", "value": 4}}]},
                            duration_sec_target=int(hours * 3600), block=b))
    assert "R6" in rules_of(run(plan, history_flat(MON)))


def test_r9_new_session_type_near_race_warns():
    race_day = MON + timedelta(weeks=3, days=5)
    goal = Goal(name="Cursa", discipline="triathlon", event_date=race_day, priority="A",
                profile={"target_times_sec": {"total": [8000, 7400, 6900]}})
    b = mk_block(MON, weeks=4)
    plan = []
    for i in range(4):
        plan += steady_week(MON + timedelta(weeks=i), 6, b)
    plan.append(Session(local_date=race_day - timedelta(days=3), sport="run",
                        session_type="hills", title="novetat",
                        structure={"steps": [{"phase": "main", "duration_sec": 1200,
                                              "target": {"type": "rpe", "value": 8}}]},
                        block=b))
    assert "R9" in rules_of(run(plan, history_flat(MON), goals=[goal]))


def test_r10_key_session_right_after_race_warns():
    race_day = MON + timedelta(days=10)
    goal = Goal(name="Cursa", discipline="triathlon", event_date=race_day, priority="A",
                profile={"target_times_sec": {"total": [8000, 7400, 6900]}})
    b = mk_block(MON, weeks=3)
    plan = steady_week(MON, 6, b) + steady_week(MON + timedelta(weeks=1), 6, b)
    plan.append(Session(local_date=race_day, sport="multisport", session_type="race",
                        title="LA CURSA", is_goal_event=True, priority="key",
                        structure={"segments": [{"sport": "run", "distance_m": 9000}]},
                        duration_sec_target=7400, block=b))
    plan.append(easy_session(race_day + timedelta(days=1), priority="key", block=b, hours=0.5))
    assert "R10" in rules_of(run(plan, history_flat(MON), goals=[goal]))
