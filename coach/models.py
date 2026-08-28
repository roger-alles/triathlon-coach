"""Models del validador (spec §8): objectes plans, sense dependència de la DB."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Athlete:
    name: str
    max_hr: int | None = None
    ftp_watts: int | None = None
    css_sec_per_100m: float | None = None
    threshold_pace_sec_km: float | None = None
    zones: dict = field(default_factory=dict)


@dataclass
class Goal:
    name: str
    discipline: str
    event_date: date | None
    priority: str
    profile: dict = field(default_factory=dict)


@dataclass
class Block:
    id: int
    phase: str
    start_date: date
    end_date: date
    target_weekly_hours: float | None = None
    return_from_layoff: bool = False


@dataclass
class Session:
    local_date: date
    sport: str
    session_type: str
    title: str
    structure: dict
    block: Block | None = None
    duration_sec_target: int | None = None
    priority: str = "support"
    status: str = "planned"
    is_test: bool = False
    rehearses_goal: bool = False
    is_goal_event: bool = False
    chained: bool = False       # brick encadenat a la sessió pare del mateix dia


@dataclass
class DailyMetric:
    local_date: date
    hrv_status: str | None = None
    training_readiness: int | None = None


@dataclass
class History:
    """El que el validador sap del passat real."""
    weekly_hours: dict[date, float] = field(default_factory=dict)  # dilluns -> hores
    daily_metrics: list[DailyMetric] = field(default_factory=list)


@dataclass
class Violation:
    rule: str
    severity: str  # 'blocking' | 'warning'
    message: str

    @property
    def blocking(self) -> bool:
        return self.severity == "blocking"
