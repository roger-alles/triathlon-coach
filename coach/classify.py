"""Auto o proposta? Regla determinista sobre els canvis d'un informe (docs/post-cursa-design.md).

El model no decideix si un canvi s'aplica sol: ho decideix aquesta regla, al
codi, i el resultat es desa a coach_report.classification perquè l'atleta
vegi per què. Automàtic NOMÉS si tot es compleix:
  - cap violació bloquejant del validador
  - com a molt 2 sessions afectades
  - horitzó de 3 dies (la data més llunyana tocada, incloent-hi new_date)
  - accions: modificar, moure dins la mateixa setmana i cap endavant,
    cancel·lar una sessió que no sigui clau
  - la càrrega total i la càrrega dura de les sessions afectades no pugen
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from coach.models import Session, Violation
from coach.rules import _monday, session_easy_hard, session_seconds

MAX_SESSIONS = 2
MAX_HORIZON_DAYS = 3


@dataclass
class Classification:
    auto: bool
    reasons: list[str]
    horizon_days: int
    n_sessions: int
    load_before_sec: float
    load_after_sec: float
    hard_before_sec: float
    hard_after_sec: float

    def to_dict(self) -> dict:
        return asdict(self)


def _after(session: Session | None, change: dict, blocks) -> Session | None:
    """La sessió tal com quedaria (None si es cancel·la; nova si és un add)."""
    from coach.run import apply_changes  # import tardà: run importa classify
    result = apply_changes([session] if session else [], [change], blocks)
    return result[0] if result else None


def classify(changes: list[dict], plan_by_id: dict[int, Session], today: date,
             blocking: list[Violation], blocks=None) -> Classification:
    affected = [c for c in changes if c["action"] != "keep"]
    reasons = [f"{v.rule}: {v.message}" for v in blocking]
    horizon = 0
    load_before = load_after = hard_before = hard_after = 0.0

    for change in affected:
        action = change["action"]
        before = None if action == "add" else plan_by_id[change["plan_session_id"]]
        after = _after(before, change, blocks)
        dates = ([before.local_date] if before else []) + ([after.local_date] if after else [])
        horizon = max(horizon, max((d - today).days for d in dates))
        if action == "add":
            reasons.append(f"afegeix una sessió ({after.title}): no és automàtic")
        elif action == "cancel" and before.priority == "key":
            reasons.append(f"cancel·la una sessió clau ({before.title})")
        elif action == "move":
            new_date = date.fromisoformat(change["new_date"])
            if _monday(new_date) != _monday(before.local_date):
                reasons.append(f"mou {before.title} a una altra setmana")
            elif new_date < today:
                reasons.append(f"mou {before.title} al passat")
        elif action not in ("modify", "replace", "cancel"):
            reasons.append(f"acció {action} no és automàtica")
        if before:
            load_before += session_seconds(before)
            hard_before += session_easy_hard(before)[1]
        if after:
            load_after += session_seconds(after)
            hard_after += session_easy_hard(after)[1]

    if len(affected) > MAX_SESSIONS:
        reasons.append(f"{len(affected)} sessions afectades (màxim {MAX_SESSIONS})")
    if horizon > MAX_HORIZON_DAYS:
        reasons.append(f"horitzó de {horizon} dies (màxim {MAX_HORIZON_DAYS})")
    if load_after > load_before:
        reasons.append("puja la càrrega total")
    if hard_after > hard_before:
        reasons.append("puja la càrrega dura")

    return Classification(auto=not reasons, reasons=reasons, horizon_days=horizon,
                          n_sessions=len(affected), load_before_sec=load_before,
                          load_after_sec=load_after, hard_before_sec=hard_before,
                          hard_after_sec=hard_after)
