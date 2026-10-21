"""CO₂ control: switch the CO₂ plug from the light schedule.

CO₂ goes on `on_before` minutes before the day's first On step starts, and off
`off_before` minutes before the day's last Off step (the time the light is fully
off), never longer than `max_hours`. A watchdog checks every minute and switches
CO₂ off whenever it is on outside that window: at night, when the schedule is
switched off, or after someone turned it on by hand.

Safety notes:
- CO₂ left on without light can suffocate fish. Home Assistant can only switch
  the plug while it is running, so a backstop *in the plug itself* (an off-only
  schedule, or auto-off) is required.
- CO₂ is deliberately NOT switched off when Home Assistant restarts or the
  integration reloads: that would cut CO₂ on every restart, and the interlock
  would then dim the light for the lead time.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .schedule import OFF_TARGET, WeekAquaScheduler

_LOGGER = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {"control": False, "on_before": 60, "off_before": 60, "max_hours": 10}
CONTROLLABLE_DOMAINS = ("switch", "input_boolean", "light")


class CO2Control:
    def __init__(
        self,
        hass: HomeAssistant,
        scheduler: WeekAquaScheduler,
        settings: dict | None,
        starting: bool,
    ) -> None:
        self.hass = hass
        self.scheduler = scheduler
        s = {**DEFAULTS, **(settings or {})}
        self.entity_id: str | None = s.get("entity_id")
        self.enabled = bool(
            s["control"]
            and self.entity_id
            and self.entity_id.split(".")[0] in CONTROLLABLE_DOMAINS
        )
        self.on_before = int(s["on_before"])
        self.off_before = int(s["off_before"])
        self.max_hours = float(s["max_hours"])
        self._starting = starting
        self._unsub = None
        self._busy = False

    # ---- the window ---------------------------------------------------

    def window(self, day: date | None = None) -> tuple[datetime | None, datetime | None, str]:
        """(on, off, explanation) for a day; (None, None, why) if CO₂ stays off."""
        sched = self.scheduler
        if not sched.enabled:
            return None, None, "the schedule is switched off"
        day = day or dt_util.now().date()
        tz = dt_util.get_default_time_zone()
        today = [s for s in sched.steps if day.weekday() in s.get("days", range(7))]
        ons = [s for s in today if s["target"] != OFF_TARGET]
        offs = [s for s in today if s["target"] == OFF_TARGET]
        if not ons or not offs:
            return None, None, "no On and Off step today"
        first_on = min(datetime.combine(day, sched.run_time(s), tzinfo=tz) for s in ons)
        last_off = max(datetime.combine(day, sched.effective_time(s), tzinfo=tz) for s in offs)
        if last_off <= first_on:
            return None, None, "the last Off step is before the first On step"
        on = max(first_on - timedelta(minutes=self.on_before), datetime.combine(day, time(0, 0), tzinfo=tz))
        off = last_off - timedelta(minutes=self.off_before)
        if off <= on:
            return None, None, "the On and Off times leave no time for CO₂"
        note = ""
        if off - on > timedelta(hours=self.max_hours):
            on = off - timedelta(hours=self.max_hours)
            note = f" (shortened to the {self.max_hours:g} h maximum)"
        return on, off, f"{on:%H:%M}–{off:%H:%M}{note}"

    def in_window(self, now: datetime | None = None) -> bool:
        now = now or dt_util.now()
        on, off, _ = self.window(now.date())
        return bool(on and on <= now < off)

    def summary(self) -> str:
        if not self.enabled:
            return "Not controlled"
        on, off, why = self.window()
        if on is None:
            return f"Off today ({why})"
        hours = (off - on).total_seconds() / 3600
        return f"{why} ({hours:.1f} h)".replace(".0 h", " h")

    # ---- running ------------------------------------------------------

    @callback
    def start(self) -> None:
        if not self.enabled:
            return
        self._unsub = async_track_time_change(self.hass, self._tick, second=0)
        if not self._starting:  # at HA start, __init__.py catches up once HA has started
            self.hass.async_create_task(self.catch_up())

    @callback
    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _plug(self):
        return self.hass.states.get(self.entity_id) if self.entity_id else None

    async def catch_up(self) -> None:
        """If CO₂ missed its start (HA wasn't running, control just enabled), switch it on now."""
        if not self.enabled:
            return
        on, _off, _ = self.window()
        state = self._plug()
        if not on or not self.in_window() or state is None or state.state != STATE_OFF:
            return
        # Respect a manual switch-off during today's window; after an HA start we can't tell.
        if self._starting or state.last_changed < on:
            await self._switch(True, "the CO₂ window had already started")

    @callback
    def _tick(self, now: datetime) -> None:
        if self._busy:
            return
        state = self._plug()
        if state is None:
            return
        on, off, _ = self.window(now.date())
        local = dt_util.as_local(now)
        if on and on <= local < on + timedelta(minutes=1) and state.state != STATE_ON:
            self.hass.async_create_task(self._switch(True, "the CO₂ window starts"))
        elif state.state == STATE_ON and not self.in_window(local):
            planned_end = off and off <= local < off + timedelta(minutes=1)
            reason = "the CO₂ window ends" if planned_end else "it was on outside its window"
            self.hass.async_create_task(self._switch(False, reason, warn=not planned_end))

    async def _switch(self, turn_on: bool, reason: str, warn: bool = False) -> None:
        self._busy = True
        try:
            _LOGGER.info("CO₂ %s: %s", "on" if turn_on else "off", reason)
            await self.hass.services.async_call(
                "homeassistant", "turn_on" if turn_on else "turn_off",
                {"entity_id": self.entity_id}, blocking=True,
            )
            if warn:
                persistent_notification.async_create(
                    self.hass,
                    f"CO₂ was switched off because {reason} ({self.summary()}). "
                    "CO₂ without light can harm fish.",
                    title="Week Aqua: CO₂ control",
                    notification_id="weekaqua_co2_control",
                )
        except Exception as err:  # noqa: BLE001 - tell the user, the plug's own schedule is the backstop
            _LOGGER.error("Couldn't switch CO₂ %s: %s", "on" if turn_on else "off", err)
            persistent_notification.async_create(
                self.hass,
                f"Couldn't switch CO₂ {'on' if turn_on else 'off'} ({err}). Check the plug.",
                title="Week Aqua: CO₂ control",
                notification_id="weekaqua_co2_control",
            )
        finally:
            self._busy = False

    async def schedule_switched_off(self) -> None:
        """The schedule was switched off: CO₂ off too."""
        if not self.enabled:
            return
        state = self._plug()
        if state is not None and state.state == STATE_ON:
            await self._switch(False, "the schedule was switched off")

    def diagnostics(self) -> dict[str, Any]:
        on, off, why = self.window()
        return {
            "enabled": self.enabled,
            "on_before": self.on_before,
            "off_before": self.off_before,
            "max_hours": self.max_hours,
            "window_today": why,
            "in_window": self.in_window() if self.enabled else None,
        }
