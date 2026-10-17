"""Tests de la porta del matí (coach/gate.py).

L'informe del matí només té sentit amb el son d'aquesta nit: Garmin el publica
quan el rellotge sincronitza amb el mòbil, sovint hores després de les 06:15.
La feina s'intenta cada 5 min i aquesta porta decideix, en aquest ordre i
parant al primer "no": (1) ¿ja hi ha informe del matí avui? (base de dades,
zero peticions a Garmin) → (2) ¿Garmin té el son d'avui? → (3) ¿l'última
sincronització és de les 06:00 o més tard? (si no, va ser de nit i el son pot
ser parcial) → genera. A partir de les 10:00 genera igualment.
Després de l'informe, la resta del matí no toca Garmin.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.gate import local_today, morning_decision
from ingest.providers.garmin import SleepStatus

TZ = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 9, 7)
MIDNIGHT = datetime(2026, 9, 7, 0, 0, tzinfo=TZ)
AT_0600 = MIDNIGHT + timedelta(hours=6)


def _local(h, m):
    return MIDNIGHT + timedelta(hours=h, minutes=m)


# Despertat a les 07:04, el mòbil ha sincronitzat a les 07:40: son sencer
COMPLETE = SleepStatus(30120, end=_local(7, 4), last_sync=_local(7, 40))


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


def test_son_present_i_cap_informe_genera():
    run, reason = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(COMPLETE), tz=TZ, now=AT_0600)
    assert run is True
    assert "8.4" in reason


def test_informe_ja_generat_avui_no_repeteix_i_no_toca_garmin():
    at = datetime(2026, 9, 7, 7, 52, tzinfo=TZ)
    sleep = _Sleep(COMPLETE)
    run, reason = morning_decision(TODAY, last_report_at=at, sleep=sleep, tz=TZ, now=AT_0600)
    assert run is False
    assert "07:52" in reason
    assert sleep.calls == 0  # primer la BD; si ja hi ha informe, cap petició a Garmin


def test_sense_informe_consulta_garmin_un_cop():
    sleep = _Sleep(COMPLETE)
    morning_decision(TODAY, last_report_at=None, sleep=sleep, tz=TZ, now=AT_0600)
    assert sleep.calls == 1


def test_preview_del_vespre_anterior_no_bloqueja():
    # El vespre del dia 6 crea un informe amb window_start=7: no és el del matí del 7
    at = datetime(2026, 9, 6, 21, 32, tzinfo=TZ)
    run, _ = morning_decision(TODAY, last_report_at=at, sleep=_Sleep(COMPLETE), tz=TZ, now=AT_0600)
    assert run is True


def test_informe_avui_comparat_en_hora_local_no_utc():
    # 23:30 UTC del dia 6 és 01:30 del dia 7 a Madrid: ja és "avui"
    at = datetime(2026, 9, 6, 23, 30, tzinfo=timezone.utc)
    run, _ = morning_decision(TODAY, last_report_at=at, sleep=_Sleep(COMPLETE), tz=TZ, now=AT_0600)
    assert run is False


def test_son_parcial_de_sincronitzacio_a_mitja_nit_espera():
    # Cas real del 17/10: a les 06:00 Garmin tenia 4,2 h (de 9,5) perquè el mòbil
    # havia sincronitzat a les 02:53, mentre en Roger dormia
    partial = SleepStatus(15120, end=_local(2, 53), last_sync=_local(2, 54))
    run, reason = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(partial),
                                   tz=TZ, now=AT_0600)
    assert run is False
    assert "parcial" in reason
    assert "02:54" in reason  # el log ha de deixar veure per què espera


def test_sincronitzacio_just_en_despertar_genera_a_l_acte():
    # Despertat a les 07:04 i sincronitzat a les 07:05: no cal esperar res més
    status = SleepStatus(30120, end=_local(7, 4), last_sync=_local(7, 5))
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(status),
                              tz=TZ, now=_local(7, 10))
    assert run is True


def test_sincronitzacio_a_les_6_en_punt_ja_compta():
    status = SleepStatus(30120, end=_local(5, 58), last_sync=_local(6, 0))
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(status),
                              tz=TZ, now=_local(6, 5))
    assert run is True


def test_despertar_molt_d_hora_espera_una_sincronitzacio_de_matí():
    # Dia de viatge: llevat a les 03:14 i sincronitzat a les 03:20. No es pot
    # distingir d'una sincronització de nit: s'espera la següent (o les 10:00)
    status = SleepStatus(17760, end=_local(3, 14), last_sync=_local(3, 20))
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(status),
                              tz=TZ, now=_local(6, 30))
    assert run is False


def test_sincronitzacio_en_utc_es_compara_en_hora_local():
    # 04:30 UTC són les 06:30 a Madrid a l'estiu: ja és de matí
    status = SleepStatus(30120, end=_local(6, 20),
                         last_sync=datetime(2026, 9, 7, 4, 30, tzinfo=timezone.utc))
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(status),
                              tz=TZ, now=_local(6, 35))
    assert run is True


def test_sense_hora_de_sincronitzacio_espera_fins_al_limit():
    status = SleepStatus(30120, end=_local(7, 4), last_sync=None)
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(status),
                              tz=TZ, now=_local(9, 55))
    assert run is False


def test_passades_les_10_genera_encara_que_el_son_sigui_dubtos():
    # Millor un informe amb el son dubtós (i el motiu al log) que cap informe;
    # si era parcial, coach.recheck el corregeix
    partial = SleepStatus(15120, end=_local(2, 53), last_sync=_local(2, 54))
    run, reason = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(partial),
                                   tz=TZ, now=_local(10, 0))
    assert run is True
    assert "potser incomplet" in reason


def test_limit_de_les_10_en_hora_local_no_utc():
    # 08:30 UTC són les 10:30 a Madrid a l'estiu: ja ha passat el límit
    partial = SleepStatus(15120, end=_local(2, 53), last_sync=_local(2, 54))
    now = datetime(2026, 9, 7, 8, 30, tzinfo=timezone.utc)
    run, _ = morning_decision(TODAY, last_report_at=None, sleep=_Sleep(partial),
                              tz=TZ, now=now)
    assert run is True


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
