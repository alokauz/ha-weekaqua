"""The day's planned light: channel levels minute by minute, from the schedule.

Used for the Light plan sensor (planned full-power hours and the curve for a
chart). Follows the schedule as it would run today: run times, fades and their
curves, acclimation (incl. UV hold-back) and the power limit. The CO₂ fallback
is left out (CO₂ readiness later in the day isn't known in advance).

"Full-power hours" = the integral of total power over the day: 1 h at 100 %
power, or 2 h at 50 %, is 1 full-power hour. A relative measure of light, not
PAR or DLI.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import total_power
from .device import _interpolate
from .schedule import ALL_DAYS, OFF_TARGET, WeekAquaScheduler

MINUTES = 24 * 60


def _day_events(sched: WeekAquaScheduler, day: date) -> list[tuple[int, int, tuple, bool]]:
    """(start minute, fade minutes, target levels, perceptual) of the steps that run on a day."""
    events = []
    for step in sched.steps:
        if day.weekday() not in step.get("days", ALL_DAYS):
            continue
        start, _ = sched.run_window(step)
        fade = int(round(sched.run_fade(step)))
        target = (0, 0, 0, 0) if step["target"] == OFF_TARGET else sched.step_levels(step, include_co2=False)
        perceptual = (step.get("curve") or sched.device.fade_curve) == "perceptual"
        events.append((start, fade, target, perceptual))
    return sorted(events, key=lambda e: e[0])


def plan_minutes(sched: WeekAquaScheduler, day: date | None = None) -> list[tuple[int, int, int, int]]:
    """Channel levels for each minute of the day (index 0 = 00:00)."""
    day = day or dt_util.now().date()
    if not sched.enabled or not sched.steps:
        return [(0, 0, 0, 0)] * MINUTES
    # The day starts where the previous day ended (its last step, completed)
    previous = _day_events(sched, day - timedelta(days=1))
    current = previous[-1][2] if previous else (0, 0, 0, 0)
    events = _day_events(sched, day)
    levels: list[tuple[int, int, int, int]] = []
    active = None  # (start, fade, from, to, perceptual)
    i = 0
    for minute in range(MINUTES):
        while i < len(events) and events[i][0] <= minute:
            start, fade, target, perceptual = events[i]
            # A new step starts from wherever the light is at that moment
            active = (start, fade, current, target, perceptual)
            i += 1
        if active is not None:
            start, fade, frm, to, perceptual = active
            if fade <= 0 or minute >= start + fade:
                current = to
            else:
                current = _interpolate(frm, to, (minute - start) / fade, perceptual)
        levels.append(current)
    return levels


def full_power_hours(levels: list[tuple[int, int, int, int]]) -> float:
    """Integral of total power over the minutes, in full-power hours."""
    return sum(total_power(lv) for lv in levels) / 100 / 60


def summary(sched: WeekAquaScheduler, day: date | None = None, every: int = 5) -> dict[str, Any]:
    """Planned full-power hours, light period, peak and a curve for charts."""
    minutes = plan_minutes(sched, day)
    lit = [m for m, lv in enumerate(minutes) if any(lv)]
    pct = lambda v: round(v / 235 * 100, 1)  # noqa: E731
    curve = [
        {
            "t": f"{m // 60:02d}:{m % 60:02d}",
            "r": pct(minutes[m][0]),
            "g": pct(minutes[m][1]),
            "b": pct(minutes[m][2]),
            "uv": pct(minutes[m][3]),
            "power": round(total_power(minutes[m]), 1),
        }
        for m in list(range(0, MINUTES, every)) + [MINUTES - 1]
    ]
    return {
        "planned_full_power_hours": round(full_power_hours(minutes), 2),
        "light_from": f"{lit[0] // 60:02d}:{lit[0] % 60:02d}" if lit else None,
        "light_until": f"{(lit[-1] + 1) // 60:02d}:{(lit[-1] + 1) % 60:02d}" if lit else None,
        "light_hours": round(len(lit) / 60, 2),
        "peak_power": round(max((total_power(lv) for lv in minutes), default=0), 1),
        "curve": curve,
    }


def planned_until_now(sched: WeekAquaScheduler, now: datetime | None = None) -> float:
    """Planned full-power hours from midnight until now."""
    now = now or dt_util.now()
    minutes = plan_minutes(sched, now.date())
    upto = now.hour * 60 + now.minute
    return full_power_hours(minutes[:upto])
