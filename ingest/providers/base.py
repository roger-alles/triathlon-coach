"""Protocol del proveïdor de dades d'entrenament (spec §2).

Tot el que sap parlar amb Garmin queda darrere d'aquesta interfície: quan
l'autenticació no oficial es trenqui (passarà), es substitueix el proveïdor
per Intervals.icu o per fitxers .FIT sense tocar sync ni res més.
"""

from datetime import date
from typing import Protocol, runtime_checkable


@runtime_checkable
class ActivityProvider(Protocol):
    def fetch_activities(self, start: date, end: date) -> list[dict]:
        """Resums d'activitat crus del proveïdor, de start a end inclosos."""
        ...

    def fetch_daily(self, day: date) -> dict:
        """Mètriques de recuperació crues d'un dia."""
        ...
