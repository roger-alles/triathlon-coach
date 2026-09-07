"""Tests de la porta del matí (coach/gate.py).

L'informe del matí només té sentit amb el son d'aquesta nit: Garmin el publica
quan el rellotge sincronitza amb el mòbil, sovint hores després de les 06:15.
La feina programada s'executa cada 20 min i aquesta porta decideix si toca
generar l'informe (son present i cap informe d'avui encara) o esperar.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.gate import local_today, morning_decision

TZ = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 9, 7)
MIDNIGHT = datetime(2026, 9, 7, 0, 0, tzinfo=TZ)


def test_sense_son_espera():
    run, reason = morning_decision(TODAY, sleep_sec=None, last_report_at=None, tz=TZ)
    assert run is False
    assert "son" in reason


def test_son_zero_compta_com_absent():
    # Garmin retorna sleepingSeconds=0 mentre no ha rebut la nit
    run, _ = morning_decision(TODAY, sleep_sec=0, last_report_at=None, tz=TZ)
    assert run is False


def test_son_present_i_cap_informe_genera():
    run, reason = morning_decision(TODAY, sleep_sec=30120, last_report_at=None, tz=TZ)
    assert run is True
    assert "8.4" in reason


def test_informe_ja_generat_avui_no_repeteix():
    at = datetime(2026, 9, 7, 11, 52, tzinfo=TZ)
    run, reason = morning_decision(TODAY, sleep_sec=30120, last_report_at=at, tz=TZ)
    assert run is False
    assert "11:52" in reason


def test_preview_del_vespre_anterior_no_bloqueja():
    # El vespre del dia 6 crea un informe amb window_start=7: no és el del matí del 7
    at = datetime(2026, 9, 6, 21, 32, tzinfo=TZ)
    run, _ = morning_decision(TODAY, sleep_sec=30120, last_report_at=at, tz=TZ)
    assert run is True


def test_informe_avui_comparat_en_hora_local_no_utc():
    # 23:30 UTC del dia 6 és 01:30 del dia 7 a Madrid: ja és "avui"
    at = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
    run, _ = morning_decision(TODAY, sleep_sec=30120, last_report_at=at, tz=TZ)
    assert run is False


def test_force_salta_la_porta_pero_no_el_son():
    run, reason = morning_decision(TODAY, sleep_sec=30120,
                                   last_report_at=MIDNIGHT + timedelta(hours=9),
                                   tz=TZ, force=True)
    assert run is True
    assert "forç" in reason
    run, _ = morning_decision(TODAY, sleep_sec=None, last_report_at=None, tz=TZ, force=True)
    assert run is True  # forçar és decisió humana: es genera, i el coach dirà que no té son


def test_local_today_usa_la_zona_de_l_atleta():
    # 23:30 UTC del 6 és ja dia 7 a Madrid: un servidor en UTC no ha de confondre's
    now = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
    assert local_today(TZ, now=now) == date(2026, 9, 7)
