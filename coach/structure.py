"""Validador del contracte de sessió (spec §6).

Un pas té exactament un de duration_sec/distance_m; els targets són d'un
catàleg tancat; els que depenen d'un llindar (ftp_pct, css_pct,
pace_pct_threshold) es rebutgen si l'atleta no té el llindar mesurat.
El JSON Schema equivalent viu a contracts/session-structure.schema.json.
"""

from coach.models import Athlete

ALLOWED_TARGETS = {"hr_zone", "ftp_pct", "pace_sec_km", "pace_pct_threshold",
                   "css_pct", "pace_sec_100m", "rpe", "open"}
THRESHOLD_REQUIRED = {"ftp_pct": "ftp_watts",
                      "css_pct": "css_sec_per_100m",
                      "pace_pct_threshold": "threshold_pace_sec_km"}
SEGMENT_SPORTS = {"swim", "bike", "run", "transition"}


def validate_structure(structure: dict, sport: str, athlete: Athlete) -> list[str]:
    errors: list[str] = []
    if sport == "multisport":
        segments = structure.get("segments")
        if not isinstance(segments, list) or not segments:
            return ["multisport sense 'segments'"]
        for i, seg in enumerate(segments):
            _check_segment(seg, i, athlete, errors)
        return errors

    steps = structure.get("steps")
    if steps is None:
        return ["sense 'steps'"]
    if sport == "rest":
        return errors  # descans: steps buits permesos
    for i, step in enumerate(steps):
        _check_step(step, f"steps[{i}]", athlete, errors, require_target=True)
    return errors


def _check_step(step: dict, where: str, athlete: Athlete,
                errors: list[str], require_target: bool) -> None:
    if "repeats" in step:
        work = step.get("work")
        if not work:
            errors.append(f"{where}: repeats sense 'work'")
            return
        _check_step(work, f"{where}.work", athlete, errors, require_target=True)
        if step.get("recovery"):
            # la recuperació pot ser només una pausa: target opcional
            _check_step(step["recovery"], f"{where}.recovery", athlete, errors,
                        require_target=False)
        return

    has_duration = step.get("duration_sec") is not None
    has_distance = step.get("distance_m") is not None
    if has_duration == has_distance:
        errors.append(f"{where}: cal exactament un de duration_sec/distance_m")

    target = step.get("target")
    if target is None:
        if require_target:
            errors.append(f"{where}: sense target")
    else:
        _check_target(target, where, athlete, errors)


def _check_target(target: dict, where: str, athlete: Athlete,
                  errors: list[str]) -> None:
    ttype = target.get("type")
    if ttype not in ALLOWED_TARGETS:
        errors.append(f"{where}: target.type '{ttype}' no admès")
        return
    if ttype in THRESHOLD_REQUIRED:
        attr = THRESHOLD_REQUIRED[ttype]
        if getattr(athlete, attr) is None:
            errors.append(f"{where}: target '{ttype}' requereix {attr} "
                          f"i l'atleta no el té mesurat")
    value = target.get("value", 0)
    if ttype == "hr_zone" and not 1 <= value <= 5:
        errors.append(f"{where}: hr_zone {value} fora de 1-5")
    if ttype == "rpe" and not 1 <= value <= 10:
        errors.append(f"{where}: rpe {value} fora de 1-10")


def _check_segment(seg: dict, i: int, athlete: Athlete, errors: list[str]) -> None:
    sport = seg.get("sport")
    if sport not in SEGMENT_SPORTS:
        errors.append(f"segments[{i}]: sport '{sport}' no admès")
        return
    if sport == "transition":
        if seg.get("transition") not in ("t1", "t2"):
            errors.append(f"segments[{i}]: transition ha de ser t1 o t2")
        return
    if seg.get("distance_m") is None and seg.get("duration_sec") is None:
        errors.append(f"segments[{i}]: cal distance_m o duration_sec")
    if seg.get("target"):
        _check_target(seg["target"], f"segments[{i}]", athlete, errors)
    for j, step in enumerate(seg.get("steps") or []):
        _check_step(step, f"segments[{i}].steps[{j}]", athlete, errors,
                    require_target=True)
