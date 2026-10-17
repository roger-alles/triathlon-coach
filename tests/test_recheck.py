"""Tests de la revisió del matí (coach/recheck.py).

Després de cada sync horari, fins a les 12:00: si l'informe del matí es va fer
amb un son que ara ha canviat (≥ 1 h o ≥ 15 de body battery), es refà UN cop.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.recheck import changed_inputs, recheck_decision

TZ = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 10, 17)


def _local(h, m):
    return datetime(2026, 10, 17, h, m, tzinfo=TZ)


def _report(sleep_h, bb_max, local_date="2026-10-17"):
    return {"id": 104, "created_at": _local(6, 1),
            "snapshot": {"recovery_last_14d": [
                {"local_date": "2026-10-16", "sleep_h": 8.1, "body_battery_max": 94},
                {"local_date": local_date, "sleep_h": sleep_h, "body_battery_max": bb_max}]}}


def test_cas_real_del_17_10_refà():
    # Informe de les 06:01 amb 4,2 h i body battery 58; a les 09:01, 9,5 h i 90
    redo, reason = recheck_decision(TODAY, _local(9, 1), TZ, [_report(4.2, 58)],
                                    {"sleep_h": 9.5, "body_battery_max": 90})
    assert redo is True
    assert "son 4,2 h → 9,5 h" in reason
    assert "body battery màxima 58 → 90" in reason


def test_mateixes_dades_no_refà():
    redo, reason = recheck_decision(TODAY, _local(9, 1), TZ, [_report(8.1, 94)],
                                    {"sleep_h": 8.1, "body_battery_max": 94})
    assert redo is False
    assert "no han canviat" in reason


def test_canvis_petits_no_refan():
    # Garmin reajusta uns minuts de son o uns punts de bateria: soroll
    redo, _ = recheck_decision(TODAY, _local(9, 1), TZ, [_report(7.4, 88)],
                               {"sleep_h": 8.3, "body_battery_max": 100})
    assert redo is False


def test_una_hora_de_son_ja_refà():
    redo, _ = recheck_decision(TODAY, _local(9, 1), TZ, [_report(7.0, 90)],
                               {"sleep_h": 8.0, "body_battery_max": 90})
    assert redo is True


def test_nomes_la_body_battery_tambe_refà():
    redo, reason = recheck_decision(TODAY, _local(9, 1), TZ, [_report(8.0, 60)],
                                    {"sleep_h": 8.0, "body_battery_max": 85})
    assert redo is True
    assert reason == "body battery màxima 60 → 85"


def test_mai_mes_d_una_correccio_al_dia():
    reports = [_report(4.2, 58), _report(6.0, 70)]
    redo, reason = recheck_decision(TODAY, _local(10, 1), TZ, reports,
                                    {"sleep_h": 9.5, "body_battery_max": 90})
    assert redo is False
    assert "un cop" in reason


def test_sense_informe_del_mati_no_fa_res():
    redo, _ = recheck_decision(TODAY, _local(7, 1), TZ, [],
                               {"sleep_h": 9.5, "body_battery_max": 90})
    assert redo is False


def test_a_partir_de_les_12_no_corregeix():
    redo, _ = recheck_decision(TODAY, _local(12, 1), TZ, [_report(4.2, 58)],
                               {"sleep_h": 9.5, "body_battery_max": 90})
    assert redo is False


def test_les_12_es_comparen_en_hora_local_no_utc():
    # 10:01 UTC són les 12:01 a Madrid a l'estiu: massa tard
    now = datetime(2026, 10, 17, 10, 1, tzinfo=timezone.utc)
    redo, _ = recheck_decision(TODAY, now, TZ, [_report(4.2, 58)],
                               {"sleep_h": 9.5, "body_battery_max": 90})
    assert redo is False


def test_informe_fet_sense_son_i_ara_n_hi_ha_refà():
    # Forçat (COACH_FORCE=1) abans que Garmin tingués la nit
    redo, reason = recheck_decision(TODAY, _local(9, 1), TZ, [_report(None, None)],
                                    {"sleep_h": 8.0, "body_battery_max": 92})
    assert redo is True
    assert "son ? → 8 h" in reason


def test_snapshot_sense_el_dia_d_avui_compta_com_sense_dades():
    redo, _ = recheck_decision(TODAY, _local(9, 1), TZ,
                               [_report(8.0, 92, local_date="2026-10-16")],
                               {"sleep_h": 8.0, "body_battery_max": 92})
    assert redo is True


def test_sense_metriques_d_avui_no_refà():
    assert changed_inputs({"sleep_h": 4.2, "body_battery_max": 58}, None) is None


def test_valors_decimal_de_la_bd():
    # psycopg retorna numeric com a Decimal
    from decimal import Decimal
    assert changed_inputs({"sleep_h": 4.2, "body_battery_max": 58},
                          {"sleep_h": Decimal("9.5"), "body_battery_max": 90}) is not None
