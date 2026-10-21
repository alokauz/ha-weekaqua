"""Schedule steps defined under Configure, run by the integration itself.

A step: {"time": "HH:MM", "target": preset name or OFF_TARGET,
         "brightness": 1-100, "fade": minutes, "days": [0-6],  (0 = Monday)
         "curve": "perceptual"/"linear" (optional), "smoothness": seconds (optional)}
Missing curve/smoothness = use the general fade settings.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, time, timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .device import WeekAquaDevice

_LOGGER = logging.getLogger(__name__)

OFF_TARGET = "__off__"
# A step that can't reach the light (phone app connected, Bluetooth hiccup)
# is retried this often, for this long.
RETRY_INTERVAL = 30
RETRY_FOR = 600
ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
SMOOTHNESS_SHORT = {"0.5": "fine", "10": "medium", "30": "coarse", "60": "very coarse"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def step_time(step: dict[str, Any]) -> time:
    hour, minute = (int(part) for part in step["time"].split(":")[:2])
    return time(hour, minute)


def describe_step(step: dict[str, Any], presets: dict | None = None) -> str:
    """Human-readable summary, e.g. '08:00 · On · Nature 80% · fade 45 min · Mon–Fri'."""
    if step["target"] == OFF_TARGET:
        what = "Off"
    else:
        what = f"On · {step['target']} {step.get('brightness', 100)}%"
        if presets is not None and step["target"] not in presets:
            what += " (preset missing!)"
    fade = ""
    if step.get("fade"):
        extras = [
            label
            for label in (
                {"perceptual": "natural", "linear": "linear"}.get(step.get("curve") or ""),
                SMOOTHNESS_SHORT.get(str(step.get("smoothness") or "")),
            )
            if label
        ]
        fade = f" · fade {step['fade']:g} min" + (f" ({', '.join(extras)})" if extras else "")
    days = sorted(step.get("days", ALL_DAYS))
    if days == ALL_DAYS:
        day_text = "every day"
    elif days == [0, 1, 2, 3, 4]:
        day_text = "Mon–Fri"
    elif days == [5, 6]:
        day_text = "Sat–Sun"
    else:
        day_text = ", ".join(DAY_NAMES[d] for d in days)
    return f"{step['time']} · {what}{fade} · {day_text}"


class WeekAquaScheduler:
    """Fires schedule steps and can catch up to where the schedule should be."""

    def __init__(
        self, hass: HomeAssistant, device: WeekAquaDevice, steps: list[dict[str, Any]]
    ) -> None:
        self.hass = hass
        self.device = device
        self.steps = sorted(steps, key=step_time)
        self.enabled = True
        self.acclimation = None  # set in __init__.py
        self._unsubs: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []
        # Bumped whenever a newer step starts, so a retrying older step gives up.
        self._generation = 0

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def effective_time(self, step: dict[str, Any]) -> time:
        """The step's time today, with acclimation moving Off steps earlier."""
        normal = step_time(step)
        acc = self.acclimation
        if acc is None or step["target"] != OFF_TARGET or not acc.shorter_minutes():
            return normal
        minutes = normal.hour * 60 + normal.minute - acc.shorter_minutes()
        # Not before the previous step (and its fade) has finished
        earlier = [s for s in self.steps if step_time(s) < normal]
        if earlier:
            prev = earlier[-1]
            prev_t = step_time(prev)
            floor = prev_t.hour * 60 + prev_t.minute + int(prev.get("fade", 0)) + 1
            minutes = max(minutes, floor)
        minutes = max(0, min(int(minutes), normal.hour * 60 + normal.minute))
        return time(minutes // 60, minutes % 60)

    @callback
    def reschedule(self) -> None:
        """Re-register step times (acclimation changed the Off times)."""
        self.stop()
        self.start()
        self._notify()

    @callback
    def start(self) -> None:
        for step in self.steps:
            at = self.effective_time(step)
            self._unsubs.append(
                async_track_time_change(
                    self.hass, partial(self._fire, step), hour=at.hour, minute=at.minute, second=0
                )
            )

    @callback
    def stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _fire(self, step: dict[str, Any], now: datetime) -> None:
        if not self.enabled:
            _LOGGER.info("Schedule is switched off, skipping step %s", step["time"])
        elif now.weekday() in step.get("days", ALL_DAYS):
            self.hass.async_create_background_task(
                self._run(step, step.get("fade", 0) * 60),
                f"weekaqua schedule {step['time']}",
            )
        self._notify()  # the next step has moved on

    async def _run(self, step: dict[str, Any], transition: float) -> None:
        """Run a step; if the light can't be reached, keep retrying for a while."""
        self._generation += 1
        generation = self._generation
        loop = asyncio.get_running_loop()
        started = loop.time()
        _LOGGER.info("Running schedule step %s", self._explain(step, transition))
        for attempt in range(RETRY_FOR // RETRY_INTERVAL + 1):
            elapsed = loop.time() - started
            try:
                await self._apply_step(step, max(0.0, transition - elapsed))
            except HomeAssistantError as err:
                if attempt == RETRY_FOR // RETRY_INTERVAL:
                    _LOGGER.warning(
                        "Schedule step at %s failed, giving up after %s min: %s",
                        step["time"], RETRY_FOR // 60, err,
                    )
                    return
                _LOGGER.warning(
                    "Schedule step at %s failed (%s), retrying in %s s",
                    step["time"], err, RETRY_INTERVAL,
                )
                target_before = self.device.target
                await asyncio.sleep(RETRY_INTERVAL)
                if (
                    generation != self._generation
                    or not self.enabled
                    or self.device.target != target_before
                ):
                    _LOGGER.info(
                        "Not retrying step at %s: something newer happened", step["time"]
                    )
                    return
                continue
            if attempt:
                _LOGGER.info("Schedule step at %s succeeded after retrying", step["time"])
            return

    def _explain(self, step: dict[str, Any], transition: float) -> str:
        """Everything the step will do, for the log."""
        from .device import SMOOTHNESS_NAMES, describe_duration, describe_levels

        dev = self.device
        if step["target"] == OFF_TARGET:
            what = "to Off"
        elif step["target"] in dev.presets:
            factor = self.acclimation_factor()
            scale = step.get("brightness", 100) / 100 * factor
            levels = tuple(round(v * scale) for v in dev.presets[step["target"]])
            what = f"to preset {step['target']!r} at {step.get('brightness', 100) * factor:g}%"
            if factor < 1:
                what += f" (acclimation {factor * 100:g}% of {step.get('brightness', 100)}%)"
            what += f" ({describe_levels(levels)})"
            if (fan := dev.preset_fans.get(step["target"])) is not None:
                what += f", fan {fan:g}%"
        else:
            what = f"to missing preset {step['target']!r}"
        if not transition:
            fade = "instantly"
        else:
            curve = step.get("curve")
            smooth = step.get("smoothness")
            curve_text = (
                f"{'natural' if curve == 'perceptual' else 'linear'} (this step)"
                if curve
                else f"{'natural' if dev.fade_curve == 'perceptual' else 'linear'} (general setting)"
            )
            interval = float(smooth) if smooth else dev.fade_interval
            smooth_text = SMOOTHNESS_NAMES.get(interval, f"{interval:g} s") + (
                " (this step)" if smooth else " (general setting)"
            )
            planned = step.get("fade", 0) * 60
            fade = f"fading over {describe_duration(transition)}"
            if abs(planned - transition) > 1:
                fade += f" (remaining of {describe_duration(planned)})"
            fade += f", curve {curve_text}, smoothness {smooth_text}"
        days = describe_step(step).rsplit(" · ", 1)[-1]
        at = self.effective_time(step).strftime("%H:%M")
        when = step["time"] if at == step["time"] else f"{at} (acclimation, normally {step['time']})"
        return (
            f"{when} ({days}): from {describe_levels(dev.levels)} {what}, {fade}"
        )

    def acclimation_factor(self) -> float:
        return (self.acclimation.brightness() / 100) if self.acclimation else 1.0

    async def _apply_step(self, step: dict[str, Any], transition: float) -> None:
        interval = float(step["smoothness"]) if step.get("smoothness") else None
        curve = step.get("curve") or None
        if step["target"] == OFF_TARGET:
            await self.device.set_levels((0, 0, 0, 0), transition, interval, curve)
        elif step["target"] in self.device.presets:
            scale = step.get("brightness", 100) / 100 * self.acclimation_factor()
            await self.device.apply_preset(step["target"], transition, scale, interval, curve)
        else:
            _LOGGER.warning(
                "Schedule step at %s uses preset %r, which no longer exists",
                step["time"],
                step["target"],
            )

    def _occurrences(self, now: datetime, backwards: bool):
        """Step datetimes going back (or forward) from now, up to 8 days."""
        day_range = range(0, -8, -1) if backwards else range(0, 8)
        for offset in day_range:
            day = now.date() + timedelta(days=offset)
            steps = reversed(self.steps) if backwards else self.steps
            for step in steps:
                if day.weekday() not in step.get("days", ALL_DAYS):
                    continue
                when = datetime.combine(day, self.effective_time(step), tzinfo=now.tzinfo)
                if (backwards and when <= now) or (not backwards and when > now):
                    yield step, when

    def last_step(self, now: datetime | None = None):
        return next(self._occurrences(now or dt_util.now(), True), (None, None))

    def next_step(self, now: datetime | None = None):
        return next(self._occurrences(now or dt_util.now(), False), (None, None))

    def step_kind(self, step: dict[str, Any], when: datetime) -> str:
        """'sunset' (to Off), 'sunrise' (On after Off) or 'change' (On while on)."""
        if step["target"] == OFF_TARGET:
            return "sunset"
        previous, _ = self.last_step(when - timedelta(seconds=1))
        if previous is None or previous["target"] == OFF_TARGET:
            return "sunrise"
        return "change"

    async def apply_current(self) -> None:
        """Put the light where the schedule says it should be now.

        If the last step's fade is still running, continue it for the remaining time.
        """
        if not self.enabled or not self.steps:
            return
        step, when = self.last_step()
        if step is None:
            return
        remaining = step.get("fade", 0) * 60 - (dt_util.now() - when).total_seconds()
        _LOGGER.info("Catching up with the schedule (step at %s)", step["time"])
        await self._run(step, max(0.0, remaining) if remaining > 1 else 0)

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._notify()
        if enabled:
            await self.apply_current()
