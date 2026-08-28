"""Les 14 regles dures del pla (spec §8).

Cada regla és una funció independent amb el seu test. R1, R3, R5, R8, R11 i
R14 són bloquejants; la resta, avisos. Les decisions d'interpretació preses
en calibrar contra el pla real de Fornells estan documentades a
docs/decisions.md (§ validador).

Setmanes = dilluns-diumenge. Només s'avaluen les setmanes COMPLETES dins del
pla; els temps es deriven de duration_sec_target o, si falta, de l'estructura
(distàncies convertides amb heurístiques documentades).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from coach.models import Athlete, Goal, History, Session, Violation
from coach.structure import validate_structure

BLOCKING_RULES = {"R1", "R3", "R5", "R8", "R11", "R14"}

DISCIPLINE_SHARES = {
    "triathlon": {"swim": 22, "bike": 45, "run": 28, "strength": 5},
    "run": {"swim": 5, "bike": 15, "run": 75, "strength": 5},
    "bike": {"swim": 0, "bike": 85, "run": 10, "strength": 5},
    "swim": {"swim": 80, "bike": 10, "run": 5, "strength": 5},
    "ultra_endurance": {"swim": 0, "bike": 70, "run": 20, "strength": 10},
}

# fàcil (Z1-Z2) per fase: fracció mínima del temps (R4). El taper és 0.75 i no
# 0.80: R8 exigeix mantenir la intensitat, i en un taper d'una setmana per a
# cursa curta els tocs de ritme ja pesen ~20-25% (vegeu docs/decisions.md).
EASY_SHARE_BY_PHASE = {"base": 0.75, "build": 0.75, "peak": 0.60,
                       "taper": 0.75, "race": 0.60, "recovery": 0.80,
                       "transition": 0.75}

# heurístiques distància->temps quan un pas no porta durada ni ritme
SWIM_SEC_PER_100M = 135      # ritme real mesurat de l'atleta (2:15/100)
RUN_EASY_SEC_PER_KM = 300
FALLBACK_SEC_PER_M = {"swim": 1.35, "bike": 0.11, "run": 0.28}

RAMP_HARD = 0.12             # R1: rampa màxima dura
RAMP_SOFT = 0.08
LOW_VOLUME_FLOOR_HOURS = 5.0
DELOAD_RATIO = 0.72          # setmana ≤72% de l'anterior = descàrrega


# ─── temps i intensitat d'una sessió ─────────────────────────────────

def _step_seconds(step: dict, sport: str) -> float:
    if "repeats" in step:
        one = (_step_seconds(step.get("work") or {}, sport)
               + _step_seconds(step.get("recovery") or {}, sport))
        return step["repeats"] * one
    if step.get("duration_sec") is not None:
        return step["duration_sec"]
    distance = step.get("distance_m")
    if distance:
        target = step.get("target") or {}
        if sport == "swim":
            return distance / 100 * SWIM_SEC_PER_100M
        if target.get("type") == "pace_sec_km":
            return distance / 1000 * target["value"]
        return distance / 1000 * RUN_EASY_SEC_PER_KM
    return 0.0


def _is_easy(target: dict | None) -> bool:
    if not target:
        return True                       # recuperacions sense target
    if target.get("comparator") == "slower_than":
        return True
    ttype = target.get("type")
    if ttype == "open":
        return True
    if ttype == "rpe":
        return target.get("value", 10) <= 6
    if ttype == "hr_zone":
        return target.get("value", 5) <= 2
    return False                          # ritmes concrets = treball


def _step_easy_hard(step: dict, sport: str) -> tuple[float, float]:
    if "repeats" in step:
        we, wh = _step_easy_hard(step.get("work") or {}, sport)
        re_, rh = _step_easy_hard(step.get("recovery") or {}, sport)
        n = step["repeats"]
        return n * (we + re_), n * (wh + rh)
    sec = _step_seconds(step, sport)
    return (sec, 0.0) if _is_easy(step.get("target")) else (0.0, sec)


def session_easy_hard(session: Session) -> tuple[float, float]:
    """(segons fàcils, segons durs) segons l'estructura de la sessió."""
    structure = session.structure or {}
    easy = hard = 0.0
    for step in structure.get("steps") or []:
        e, h = _step_easy_hard(step, session.sport)
        easy, hard = easy + e, hard + h
    for seg in structure.get("segments") or []:
        if seg.get("sport") == "transition":
            continue
        sec = (seg.get("duration_sec")
               or (seg.get("distance_m") or 0) * FALLBACK_SEC_PER_M.get(seg.get("sport"), 0.3))
        if _is_easy(seg.get("target")):
            easy += sec
        else:
            hard += sec
    return easy, hard


def session_seconds(session: Session) -> float:
    if session.duration_sec_target:
        return session.duration_sec_target
    easy, hard = session_easy_hard(session)
    return easy + hard


def _sec_per_m(goal: Goal | None) -> dict[str, float]:
    """Ritme objectiu per metre i esport, per repartir sessions multiesport."""
    rates = dict(FALLBACK_SEC_PER_M)
    profile = (goal.profile if goal else None) or {}
    times = profile.get("target_times_sec") or {}
    distances = {s.get("sport"): s.get("distance_m")
                 for s in profile.get("segments") or []}
    for sport in ("swim", "bike", "run"):
        if times.get(sport) and distances.get(sport):
            rates[sport] = times[sport][1] / distances[sport]
    return rates


def sport_seconds(session: Session, goal: Goal | None) -> dict[str, float]:
    """Temps per esport d'una sessió (spec §6: el multiesport es reparteix)."""
    if session.sport == "rest":
        return {}
    if session.sport == "brick":
        return {"run": session_seconds(session)}
    if session.sport == "multisport":
        rates = _sec_per_m(goal)
        out: dict[str, float] = {}
        for seg in (session.structure or {}).get("segments") or []:
            sport = seg.get("sport")
            if sport == "transition":
                continue
            sec = seg.get("duration_sec") or (seg.get("distance_m") or 0) * rates.get(sport, 0.3)
            out[sport] = out.get(sport, 0) + sec
        return out
    return {session.sport: session_seconds(session)}


# ─── setmanes ────────────────────────────────────────────────────────

@dataclass
class Week:
    monday: date
    sessions: list[Session] = field(default_factory=list)
    full: bool = False

    @property
    def hours(self) -> float:
        return round(sum(session_seconds(s) for s in self.sessions
                         if not s.is_goal_event) / 3600, 2)

    @property
    def layoff(self) -> bool:
        return any(s.block and s.block.return_from_layoff for s in self.sessions)

    @property
    def phase(self) -> str:
        by_phase: dict[str, float] = {}
        for s in self.sessions:
            if s.block:
                by_phase[s.block.phase] = by_phase.get(s.block.phase, 0) + session_seconds(s)
        return max(by_phase, key=by_phase.get) if by_phase else "build"


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_weeks(plan: list[Session]) -> list[Week]:
    start, end = min(s.local_date for s in plan), max(s.local_date for s in plan)
    by_monday: dict[date, Week] = {}
    for s in plan:
        wk = by_monday.setdefault(_monday(s.local_date), Week(_monday(s.local_date)))
        wk.sessions.append(s)
    weeks = [by_monday[m] for m in sorted(by_monday)]
    for wk in weeks:
        # només s'exclou la primera setmana si el pla comença a mig fer-la;
        # que el pla acabi en dissabte no fa parcial l'última setmana
        wk.full = wk.monday >= start
    return weeks


def _is_deload(weeks: list[Week], i: int) -> bool:
    return i > 0 and weeks[i].hours <= DELOAD_RATIO * weeks[i - 1].hours


# ─── regles ──────────────────────────────────────────────────────────

def r1_weekly_ramp(weeks: list[Week], history: History) -> list[Violation]:
    out = []
    full = [w for w in weeks if w.full]
    plan_has_layoff = any(w.layoff for w in weeks)
    for i, wk in enumerate(full):
        if wk.layoff or wk.hours <= LOW_VOLUME_FLOOR_HOURS:
            continue
        if i > 0 and full[i - 1].layoff:
            continue  # la base és una setmana de represa: no comparable
        if i > 0:
            prev = full[i - 1]
            target = next((s.block.target_weekly_hours for s in prev.sessions
                           if s.block and s.block.target_weekly_hours), None)
            if target and prev.hours < 0.6 * target:
                continue  # setmana anterior interrompuda
        base = [w.hours for w in full[:i] if not w.layoff][-4:]
        if len(base) < 4 and not plan_has_layoff:
            # completar amb l'historial real, però mai si hi ha hagut represa:
            # la base pre-layoff no és comparable
            hist = [h for _, h in sorted(history.weekly_hours.items())]
            base = hist[-(4 - len(base)):] + base
        if not base:
            continue
        mean_base = statistics.mean(base)
        if mean_base <= 0:
            continue
        ramp = wk.hours / mean_base - 1
        if ramp > RAMP_HARD:
            out.append(Violation("R1", "blocking",
                f"setmana {wk.monday}: {wk.hours}h és +{round(ramp*100)}% sobre la "
                f"mitjana de les setmanes anteriors ({round(mean_base,2)}h); màxim +12%"))
        elif ramp > RAMP_SOFT:
            out.append(Violation("R1", "warning",
                f"setmana {wk.monday}: rampa +{round(ramp*100)}% (tou: +8%)"))
    return out


def r2_deload_cadence(weeks: list[Week], goals: list[Goal]) -> list[Violation]:
    full = [w for w in weeks if w.full]
    a_races = [g.event_date for g in goals if g.priority == "A" and g.event_date]

    def exempt(w: Week) -> bool:
        if w.phase in ("taper", "recovery", "race"):
            return True
        week_end = w.monday + timedelta(days=6)
        return any(0 <= (race - week_end).days <= 28 for race in a_races)

    streak = 0
    for i, wk in enumerate(full):
        if exempt(wk) or _is_deload(full, i):
            streak = 0
            continue
        streak += 1
        if streak >= 5:
            return [Violation("R2", "warning",
                f"{streak} setmanes seguides sense descàrrega (fins {wk.monday}); "
                f"màxim 4 fora de taper")]
    return []


def r3_key_separation(plan: list[Session]) -> list[Violation]:
    out = []
    keys = sorted((s for s in plan if s.priority == "key" and s.sport != "rest"
                   and not s.is_goal_event and not s.chained),
                  key=lambda s: s.local_date)
    by_sport: dict[str, list[Session]] = {}
    for s in keys:
        by_sport.setdefault(s.sport, []).append(s)
    for sport, sessions in by_sport.items():
        for a, b in zip(sessions, sessions[1:]):
            gap = (b.local_date - a.local_date).days
            if gap < 2:
                out.append(Violation("R3", "blocking",
                    f"dues sessions clau de {sport} a menys de 48h: "
                    f"{a.local_date} i {b.local_date}"))
    by_day: dict[date, list[Session]] = {}
    for s in keys:
        by_day.setdefault(s.local_date, []).append(s)
    for day, sessions in by_day.items():
        sports = {s.sport for s in sessions}
        if len(sports) > 1:
            out.append(Violation("R3", "blocking",
                f"{day}: sessions clau de {sorted(sports)} el mateix dia "
                f"(mínim 18h entre esports)"))
    return out


def r4_intensity_distribution(weeks: list[Week], goals: list[Goal]) -> list[Violation]:
    out = []
    a_races = [g.event_date for g in goals if g.priority == "A" and g.event_date]
    for wk in weeks:
        if not wk.full:
            continue
        easy = hard = 0.0
        for s in wk.sessions:
            if s.rehearses_goal or s.is_goal_event:
                continue
            e, h = session_easy_hard(s)
            easy, hard = easy + e, hard + h
        total = easy + hard
        if total == 0:
            continue
        phase = wk.phase
        week_end = wk.monday + timedelta(days=6)
        if phase == "build" and any(0 <= (r - week_end).days <= 28 for r in a_races):
            # §8.1: les setmanes prèvies a una cursa A curta són específiques
            # encara que el bloc es digui build — llindar de fase peak
            phase = "peak"
        minimum = EASY_SHARE_BY_PHASE.get(phase, 0.75)
        share = easy / total
        if share < minimum:
            out.append(Violation("R4", "warning",
                f"setmana {wk.monday} ({phase}): {round(share*100)}% del temps "
                f"en fàcil, mínim {round(minimum*100)}%"))
    return out


def r5_rest_days(weeks: list[Week]) -> list[Violation]:
    out = []
    full = [w for w in weeks if w.full]
    for i, wk in enumerate(full):
        rest_days = {s.local_date for s in wk.sessions
                     if s.sport == "rest" and s.session_type == "full"}
        required = 2 if _is_deload(full, i) else 1
        if len(rest_days) < required:
            out.append(Violation("R5", "blocking",
                f"setmana {wk.monday}: {len(rest_days)} dies de descans complet, "
                f"mínim {required}"))
    return out


def r6_long_session_growth(weeks: list[Week]) -> list[Violation]:
    out = []
    full = [w for w in weeks if w.full]
    last_long: dict[str, tuple[date, float]] = {}
    for i, wk in enumerate(full):
        longs: dict[str, float] = {}
        for s in wk.sessions:
            if s.session_type == "long":
                longs[s.sport] = max(longs.get(s.sport, 0), session_seconds(s))
        for sport, sec in longs.items():
            if sport in last_long and not wk.layoff:
                prev_date, prev_sec = last_long[sport]
                prev_week_layoff = any(w.layoff for w in full[:i]
                                       if w.monday == _monday(prev_date))
                if not prev_week_layoff and prev_sec > 0 and sec / prev_sec > 1.10:
                    out.append(Violation("R6", "warning",
                        f"sessió llarga de {sport}: {round(prev_sec/60)}min -> "
                        f"{round(sec/60)}min (+{round((sec/prev_sec-1)*100)}%), màxim +10%"))
            last_long[sport] = (wk.monday, sec)
    return out


def r7_triathlon_frequency(weeks: list[Week], goals: list[Goal]) -> list[Violation]:
    if not any(g.discipline == "triathlon" for g in goals):
        return []
    out = []
    for wk in weeks:
        if not wk.full or wk.phase not in ("build", "peak"):
            continue
        swims = sum(1 for s in wk.sessions if s.sport == "swim")
        bricks = sum(1 for s in wk.sessions if s.sport == "brick"
                     or (s.sport == "multisport" and s.rehearses_goal))
        if swims < 2:
            out.append(Violation("R7", "warning",
                f"setmana {wk.monday}: {swims} natacions, mínim 2"))
        if bricks < 1:
            out.append(Violation("R7", "warning",
                f"setmana {wk.monday}: cap brick en fase {wk.phase}"))
    return out


def r8_taper(plan: list[Session], weeks: list[Week], goals: list[Goal]) -> list[Violation]:
    out = []
    start, end = min(s.local_date for s in plan), max(s.local_date for s in plan)
    full = [w for w in weeks if w.full]
    for goal in goals:
        if goal.priority != "A" or not goal.event_date or not start <= goal.event_date <= end:
            continue
        taper_sessions = [s for s in plan
                          if s.block and s.block.phase == "taper" and not s.is_goal_event]
        if not taper_sessions:
            out.append(Violation("R8", "blocking",
                f"cursa A '{goal.name}' sense bloc de taper"))
            continue
        taper_start = min(s.block.start_date for s in taper_sessions)
        days = (goal.event_date - taper_start).days + 1
        total_target = ((goal.profile or {}).get("target_times_sec") or {}).get("total")
        is_short = (total_target[1] <= 3 * 3600) if total_target else True
        lo, hi = (7, 10) if is_short else (12, 21)
        if not lo <= days <= hi:
            out.append(Violation("R8", "blocking",
                f"taper de {days} dies per a '{goal.name}'; ha de ser {lo}-{hi}"))
        taper_hours = sum(session_seconds(s) for s in taper_sessions) / 3600
        prev_weeks = [w.hours for w in full if w.phase != "taper"][-2:]
        if prev_weeks:
            ratio = taper_hours / statistics.mean(prev_weeks)
            if not 0.30 <= ratio <= 0.70:
                out.append(Violation("R8", "blocking",
                    f"volum de taper {round(taper_hours,1)}h = {round(ratio*100)}% de "
                    f"les setmanes prèvies; ha de ser 30-70%"))
        hard = sum(session_easy_hard(s)[1] for s in taper_sessions)
        if hard == 0:
            out.append(Violation("R8", "blocking",
                "el taper no manté gens d'intensitat (spec: volum baixa, intensitat es manté)"))
    return out


def r9_novelty_near_race(plan: list[Session], goals: list[Goal]) -> list[Violation]:
    out = []
    for goal in goals:
        if goal.priority != "A" or not goal.event_date:
            continue
        window_start = goal.event_date - timedelta(days=10)
        practiced = {(s.sport, s.session_type) for s in plan
                     if s.local_date < window_start}
        for s in plan:
            if not window_start <= s.local_date < goal.event_date:
                continue
            if s.rehearses_goal or s.is_goal_event or s.sport == "rest":
                continue
            if session_easy_hard(s)[1] == 0:
                continue  # tot fàcil: no és una novetat de risc
            if (s.sport, s.session_type) not in practiced:
                out.append(Violation("R9", "warning",
                    f"{s.local_date}: '{s.sport}/{s.session_type}' mai practicat "
                    f"abans, a {(goal.event_date - s.local_date).days} dies de la cursa"))
    return out


def r10_post_race_recovery(plan: list[Session]) -> list[Violation]:
    out = []
    for race in (s for s in plan if s.is_goal_event):
        hard_hours = session_seconds(race) / 3600
        for offset in range(1, math.ceil(hard_hours) + 1):
            day = race.local_date + timedelta(days=offset)
            for s in plan:
                if s.local_date == day and s.priority == "key" and s.sport != "rest":
                    out.append(Violation("R10", "warning",
                        f"{day}: sessió clau '{s.title}' a {offset} dies de la cursa; "
                        f"calen {math.ceil(hard_hours)} dies fàcils"))
    return out


def r11_red_flags(plan: list[Session], history: History) -> list[Violation]:
    out = []
    metrics = sorted(history.daily_metrics, key=lambda m: m.local_date)

    def red(m) -> bool:
        return (m.hrv_status == "unbalanced"
                or (m.training_readiness is not None and m.training_readiness < 30))

    for prev, cur in zip(metrics, metrics[1:]):
        if (cur.local_date - prev.local_date).days == 1 and red(prev) and red(cur):
            danger_day = cur.local_date + timedelta(days=1)
            for s in plan:
                if s.local_date == danger_day and s.priority == "key" and s.sport != "rest":
                    out.append(Violation("R11", "blocking",
                        f"{danger_day}: sessió clau '{s.title}' després de 2 dies de "
                        f"senyals vermells (HRV/readiness); substituir per fàcil o descans"))
    return out


def r12_monotony(plan: list[Session]) -> list[Violation]:
    start, end = min(s.local_date for s in plan), max(s.local_date for s in plan)
    daily: dict[date, float] = {}
    for s in plan:
        if not s.is_goal_event:
            daily[s.local_date] = daily.get(s.local_date, 0) + session_seconds(s)
    n_days = (end - start).days + 1
    for i in range(n_days - 6):
        window = [daily.get(start + timedelta(days=i + j), 0.0) for j in range(7)]
        mean = statistics.mean(window)
        if mean == 0:
            continue
        std = statistics.stdev(window)
        monotony = (mean / std) if std > 0 else float("inf")
        if monotony > 2.0:
            return [Violation("R12", "warning",
                f"monotonia {'>2' if monotony == float('inf') else round(monotony, 2)} "
                f"la setmana del {start + timedelta(days=i)}: introduir variabilitat "
                f"abans d'afegir volum")]
    return []


def r13_goal_coherence(weeks: list[Week], goals: list[Goal]) -> list[Violation]:
    goal = next((g for g in goals if g.discipline in DISCIPLINE_SHARES), None)
    if goal is None:
        return []
    out = []
    shares = DISCIPLINE_SHARES[goal.discipline]
    emphasis = (goal.profile or {}).get("emphasis") or {}
    limiter, protect = emphasis.get("limiter"), emphasis.get("protect")
    for wk in weeks:
        if not wk.full:
            continue
        totals: dict[str, float] = {}
        for s in wk.sessions:
            if s.is_goal_event:
                continue
            for sport, sec in sport_seconds(s, goal).items():
                totals[sport] = totals.get(sport, 0) + sec
        total = sum(totals.values())
        if total == 0:
            continue
        for sport, pct in shares.items():
            margin = 20 if sport == limiter else 10
            lo = 0 if sport == protect else max(0, pct - margin)
            hi = pct + margin
            actual = totals.get(sport, 0) / total * 100
            if not lo <= actual <= hi:
                out.append(Violation("R13", "warning",
                    f"setmana {wk.monday}: {sport} al {round(actual)}% del temps, "
                    f"fora de [{lo}, {hi}]% (perfil {goal.discipline})"))
    return out


def r14_integrity(plan: list[Session], athlete: Athlete,
                  reference_date: date) -> list[Violation]:
    out = []
    for s in plan:
        for error in validate_structure(s.structure or {}, s.sport, athlete):
            out.append(Violation("R14", "blocking",
                f"{s.local_date} '{s.title}': {error}"))
        if s.status == "planned" and s.local_date < reference_date:
            out.append(Violation("R14", "blocking",
                f"{s.local_date} '{s.title}': sessió planificada al passat "
                f"(referència {reference_date})"))
    by_day: dict[date, list[Session]] = {}
    for s in plan:
        if s.priority == "key" and s.sport != "rest" and not s.chained:
            by_day.setdefault(s.local_date, []).append(s)
    for day, sessions in by_day.items():
        if len(sessions) > 1:
            out.append(Violation("R14", "blocking",
                f"{day}: {len(sessions)} sessions clau el mateix dia"))
    return out


# ─── punt d'entrada ──────────────────────────────────────────────────

def validate_plan(plan: list[Session], athlete: Athlete, history: History,
                  goals: list[Goal], reference_date: date | None = None) -> list[Violation]:
    if not plan:
        return []
    if reference_date is None:
        reference_date = min(s.local_date for s in plan)
    weeks = build_weeks(plan)
    violations = []
    violations += r1_weekly_ramp(weeks, history)
    violations += r2_deload_cadence(weeks, goals)
    violations += r3_key_separation(plan)
    violations += r4_intensity_distribution(weeks, goals)
    violations += r5_rest_days(weeks)
    violations += r6_long_session_growth(weeks)
    violations += r7_triathlon_frequency(weeks, goals)
    violations += r8_taper(plan, weeks, goals)
    violations += r9_novelty_near_race(plan, goals)
    violations += r10_post_race_recovery(plan)
    violations += r11_red_flags(plan, history)
    violations += r12_monotony(plan)
    violations += r13_goal_coherence(weeks, goals)
    violations += r14_integrity(plan, athlete, reference_date)
    return violations
