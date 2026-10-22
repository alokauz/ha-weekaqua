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

from .texts import format_date, t

_LOGGER = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "start_brightness": 60,
    "brightness_step": 10,
    "interval_days": 7,
    "shorten": 120,
    "shorten_step": 30,
    # UV follows the square of the brightness share (60 % -> UV 36 %), so it starts
    # lower and catches up, still reaching normal with everything else.
    "uv_holdback": False,
}
STORE_VERSION = 1


def describe_minutes(minutes: float) -> str:
    """'1 h 30 min', '2 h', '45 min'"""
    minutes = int(round(minutes))
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return t("hours_minutes", hours=hours, minutes=rest)
    if hours:
        return t("hours", hours=hours)
    return t("minutes", minutes=rest)


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

    def uv_brightness(self, brightness: float | None = None) -> float:
        """Percent of the schedule's UV to use (equals brightness() without UV hold-back)."""
        b = self.brightness() if brightness is None else brightness
        return b * b / 100 if self.settings.get("uv_holdback") else b

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
            return t("acc_finished")
        if not self.running:
            return t("acc_not_running")
        brightness, shorter = self.values(self.stage())
        text = f"{brightness:g}%"
        if self.settings.get("uv_holdback") and brightness < 100:
            text += t("acc_uv", percent=f"{round(self.uv_brightness(brightness)):g}")
        if shorter:
            text += t("acc_shorter", minutes=describe_minutes(shorter))
        return (t("acc_paused") if self.paused else "") + text

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
            t("acc_started_title"),
            t(
                "acc_started",
                brightness=f"{brightness:g}",
                shorter=t("acc_started_shorter", minutes=describe_minutes(shorter)) if shorter else "",
                interval=self.settings["interval_days"],
                end=format_date(self.ends(), year=True),
            ),
        )
        self._notify()

    async def async_stop(self) -> None:
        """Stop and go back to the normal schedule."""
        was_running = self.running
        self.state.update(started=None, paused_since=None, paused_days=0, finished=None, stage_notified=None)
        await self._save()
        if was_running:
            self._message(t("acc_stopped_title"), t("acc_stopped"))
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
            uv = (
                t("acc_uv", percent=f"{round(brightness * brightness / 100):g}")
                if preview.settings.get("uv_holdback") and brightness < 100 else ""
            )
            what = t("plan_normal") if stage == preview.total_stages() else (
                f"{brightness:g}%{uv}" + (t("acc_shorter", minutes=describe_minutes(shorter)) if shorter else "")
            )
            mark = t("plan_now") if self.running and settings is None and stage == self.stage() else ""
            lines.append(t("plan_line", date=format_date(day), what=what + mark))
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
            t("acc_back_title"),
            t(
                "acc_back",
                brightness=f"{brightness:g}",
                period=t("acc_step_shorter", minutes=describe_minutes(shorter)) if shorter else "",
                next=format_date(self.next_change()),
                end=format_date(self.ends(), year=True),
            ),
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
            self._message(t("acc_finished_title"), t("acc_finished_msg"))
            _LOGGER.info("Acclimation finished")
            self._notify()
            return
        if stage != self.state.get("stage_notified"):
            self.state["stage_notified"] = stage
            await self._save()
            brightness, shorter = self.values(stage)
            nxt = self.next_change()
            self._message(
                t("acc_step_title"),
                t(
                    "acc_step",
                    brightness=f"{brightness:g}",
                    period=t("acc_step_shorter", minutes=describe_minutes(shorter)) if shorter else t("acc_step_normal_period"),
                    next=t("acc_next", date=format_date(nxt)) if nxt else "",
                    end=format_date(self.ends(), year=True),
                ),
            )
            _LOGGER.info("Acclimation stage %s: %s%%, %s min shorter", stage, brightness, shorter)
            self._notify()

    def _message(self, title: str, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"Week Aqua: {title}",  # title already translated
            notification_id=f"weekaqua_acclimation_{self.entry_id}",
        )
