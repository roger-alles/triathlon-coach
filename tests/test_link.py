"""Tests del vinculador planificat<->real (spec §9), part pura."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.link import match_day, session_status

TODAY = date(2026, 8, 28)
D_PAST = date(2026, 8, 26)


def sess(id=1, sport="swim", target=2100, load=None, local_date=D_PAST, distance_target=None):
    return {"id": id, "sport": sport, "local_date": local_date,
            "duration_sec_target": target, "distance_m_target": distance_target,
            "planned_load": load}


def act(id=100, sport="swim", dur=1500, load=20.8, distance_m=None):
    return {"id": id, "sport": sport, "duration_sec": dur, "load": load,
            "distance_m": distance_m}


def test_match_same_day_same_sport():
    links = match_day([sess()], [act()])
    assert links == [(100, 1)]


def test_match_picks_closest_duration_among_candidates():
    short = sess(id=1, target=1800)
    long = sess(id=2, target=5400)
    links = match_day([short, long], [act(dur=5100)])
    assert links == [(100, 2)]


def test_match_ignores_other_sports():
    assert match_day([sess(sport="bike")], [act(sport="swim")]) == []


def test_status_completed_at_80pct_duration():
    s = sess(target=2100)
    assert session_status(s, [act(dur=1700)], TODAY) == "completed"  # 81%
    assert session_status(s, [act(dur=1500)], TODAY) == "partial"    # 71%


def test_status_uses_planned_load_when_present():
    s = sess(target=2100, load=100.0)
    assert session_status(s, [act(load=85.0)], TODAY) == "completed"
    assert session_status(s, [act(load=50.0)], TODAY) == "partial"


def test_status_missed_only_after_the_day_ends():
    assert session_status(sess(local_date=D_PAST), [], TODAY) == "missed"
    assert session_status(sess(local_date=TODAY), [], TODAY) is None  # el dia no s'ha acabat


def test_status_multiple_activities_sum():
    s = sess(target=3600)
    linked = [act(id=1, dur=1500), act(id=2, dur=1500)]
    assert session_status(s, linked, TODAY) == "completed"  # 83%


def test_rest_day_completes_itself_when_past():
    s = sess(sport="rest", target=None, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "completed"
    assert session_status(sess(sport="rest", target=None, local_date=TODAY), [], TODAY) is None


def test_brick_completed_bike_and_run_by_run_duration():
    s = sess(sport="brick", target=1800)  # 1800s: durada objectiu del tram a peu
    day = [act(id=1, sport="bike", dur=5400), act(id=2, sport="run", dur=1600)]
    assert session_status(s, day, TODAY) == "completed"  # 1600/1800 = 89%


def test_brick_partial_when_run_too_short():
    s = sess(sport="brick", target=1800)
    day = [act(id=1, sport="bike", dur=5400), act(id=2, sport="run", dur=1200)]
    assert session_status(s, day, TODAY) == "partial"  # 1200/1800 = 67%


def test_brick_only_bike_is_partial_when_day_over_not_missed():
    s = sess(sport="brick", target=1800, local_date=D_PAST)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) == "partial"


def test_brick_only_bike_stays_open_while_day_not_over():
    s = sess(sport="brick", target=1800, local_date=TODAY)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) is None


def test_brick_missed_without_any_activity():
    s = sess(sport="brick", target=1800, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "missed"


def test_multisport_three_sports_completed():
    s = sess(sport="multisport", target=10800)
    day = [act(id=1, sport="swim", dur=1800), act(id=2, sport="bike", dur=5400),
           act(id=3, sport="run", dur=2400)]
    assert session_status(s, day, TODAY) == "completed"  # 9600/10800 = 89%


def test_multisport_one_sport_is_partial_when_day_over():
    s = sess(sport="multisport", target=10800, local_date=D_PAST)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) == "partial"


def test_multisport_missed_without_any_activity():
    s = sess(sport="multisport", target=10800, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "missed"


def test_status_by_distance_when_no_duration_target():
    s = sess(target=None, distance_target=3000)
    assert session_status(s, [act(dur=1500, distance_m=2600)], TODAY) == "completed"  # 87%
    assert session_status(s, [act(dur=1500, distance_m=2000)], TODAY) == "partial"    # 67%


def test_status_completed_when_no_duration_and_no_distance_target():
    s = sess(target=None, distance_target=None)
    assert session_status(s, [act()], TODAY) == "completed"


def test_status_is_idempotent_given_same_inputs():
    s = sess(target=2100)
    linked = [act(dur=1700)]
    first = session_status(s, linked, TODAY)
    second = session_status(s, linked, TODAY)
    assert first == second == "completed"


def test_brick_run_link_agafa_la_cursa_curta_no_aparellada():
    from ingest.link import brick_run_link
    brick = sess(10, "brick", 600)
    acts = [act(1, "bike", 4432), act(2, "run", 827)]
    # la bici ja va a la sessió de bici; la cursa curta és el tram a peu del brick
    assert brick_run_link(brick, acts, matched_ids={1}) == 2
    # si la cursa ja s'ha aparellat amb una sessió de cursa del dia, no es roba
    assert brick_run_link(brick, acts, matched_ids={1, 2}) is None
    # sense cursa, res
    assert brick_run_link(brick, [act(1, "bike", 4432)], matched_ids=set()) is None


# --- vincle explícit de l'atleta (fila manual amb plan_session_id) ---------

class FakeConn:
    """Respon les dues selects de run_linking i recorda els updates."""

    def __init__(self, sessions, activities):
        self._sessions = sessions
        self._activities = activities
        self.updates = []

    def execute(self, sql, params=None):
        if "from plan_session" in sql:
            rows = [(s["id"], s["local_date"], s["sport"], s["duration_sec_target"],
                     s["distance_m_target"], s["planned_load"], s["status"])
                    for s in self._sessions]
        elif "from activity" in sql:
            rows = [(a["id"], a["local_date"], a["sport"], a["duration_sec"],
                     a["distance_m"], a["load"], a.get("plan_session_id"),
                     a.get("manual", False), a.get("linked_by_athlete", False))
                    for a in self._activities]
        else:
            self.updates.append((sql.split()[1], params))
            rows = []
        return iter(rows)


def dbsess(status="planned", **kw):
    return {**sess(**kw), "status": status}


def dbact(local_date, plan_session_id=None, manual=False, linked_by_athlete=False, **kw):
    return {**act(**kw), "local_date": local_date, "plan_session_id": plan_session_id,
            "manual": manual, "linked_by_athlete": linked_by_athlete}


def test_manual_amb_sessio_explicita_compta_encara_que_sigui_d_un_altre_dia():
    from ingest.link import run_linking
    # sessió del 10/09 feta l'11 i registrada des de l'app amb plan_session_id
    s = dbsess(id=43, local_date=date(2026, 9, 10), target=2400, status="missed")
    a = dbact(date(2026, 9, 11), id=-202609111, dur=2400, plan_session_id=43, manual=True)
    conn = FakeConn([s], [a])
    r = run_linking(conn, today=date(2026, 9, 12))
    assert r["completed"] == 1
    assert ("plan_session", ("completed", 43)) in conn.updates


def test_el_vincle_explicit_guanya_a_la_durada_mes_propera():
    from ingest.link import run_linking
    day = date(2026, 9, 10)
    a_sess = dbsess(id=1, target=1500)   # durada més propera a l'activitat
    b_sess = dbsess(id=2, target=3600)   # la que l'atleta ha triat
    a = dbact(day, id=-1, dur=1500, plan_session_id=2, manual=True)
    for s in (a_sess, b_sess):
        s["local_date"] = day
    conn = FakeConn([a_sess, b_sess], [a])
    r = run_linking(conn, today=date(2026, 9, 12))
    # la 2 rep l'activitat (partial: 1500 < 80% de 3600); la 1 queda missed
    assert r == {"links": 0, "completed": 0, "partial": 1, "missed": 1}
    assert ("plan_session", ("partial", 2)) in conn.updates
    assert ("plan_session", ("missed", 1)) in conn.updates
    # i no es reescriu el plan_session_id que l'atleta va posar
    assert not any(t == "activity" for t, _ in conn.updates)


def test_una_activitat_de_garmin_del_dia_segueix_anant_per_heuristica():
    from ingest.link import run_linking
    day = date(2026, 9, 10)
    s = dbsess(id=5, local_date=day, target=2400)
    a = dbact(day, id=100, dur=2300)   # de Garmin: sense plan_session_id, no manual
    conn = FakeConn([s], [a])
    r = run_linking(conn, today=date(2026, 9, 12))
    assert r["links"] == 1 and r["completed"] == 1
    assert ("activity", (5, 100)) in conn.updates


def test_multisport_compta_un_tram_manual_registrat_un_altre_dia():
    from ingest.link import run_linking
    day = date(2026, 9, 12)
    s = dbsess(id=45, sport="multisport", local_date=day, target=7200)
    bike = dbact(day, id=1, sport="bike", dur=4031)
    run = dbact(day, id=2, sport="run", dur=697)
    # la natació es va registrar l'endemà des de l'app, lligada al simulacre
    swim = dbact(date(2026, 9, 13), id=-3, sport="swim", dur=1110, plan_session_id=45, manual=True)
    conn = FakeConn([s], [bike, run, swim])
    r = run_linking(conn, today=date(2026, 9, 14))
    # 3 esports, 5838 s >= 80% de 7200 -> completed (sense la natació seria partial)
    assert r["completed"] == 1
    assert ("plan_session", ("completed", 45)) in conn.updates


# --- l'atleta corregeix des de l'app (linked_by_athlete) ---------------------

def test_dies_intercanviats_cada_activitat_de_garmin_compta_per_la_sessio_triada():
    from ingest.link import run_linking
    sat, sun = date(2026, 10, 3), date(2026, 10, 4)
    run_sess = dbsess(id=82, sport="run", local_date=sat, target=1200, status="missed")
    bike_sess = dbsess(id=83, sport="bike", local_date=sun, target=1800, status="missed")
    bike = dbact(sat, id=24594273597, sport="bike", dur=3601, plan_session_id=83, linked_by_athlete=True)
    run = dbact(sun, id=24598098311, sport="run", dur=3219, plan_session_id=82, linked_by_athlete=True)
    conn = FakeConn([run_sess, bike_sess], [bike, run])
    r = run_linking(conn, today=date(2026, 10, 5))
    assert r == {"links": 0, "completed": 2, "partial": 0, "missed": 0}
    assert ("plan_session", ("completed", 82)) in conn.updates
    assert ("plan_session", ("completed", 83)) in conn.updates
    assert not any(t == "activity" for t, _ in conn.updates)   # no es reescriu el vincle


def test_fora_de_pla_per_decisio_de_l_atleta_no_s_aparella_sola():
    from ingest.link import run_linking
    day = date(2026, 10, 3)
    s = dbsess(id=5, sport="bike", local_date=day, target=3600)
    a = dbact(day, id=100, sport="bike", dur=3600, linked_by_athlete=True)   # plan_session_id null
    conn = FakeConn([s], [a])
    r = run_linking(conn, today=date(2026, 10, 5))
    assert r["links"] == 0 and r["missed"] == 1


def test_una_sessio_d_avui_que_perd_la_seva_activitat_torna_a_pendent():
    from ingest.link import run_linking
    today = date(2026, 10, 4)
    s = dbsess(id=83, sport="bike", local_date=today, target=1800, status="completed")
    conn = FakeConn([s], [])    # l'activitat s'ha esborrat o s'ha assignat a una altra
    r = run_linking(conn, today=today)
    assert ("plan_session", ("planned", 83)) in conn.updates
    # i una de passada, missed
    s_past = dbsess(id=82, sport="run", local_date=date(2026, 10, 3), target=1200, status="completed")
    conn = FakeConn([s_past], [])
    run_linking(conn, today=today)
    assert ("plan_session", ("missed", 82)) in conn.updates


def test_un_multisport_no_compta_una_activitat_del_dia_que_l_atleta_ha_enviat_a_una_altra_sessio():
    from ingest.link import run_linking
    day = date(2026, 9, 12)
    multi = dbsess(id=45, sport="multisport", local_date=day, target=7200)
    bike = dbact(day, id=1, sport="bike", dur=4031)
    run = dbact(day, id=2, sport="run", dur=3000, plan_session_id=99, linked_by_athlete=True)
    other = dbsess(id=99, sport="run", local_date=date(2026, 9, 13), target=3000)
    conn = FakeConn([multi, other], [bike, run])
    run_linking(conn, today=date(2026, 9, 14))
    # sense la cursa, el multisport només té bici -> partial; la cursa completa la 99
    assert ("plan_session", ("partial", 45)) in conn.updates
    assert ("plan_session", ("completed", 99)) in conn.updates
