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


# ─── helpers per als escenaris amb cursa ─────────────────────────────

def _hard_run(d, hours=0.2, block=None, title=None):
    sec = int(hours * 3600)
    return Session(local_date=d, sport="run", session_type="intervals",
                   title=title or f"hard-{d}",
                   structure={"steps": [{"phase": "main", "duration_sec": sec,
                                         "target": {"type": "rpe", "value": 8}}]},
                   duration_sec_target=sec, block=block)


def race_session(d, block):
    return Session(local_date=d, sport="run", session_type="race", title="LA CURSA",
                   priority="key", is_goal_event=True, duration_sec_target=7400,
                   structure={"steps": [{"phase": "main", "distance_m": 9000,
                                         "target": {"type": "open"}}]}, block=block)


def taper_scenario(taper_start_offset, taper_hours=3.0, with_intensity=True,
                   with_taper_block=True):
    """2 setmanes de build a 7h + setmana de cursa; el taper es parametritza.

    taper_start_offset: dies abans de la cursa que comença el bloc de taper.
    """
    race_day = MON + timedelta(weeks=2, days=6)  # diumenge de la 3a setmana
    goal = Goal(name="Cursa", discipline="run", event_date=race_day, priority="A",
                profile={"target_times_sec": {"total": [8000, 7400, 6900]}})
    b = mk_block(MON, weeks=3)
    plan = []
    for i in range(2):
        plan += steady_week(MON + timedelta(weeks=i), 6.8, b)
        plan.append(_hard_run(MON + timedelta(weeks=i, days=3), block=b))

    week3 = MON + timedelta(weeks=2)
    plan += [rest_session(week3, b), rest_session(week3 + timedelta(days=1), b)]
    if with_taper_block:
        tb = Block(id=2, phase="taper", start_date=race_day - timedelta(days=taper_start_offset),
                   end_date=race_day, target_weekly_hours=taper_hours)
        hard_hours = 0.2 if with_intensity else 0.0
        plan.append(easy_session(week3 + timedelta(days=2), hours=taper_hours - hard_hours,
                                 block=tb))
        if with_intensity:
            plan.append(_hard_run(week3 + timedelta(days=4), block=tb))
        race_block = tb
    else:
        plan.append(easy_session(week3 + timedelta(days=2), hours=taper_hours, block=b))
        race_block = b
    plan.append(race_session(race_day, race_block))
    return plan, goal


def r8_of(plan, goal):
    return [v for v in run(plan, history_flat(MON), goals=[goal]) if v.rule == "R8"]


# ─── R7 freqüència mínima (triatló) ──────────────────────────────────

TRI_GOAL = Goal(name="Tri", discipline="triathlon", event_date=None, priority="A",
                profile={})


def test_r7_build_week_with_one_swim_and_no_brick_warns():
    b = mk_block(MON)
    plan = [rest_session(MON, b),
            easy_session(MON + timedelta(days=1), sport="swim", block=b),
            easy_session(MON + timedelta(days=2), sport="run", block=b),
            easy_session(MON + timedelta(days=4), sport="run", hours=0.8, block=b),
            easy_session(MON + timedelta(days=5), sport="bike", hours=1.2, block=b)]
    r7 = [v for v in run(plan, goals=[TRI_GOAL]) if v.rule == "R7"]
    assert len(r7) == 2  # 1 natació (<2) i cap brick
    assert not any(v.blocking for v in r7)


def test_r7_two_swims_and_a_brick_pass():
    b = mk_block(MON)
    plan = [rest_session(MON, b),
            easy_session(MON + timedelta(days=1), sport="swim", block=b),
            easy_session(MON + timedelta(days=2), sport="brick", hours=0.3, block=b),
            easy_session(MON + timedelta(days=4), sport="swim", hours=0.8, block=b),
            easy_session(MON + timedelta(days=5), sport="bike", hours=1.2, block=b)]
    assert "R7" not in rules_of(run(plan, goals=[TRI_GOAL]))


# ─── R8 taper: els quatre subcasos ───────────────────────────────────

def test_r8_missing_taper_block_is_blocked():
    plan, goal = taper_scenario(6, with_taper_block=False)
    v = r8_of(plan, goal)
    assert v and v[0].blocking and "sense bloc de taper" in v[0].message


def test_r8_taper_of_three_days_is_blocked():
    plan, goal = taper_scenario(2)
    v = r8_of(plan, goal)
    assert any("taper de 3 dies" in x.message for x in v)


def test_r8_taper_without_intensity_is_blocked():
    plan, goal = taper_scenario(6, with_intensity=False)
    v = r8_of(plan, goal)
    assert any("intensitat" in x.message for x in v)


def test_r8_volume_not_reduced_is_blocked():
    plan, goal = taper_scenario(6, taper_hours=6.5)
    v = r8_of(plan, goal)
    assert any("volum" in x.message for x in v)


def test_r8_proper_taper_passes():
    plan, goal = taper_scenario(6)
    assert r8_of(plan, goal) == []


# ─── R13 coherència amb l'objectiu ───────────────────────────────────

def test_r13_bike_only_week_warns():
    b = mk_block(MON)
    plan = [rest_session(MON, b),
            easy_session(MON + timedelta(days=2), sport="bike", hours=5, block=b)]
    r13 = [v for v in run(plan, goals=[TRI_GOAL]) if v.rule == "R13"]
    # bici al 100% (fora de [35,55]) i natació al 0% (sota el mínim del limitant no declarat)
    assert r13 and not any(v.blocking for v in r13)
    assert any("bike" in v.message for v in r13)


def test_r13_balanced_triathlon_week_passes():
    b = mk_block(MON)
    plan = [rest_session(MON, b),
            easy_session(MON + timedelta(days=1), sport="swim", hours=1.1, block=b),
            easy_session(MON + timedelta(days=2), sport="bike", hours=2.25, block=b),
            easy_session(MON + timedelta(days=4), sport="run", hours=1.4, block=b),
            easy_session(MON + timedelta(days=5), sport="strength", hours=0.25, block=b)]
    assert "R13" not in rules_of(run(plan, goals=[TRI_GOAL]))


# ─── passades dedicades que faltaven ─────────────────────────────────

def test_r2_deload_every_fourth_week_passes():
    b = mk_block(MON, weeks=5)
    plan = []
    for i, h in enumerate([7, 7, 7, 5.0, 7]):  # la 4a és descàrrega (≤72%)
        plan += steady_week(MON + timedelta(weeks=i), h, b)
    assert "R2" not in rules_of(run(plan, history_flat(MON)))


def test_r6_long_growth_under_10pct_passes():
    b = mk_block(MON, weeks=2)
    plan = steady_week(MON, 6, b) + steady_week(MON + timedelta(weeks=1), 6, b)
    for wk, hours in [(0, 1.0), (1, 1.08)]:
        plan.append(Session(local_date=MON + timedelta(weeks=wk, days=5), sport="bike",
                            session_type="long", title=f"llarga-{wk}",
                            structure={"steps": [{"phase": "main",
                                                  "duration_sec": int(hours * 3600),
                                                  "target": {"type": "rpe", "value": 4}}]},
                            duration_sec_target=int(hours * 3600), block=b))
    assert "R6" not in rules_of(run(plan, history_flat(MON)))


def test_r9_rehearsal_near_race_is_exempt():
    plan, goal = taper_scenario(6)
    plan.append(Session(local_date=goal.event_date - timedelta(days=5), sport="run",
                        session_type="race_simulation", title="assaig",
                        rehearses_goal=True,
                        structure={"steps": [{"phase": "main", "duration_sec": 1800,
                                              "target": {"type": "rpe", "value": 7}}]},
                        duration_sec_target=1800, block=plan[-1].block))
    assert "R9" not in rules_of(run(plan, history_flat(MON), goals=[goal]))


def test_r10_easy_days_after_race_pass():
    race_day = MON + timedelta(weeks=1, days=6)
    goal = Goal(name="Cursa", discipline="run", event_date=race_day, priority="A",
                profile={"target_times_sec": {"total": [8000, 7400, 6900]}})
    b = mk_block(MON, weeks=3)
    plan = steady_week(MON, 6, b) + steady_week(MON + timedelta(weeks=1), 6, b)
    plan.append(race_session(race_day, b))
    for i in range(1, 4):  # dies posteriors fàcils, cap sessió clau
        plan.append(easy_session(race_day + timedelta(days=i), hours=0.4, block=b))
    assert "R10" not in rules_of(run(plan, history_flat(MON), goals=[goal]))


def test_r12_varied_week_passes():
    assert "R12" not in rules_of(run(steady_week(MON, 6, mk_block(MON))))


# ─── casos sintètics R2, R6, R9, R10 (violacions) ───────────────────

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


# --- S2: diversos objectius, alguns sense data ------------------------------

def test_r13_usa_l_objectiu_A_mes_proper_encara_que_no_sigui_el_primer():
    from coach.rules import r13_goal_coherence, build_weeks
    monday = date(2026, 9, 7)
    block = mk_block(monday, weeks=1)
    # setmana de corredor (75% córrer, 19% bici, 6% natació): coherent amb un
    # objectiu 'run'; per a 'triathlon' la natació és massa poca
    plan = [easy_session(monday + timedelta(days=i), "run", 1.0, block=block) for i in range(3)]
    plan.append(easy_session(monday + timedelta(days=3), "bike", 0.75, block=block))
    plan.append(easy_session(monday + timedelta(days=4), "swim", 0.25, block=block))
    plan.append(rest_session(monday + timedelta(days=6), block))
    tri_far = Goal(name="Tri 2027", discipline="triathlon", event_date=date(2027, 6, 1), priority="A")
    run_near = Goal(name="10k", discipline="run", event_date=date(2026, 10, 4), priority="A")
    weeks = build_weeks(plan)
    # l'ordre de la llista no ha d'importar: mana l'A amb la data més propera
    assert r13_goal_coherence(weeks, [tri_far, run_near]) == []
    assert r13_goal_coherence(weeks, [run_near, tri_far]) == []
    # i un B/C abans a la llista no desplaça l'A
    c_tri = Goal(name="Tri C", discipline="triathlon", event_date=None, priority="C")
    assert r13_goal_coherence(weeks, [c_tri, run_near]) == []
    # comprovació que el test discrimina: amb el triatló com a primari sí que hi ha R13
    assert r13_goal_coherence(weeks, [tri_far]) != []


def test_un_objectiu_C_sense_data_no_trenca_cap_regla():
    monday = date(2026, 9, 7)
    block = mk_block(monday, weeks=2)
    plan = steady_week(monday, 7.0, block) + steady_week(monday + timedelta(days=7), 7.0, block)
    fornells = Goal(name="Fornells", discipline="triathlon", event_date=date(2026, 9, 27), priority="A",
                    profile={"emphasis": {"limiter": "swim", "protect": "run"}})
    popular = Goal(name="10 km popular", discipline="run", event_date=None, priority="C")
    with_c = run(plan, history_flat(monday - timedelta(days=28)), goals=[fornells, popular])
    without = run(plan, history_flat(monday - timedelta(days=28)), goals=[fornells])
    # el C sense data no afegeix ni treu cap violació
    assert rules_of(with_c) == rules_of(without)


# --- S4a: el validador jutja contra la realitat ----------------------------

def test_r1_setmanes_passades_compten_amb_hores_reals_no_planificades():
    from coach.rules import r1_weekly_ramp, build_weeks
    m0 = date(2026, 9, 7)
    m1, m2 = m0 + timedelta(days=7), m0 + timedelta(days=14)
    block = mk_block(m0, weeks=3)
    # setmana passada planificada a 7 h, setmana en curs 7 h, setmana vinent 7,8 h
    plan = steady_week(m0, 7.0, block) + steady_week(m1, 7.0, block) + steady_week(m2, 7.8, block)
    weeks = build_weeks(plan)
    flat = History(weekly_hours={m0 - timedelta(weeks=i): 7.0 for i in range(1, 4)})
    # sense realitat: +11% sobre 7 h → només avís tou
    assert all(v.severity == "warning" for v in r1_weekly_ramp(weeks, flat, reference_date=m1))
    # amb la setmana passada feta a 4 h de veritat, la base cau i 7,8 h és una rampa dura
    real = History(weekly_hours={**flat.weekly_hours, m0: 4.0})
    out = r1_weekly_ramp(weeks, real, reference_date=m1)
    assert any(v.severity == "blocking" and "2026-09-21" in v.message for v in out)


def test_r6_la_llarga_de_referencia_es_la_real_si_existeix():
    from coach.rules import r6_long_session_growth, build_weeks
    m0 = date(2026, 9, 7)
    m1 = m0 + timedelta(days=7)
    block = mk_block(m0, weeks=2)
    import dataclasses
    long = lambda d, h: dataclasses.replace(easy_session(d, "bike", h, block=block), session_type="long")
    plan = [rest_session(m0, block), long(m0 + timedelta(days=5), 2.0),
            rest_session(m1, block), long(m1 + timedelta(days=5), 2.1)]
    weeks = build_weeks(plan)
    # planificat 2 h → 2,1 h: +5%, cap avís
    assert r6_long_session_growth(weeks, History(), reference_date=m1) == []
    # però la llarga real de la setmana passada va ser d'1,5 h: 2,1 h és +40%
    real = History(long_by_week={m0: {"bike": 1.5 * 3600}})
    out = r6_long_session_growth(weeks, real, reference_date=m1)
    assert out and out[0].rule == "R6" and "90min" in out[0].message


def test_r8_pla_parcial_avisa_en_lloc_de_bloquejar():
    # Pla rodant: el setmanal només escriu la setmana vinent. Si la cursa cau
    # dins del pla però el taper no hi és sencer, el volum no es pot jutjar:
    # avís, no bloqueig. Amb el taper sencer, el bloqueig es manté.
    race_day = date(2026, 10, 25)   # diumenge
    goal = Goal(name="Cursa", discipline="run", event_date=race_day, priority="A",
                profile={"target_times_sec": {"total": [3600, 3300, 3000]}})
    build = mk_block(date(2026, 10, 5), weeks=2)
    taper = Block(id=2, phase="taper", start_date=date(2026, 10, 19), end_date=race_day)
    plan = steady_week(date(2026, 10, 5), 7.0, build) + steady_week(date(2026, 10, 12), 7.0, build)
    # taper sencer, massa volum (7 h = 100% de les prèvies) → bloqueig
    full_taper = steady_week(date(2026, 10, 19), 7.0, taper)
    race = easy_session(race_day, "run", 1.0, priority="key", block=taper, is_goal_event=True)
    out = run(plan + full_taper + [race], history_flat(date(2026, 9, 7)), goals=[goal])
    assert any(v.rule == "R8" and v.blocking and "volum" in v.message for v in out)
    # pla parcial: només fins dimecres del taper (el setmanal encara no ha escrit la resta)
    partial = [s for s in full_taper if s.local_date <= date(2026, 10, 21)]
    out = run(plan + partial + [race], history_flat(date(2026, 9, 7)), goals=[goal])
    r8 = [v for v in out if v.rule == "R8"]
    assert r8 and all(not v.blocking for v in r8)
    assert any("parcial" in v.message for v in r8)
