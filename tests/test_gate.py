"""Tests de la porta del matí (coach/gate.py).

L'informe del matí només té sentit amb el son d'aquesta nit: Garmin el publica
quan el rellotge sincronitza amb el mòbil, sovint hores després de les 06:15.
La feina s'intenta cada 5 min i aquesta porta decideix, en aquest ordre i
parant al primer "no": (1) ¿ja hi ha informe del matí avui? (base de dades,
zero peticions a Garmin) → (2) ¿Garmin té el son d'avui? (una petició) →
genera. Després de l'informe, la resta del matí no toca Garmin.
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


class _Sleep:
    """Font de son comptabilitzada: la porta només l'ha de consultar si cal."""
    def __init__(self, value):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


def test_sense_son_espera():
    run, reason = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(None), tz=TZ)
    assert run is False
    assert "son" in reason


def test_son_zero_compta_com_absent():
    # Garmin retorna sleepTimeSeconds=0 mentre no ha rebut la nit
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(0), tz=TZ)
    assert run is False


def test_son_present_i_cap_informe_genera():
    run, reason = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(30120), tz=TZ)
    assert run is True
    assert "8.4" in reason


def test_informe_ja_generat_avui_no_repeteix_i_no_toca_garmin():
    at = datetime(2026, 9, 7, 7, 52, tzinfo=TZ)
    sleep = _Sleep(30120)
    run, reason = morning_decision(TODAY, last_report_at=at, sleep=sleep, tz=TZ)
    assert run is False
    assert "07:52" in reason
    assert sleep.calls == 0  # primer la BD; si ja hi ha informe, cap petició a Garmin


def test_sense_informe_consulta_garmin_un_cop():
    sleep = _Sleep(30120)
    morning_decision(TODAY, last_report_at=None, sleep=sleep, tz=TZ)
    assert sleep.calls == 1


def test_preview_del_vespre_anterior_no_bloqueja():
    # El vespre del dia 6 crea un informe amb window_start=7: no és el del matí del 7
    at = datetime(2026, 9, 6, 21, 32, tzinfo=TZ)
    run, _ = morning_decision(TODAY, last_report_at=at, sleep=_Sleep(30120), tz=TZ)
    assert run is True


def test_informe_avui_comparat_en_hora_local_no_utc():
    # 23:30 UTC del dia 6 és 01:30 del dia 7 a Madrid: ja és "avui"
    at = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
    run, _ = morning_decision(TODAY, last_report_at=at, sleep=_Sleep(30120), tz=TZ)
    assert run is False


def test_force_salta_la_porta_sense_consultar_res():
    sleep = _Sleep(None)
    run, reason = morning_decision(TODAY, last_report_at=MIDNIGHT + timedelta(hours=9),
                                   sleep=sleep, tz=TZ, force=True)
    assert run is True
    assert "forç" in reason
    assert sleep.calls == 0  # forçar és decisió humana: es genera i el coach dirà què li falta


def test_local_today_usa_la_zona_de_l_atleta():
    # 23:30 UTC del 6 és ja dia 7 a Madrid: un servidor en UTC no ha de confondre's
    now = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
    assert local_today(TZ, now=now) == date(2026, 9, 7)
