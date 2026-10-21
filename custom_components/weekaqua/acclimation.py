"""Acclimation program: bring a tank up to its normal schedule over weeks.

Brightness starts at `start_brightness` % of the schedule's own brightness and
rises by `brightness_step` % every `interval_days`. The photoperiod starts
`shorten` minutes shorter (Off steps run earlier) and gets `shorten_step`
minutes longer every interval. Both stop at the normal schedule: when they get
there the program finishes by itself, so forgetting about it is harmless.

Settings live in the config entry options (Configure). Progress (start date,
pauses) lives in a Store, so pausing doesn't reload the integration.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
import logging
import math
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "start_brightness": 60,
    "brightness_step": 10,
    "interval_days": 7,
    "shorten": 120,
    "shorten_step": 30,
}
STORE_VERSION = 1


def describe_minutes(minutes: float) -> str:
    """'1 h 30 min', '2 h', '45 min'"""
    minutes = int(round(minutes))
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours} h {rest} min"
    if hours:
        return f"{hours} h"
    return f"{rest} min"


class Acclimation:
    """Where the program is, and what it does to the schedule today."""

    def __init__(self, hass: HomeAssistant, entry_id: str, settings: dict | None) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.settings: dict[str, Any] = {**DEFAULTS, **(settings or {})}
        self._store: Store = Store(hass, STORE_VERSION, f"weekaqua.acclimation.{entry_id}")
        self.state: dict[str, Any] = {
            "started": None,  # ISO date the program started
            "paused_since": None,  # ISO date, while paused
            "paused_days": 0,  # days spent paused before the current pause
            "finished": None,  # ISO date it finished
            "stage_notified": None,  # last stage a notification was sent for
        }
        self._listeners: list[Callable[[], None]] = []
        self._unsub: Callable[[], None] | None = None

    # ---- persistence and listeners -----------------------------------

    async def async_load(self) -> None:
        if data := await self._store.async_load():
            self.state.update(data)

    async def _save(self) -> None:
        await self._store.async_save(self.state)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Called when the program's effect on the schedule may have changed."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def start_daily_check(self) -> None:
        self._unsub = async_track_time_change(
            self.hass, self._daily, hour=0, minute=0, second=10
        )

    @callback
    def stop_daily_check(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _daily(self, _now) -> None:
        self.hass.async_create_task(self.async_check())

    # ---- state ------------------------------------------------------

    @property
    def running(self) -> bool:
        """Started and not finished (it may be paused)."""
        return self.state["started"] is not None and self.state["finished"] is None

    @property
    def paused(self) -> bool:
        return self.running and self.state["paused_since"] is not None

    @staticmethod
    def _today() -> date:
        return dt_util.now().date()

    def days(self) -> int:
        """Days the program has been running, not counting pauses."""
        if not self.running:
            return 0
        start = date.fromisoformat(self.state["started"])
        end = date.fromisoformat(self.state["paused_since"]) if self.paused else self._today()
        return max(0, (end - start).days - self.state["paused_days"])

    def total_stages(self) -> int:
        s = self.settings
        need_b = (
            math.ceil((100 - s["start_brightness"]) / s["brightness_step"])
            if s["start_brightness"] < 100 and s["brightness_step"] > 0
            else 0
        )
        need_p = (
            math.ceil(s["shorten"] / s["shorten_step"])
            if s["shorten"] > 0 and s["shorten_step"] > 0
            else 0
        )
        return max(need_b, need_p)

    def stage(self) -> int:
        return min(self.days() // max(1, int(self.settings["interval_days"])), self.total_stages())

    def values(self, stage: int) -> tuple[float, float]:
        """(brightness %, minutes shorter) at a stage."""
        s = self.settings
        brightness = min(100.0, s["start_brightness"] + stage * s["brightness_step"])
        shorter = max(0.0, s["shorten"] - stage * s["shorten_step"])
        return brightness, shorter

    def brightness(self) -> float:
        """Percent of the schedule's brightness to use now (100 = normal)."""
        return self.values(self.stage())[0] if self.running else 100.0

    def shorter_minutes(self) -> float:
        """How many minutes earlier Off steps run now (0 = normal)."""
        return self.values(self.stage())[1] if self.running else 0.0

    def _date_of_stage(self, stage: int) -> date | None:
        if not self.running:
            return None
        start = date.fromisoformat(self.state["started"])
        paused = self.state["paused_days"]
        if self.paused:
            paused += (self._today() - date.fromisoformat(self.state["paused_since"])).days
        return start + timedelta(days=stage * int(self.settings["interval_days"]) + paused)

    def next_change(self) -> date | None:
        if not self.running or self.paused or self.stage() >= self.total_stages():
            return None
        return self._date_of_stage(self.stage() + 1)

    def ends(self) -> date | None:
        return self._date_of_stage(self.total_stages())

    def summary(self) -> str:
        """Short text for the sensor."""
        if self.state["finished"]:
            return "Finished"
        if not self.running:
            return "Not running"
        brightness, shorter = self.values(self.stage())
        text = f"{brightness:g}%"
        if shorter:
            text += f" · {describe_minutes(shorter)} shorter"
        return ("Paused · " if self.paused else "") + text

    # ---- actions ------------------------------------------------------

    async def async_start(self) -> None:
        """Start (or restart) from the beginning today."""
        self.state.update(
            started=self._today().isoformat(),
            paused_since=None,
            paused_days=0,
            finished=None,
            stage_notified=0,
        )
        await self._save()
        brightness, shorter = self.values(0)
        self._message(
            "Acclimation started",
            f"The schedule now runs at {brightness:g}% brightness"
            + (f" and a {describe_minutes(shorter)} shorter light period" if shorter else "")
            + f". It steps up every {self.settings['interval_days']} days and returns to your"
            f" normal schedule on {self.ends():%d %b %Y}.",
        )
        self._notify()

    async def async_stop(self) -> None:
        """Stop and go back to the normal schedule."""
        was_running = self.running
        self.state.update(started=None, paused_since=None, paused_days=0, finished=None, stage_notified=None)
        await self._save()
        if was_running:
            self._message("Acclimation stopped", "The light is back on your normal schedule.")
        self._notify()

    def plan(self, settings: dict[str, Any] | None = None, start: date | None = None) -> list[str]:
        """One line per stage: 'From 16 Oct: 60% · 2 h shorter'."""
        preview = Acclimation.__new__(Acclimation)
        preview.settings = {**self.settings, **(settings or {})}
        start = start or (
            date.fromisoformat(self.state["started"]) if self.running and settings is None else self._today()
        )
        paused = self.state["paused_days"] if self.running and settings is None else 0
        lines = []
        for stage in range(preview.total_stages() + 1):
            brightness, shorter = preview.values(stage)
            day = start + timedelta(days=stage * int(preview.settings["interval_days"]) + paused)
            what = "normal schedule" if stage == preview.total_stages() else (
                f"{brightness:g}%" + (f" · {describe_minutes(shorter)} shorter" if shorter else "")
            )
            mark = " ← now" if self.running and settings is None and stage == self.stage() else ""
            lines.append(f"{day:%d %b}: {what}{mark}")
        return lines

    async def async_step_back(self) -> None:
        """Go back to the previous stage (e.g. algae appeared) and stay there a full interval."""
        if not self.running or self.stage() == 0:
            return
        interval = int(self.settings["interval_days"])
        target_days = (self.stage() - 1) * interval
        # Count the extra time as paused: the previous stage now lasts a full interval from today
        self.state["paused_days"] += self.days() - target_days
        self.state["stage_notified"] = self.stage()
        await self._save()
        brightness, shorter = self.values(self.stage())
        self._message(
            "Acclimation went back one step",
            f"Now {brightness:g}% brightness"
            + (f", light period {describe_minutes(shorter)} shorter than normal" if shorter else "")
            + f". Next step on {self.next_change():%d %b}; back to normal on {self.ends():%d %b %Y}.",
        )
        self._notify()

    async def async_pause(self) -> None:
        if self.running and not self.paused:
            self.state["paused_since"] = self._today().isoformat()
            await self._save()
            self._notify()

    async def async_resume(self) -> None:
        if self.paused:
            paused_since = date.fromisoformat(self.state["paused_since"])
            self.state["paused_days"] += (self._today() - paused_since).days
            self.state["paused_since"] = None
            await self._save()
            self._notify()

    async def async_check(self) -> None:
        """Daily (and at startup): step up, or finish, and tell the user once."""
        if not self.running:
            return
        stage = self.stage()
        if stage >= self.total_stages():
            self.state["finished"] = self._today().isoformat()
            await self._save()
            self._message(
                "Acclimation finished",
                "The light is now on your normal schedule. The program has ended by itself.",
            )
            _LOGGER.info("Acclimation finished")
            self._notify()
            return
        if stage != self.state.get("stage_notified"):
            self.state["stage_notified"] = stage
            await self._save()
            brightness, shorter = self.values(stage)
            nxt = self.next_change()
            self._message(
                "Acclimation stepped up",
                f"Now {brightness:g}% brightness"
                + (f", light period {describe_minutes(shorter)} shorter than normal" if shorter else ", normal light period")
                + (f". Next step on {nxt:%d %b}" if nxt else "")
                + f". Back to normal on {self.ends():%d %b %Y}.",
            )
            _LOGGER.info("Acclimation stage %s: %s%%, %s min shorter", stage, brightness, shorter)
            self._notify()

    def _message(self, title: str, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"Week Aqua: {title}",
            notification_id=f"weekaqua_acclimation_{self.entry_id}",
        )
