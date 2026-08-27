"""F0 — Explorar Garmin Connect.

Script solt (spec §10, fase F0): fa login, baixa els últims 90 dies de dades
reals i les desa com a JSON cru a `data/raw/`. No transforma res: l'objectiu
és veure què ofereix cada endpoint abans de dissenyar la ingesta de la F1.

Ús:
    .venv/bin/python f0_explore.py            # baixa el que falti
    .venv/bin/python f0_explore.py --force    # torna a baixar-ho tot

El primer login demana la contrasenya del `.env` i, si el compte té MFA,
el codi per teclat. Després queden tokens a ~/.garminconnect i la
contrasenya ja no es fa servir.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
TOKENSTORE = "~/.garminconnect"
DAYS = 90
PAUSE_SEC = 0.5  # amable amb el servidor (spec §9)

# Endpoints diaris a explorar: carpeta de sortida -> nom del mètode de la llibreria.
# Si un mètode no existeix en aquesta versió, s'apunta a errors.log i se segueix.
DAILY_ENDPOINTS = {
    "sleep": "get_sleep_data",
    "hrv": "get_hrv_data",
    "stats": "get_stats",
    "rhr": "get_rhr_day",
    "body_battery": "get_body_battery",
    "training_readiness": "get_training_readiness",
    "training_status": "get_training_status",
}

# Detall de les activitats de mostra: candidats per nom (varien entre versions).
ACTIVITY_DETAIL_METHODS = [
    "get_activity",
    "get_activity_details",
    "get_activity_splits",
    "get_activity_hr_in_timezones",
]


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


def save_json(base: Path, folder: str, name: str, payload) -> None:
    directory = base / folder
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / f"{name}.json", "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def log_error(message: str) -> None:
    print(f"  ERROR: {message}")
    with open(RAW / "errors.log", "a") as f:
        f.write(message + "\n")


def get_client() -> Garmin:
    """Login via login(tokenstore): usa tokens desats si n'hi ha; si no, fa el
    login amb email/password del .env i la llibreria mateixa desa els tokens."""
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    had_tokens = (Path(TOKENSTORE).expanduser() / "garmin_tokens.json").exists()

    if not had_tokens and not (email and password):
        sys.exit(
            "No hi ha tokens desats ni credencials.\n"
            "Copia .env.example com a .env i omple GARMIN_EMAIL i GARMIN_PASSWORD."
        )

    client = Garmin(email=email, password=password,
                    prompt_mfa=lambda: input("Codi MFA: "))
    client.login(TOKENSTORE)
    if had_tokens:
        print("Login amb tokens desats (sense contrasenya).")
    else:
        print(f"Login inicial correcte. Tokens desats a {TOKENSTORE}.")
    return client


def discover_methods(client: Garmin) -> None:
    """Desa la llista de mètodes get_* disponibles (spec §9: descobrir, no suposar)."""
    methods = sorted(m for m in dir(client) if m.startswith("get_"))
    save_json(RAW, "meta", "available_methods", methods)
    print(f"{len(methods)} mètodes get_* disponibles -> data/raw/meta/")


def fetch_activities(client: Garmin, start: date, end: date) -> list:
    activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
    save_json(RAW, "activities", "_index", activities)
    print(f"{len(activities)} activitats entre {start} i {end}")
    for a in activities:
        save_json(RAW, "activities", str(a["activityId"]), a)
    return activities


def fetch_sample_details(client: Garmin, activities: list, force: bool) -> None:
    """Detall complet només de les 5 més recents: mostres per documentar camps."""
    for a in activities[:5]:
        act_id = a["activityId"]
        for method_name in ACTIVITY_DETAIL_METHODS:
            if not hasattr(client, method_name):
                log_error(f"mètode inexistent en aquesta versió: {method_name}")
                continue
            out_file = RAW / "activity_detail" / f"{act_id}_{method_name}.json"
            if out_file.exists() and not force:
                continue
            try:
                payload = getattr(client, method_name)(act_id)
                save_json(RAW, "activity_detail", f"{act_id}_{method_name}", payload)
                time.sleep(PAUSE_SEC)
            except Exception as e:
                log_error(f"{method_name}({act_id}): {e}")
        print(f"  detall de {act_id} baixat")


def fetch_daily_metrics(client: Garmin, start: date, end: date, force: bool) -> None:
    days = date_range(start, end)
    for folder, method_name in DAILY_ENDPOINTS.items():
        if not hasattr(client, method_name):
            log_error(f"mètode inexistent en aquesta versió: {method_name}")
            continue
        method = getattr(client, method_name)
        pending = [d for d in days
                   if force or not (RAW / folder / f"{d.isoformat()}.json").exists()]
        print(f"{folder}: {len(pending)} dies per baixar")
        for d in pending:
            try:
                save_json(RAW, folder, d.isoformat(), method(d.isoformat()))
            except Exception as e:
                log_error(f"{method_name}({d}): {e}")
            time.sleep(PAUSE_SEC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="torna a baixar encara que el fitxer ja existeixi")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    RAW.mkdir(parents=True, exist_ok=True)

    client = get_client()
    discover_methods(client)

    end = date.today()
    start = end - timedelta(days=DAYS)

    activities = fetch_activities(client, start, end)
    fetch_sample_details(client, activities, args.force)
    fetch_daily_metrics(client, start, end, args.force)

    errors = RAW / "errors.log"
    if errors.exists():
        print(f"\nAcabat AMB ERRORS — revisa {errors}")
    else:
        print("\nAcabat sense errors.")


if __name__ == "__main__":
    main()
