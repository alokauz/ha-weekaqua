"""CO₂ control: switch the CO₂ plug from the light schedule.

CO₂ goes on `on_before` minutes before the day's first On step starts, and off
`off_before` minutes before the day's last Off step (the time the light is fully
off), never longer than `max_hours`. A siesta (an Off step followed by an On
step the same day) pauses CO₂ by default: off when the siesta's fade starts,
back on `siesta_on_before` minutes before the light comes back; with
`siesta` = "keep" it stays on. A watchdog checks every minute and switches
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
from .texts import t

_LOGGER = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "control": False, "on_before": 60, "off_before": 60, "max_hours": 10,
    "siesta": "off", "siesta_on_before": 30,
}
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
        self.siesta_off = s["siesta"] != "keep"
        self.siesta_on_before = int(s["siesta_on_before"])
        self._starting = starting
        self._unsub = None
        self._busy = False

    # ---- the window ---------------------------------------------------

    def window(self, day: date | None = None) -> tuple[datetime | None, datetime | None, str]:
        """(on, off, explanation) for a day; (None, None, why) if CO₂ stays off."""
        sched = self.scheduler
        if not sched.enabled:
            return None, None, t("ctl_schedule_off")
        day = day or dt_util.now().date()
        tz = dt_util.get_default_time_zone()
        today = [s for s in sched.steps if day.weekday() in s.get("days", range(7))]
        ons = [s for s in today if s["target"] != OFF_TARGET]
        offs = [s for s in today if s["target"] == OFF_TARGET]
        if not ons or not offs:
            return None, None, t("ctl_no_steps")
        first_on = min(datetime.combine(day, sched.run_time(s), tzinfo=tz) for s in ons)
        last_off = max(datetime.combine(day, sched.effective_time(s), tzinfo=tz) for s in offs)
        if last_off <= first_on:
            return None, None, t("ctl_off_before_on")
        on = max(first_on - timedelta(minutes=self.on_before), datetime.combine(day, time(0, 0), tzinfo=tz))
        off = last_off - timedelta(minutes=self.off_before)
        if off <= on:
            return None, None, t("ctl_no_time")
        note = ""
        if off - on > timedelta(hours=self.max_hours):
            on = off - timedelta(hours=self.max_hours)
            note = t("ctl_shortened", hours=f"{self.max_hours:g}")
        return on, off, t("ctl_window", on=f"{on:%H:%M}", off=f"{off:%H:%M}", note=note)

    def pauses(self, day: date | None = None) -> list[tuple[datetime, datetime]]:
        """Siesta pauses inside the day's window: (CO₂ off, CO₂ back on)."""
        on, off, _ = self.window(day)
        if on is None or not self.siesta_off:
            return []
        sched = self.scheduler
        day = day or dt_util.now().date()
        tz = dt_util.get_default_time_zone()
        today = sorted(
            (s for s in sched.steps if day.weekday() in s.get("days", range(7))),
            key=lambda s: sched.run_window(s)[0],
        )
        pauses = []
        for i, step in enumerate(today):
            if step["target"] != OFF_TARGET:
                continue
            back = next((s for s in today[i + 1:] if s["target"] != OFF_TARGET), None)
            if back is None:
                continue  # the evening Off step
            start = max(on, datetime.combine(day, sched.run_time(step), tzinfo=tz))  # the siesta's fade starts
            end = min(off, datetime.combine(day, sched.run_time(back), tzinfo=tz)
                      - timedelta(minutes=self.siesta_on_before))
            if end > start:
                pauses.append((start, end))
        return pauses

    def intervals(self, day: date | None = None) -> list[tuple[datetime, datetime, bool]]:
        """When CO₂ is on during a day: (on, off, on after a siesta), split by siesta pauses."""
        on, off, _ = self.window(day)
        if on is None:
            return []
        result, start, after_siesta = [], on, False
        for pause_start, pause_end in self.pauses(day):
            result.append((start, pause_start, after_siesta))
            start, after_siesta = pause_end, True
        result.append((start, off, after_siesta))
        return [i for i in result if i[1] > i[0]]

    def next_event(self, now: datetime | None = None) -> tuple[datetime, str, bool] | None:
        """(when, 'on' or 'off', for a siesta) of the next CO₂ switch, today or in the next days."""
        if not self.enabled:
            return None
        now = now or dt_util.now()
        for offset in range(8):
            day = now.date() + timedelta(days=offset)
            intervals = self.intervals(day)
            for i, (on, off, after_siesta) in enumerate(intervals):
                if now < on:
                    return on, "on", after_siesta
                if now < off:
                    return off, "off", i < len(intervals) - 1
        return None

    def in_window(self, now: datetime | None = None) -> bool:
        now = now or dt_util.now()
        return any(on <= now < off for on, off, _ in self.intervals(now.date()))

    def summary(self) -> str:
        if not self.enabled:
            return t("ctl_not_controlled")
        on, off, why = self.window()
        if on is None:
            return t("ctl_off_today", why=why)
        seconds = sum((b - a).total_seconds() for a, b, _ in self.intervals())
        hours = f"{seconds / 3600:.1f}".removesuffix(".0")
        for start, end in self.pauses():
            why += t("ctl_siesta", start=f"{start:%H:%M}", end=f"{end:%H:%M}")
        return t("ctl_window_hours", window=why, hours=hours)

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

    def _held(self) -> bool:
        """Maintenance/photo mode switched CO₂ off and it isn't back on yet."""
        return bool(self.scheduler.held.get("co2"))

    async def catch_up(self) -> None:
        """If CO₂ missed its start (HA wasn't running, control just enabled), switch it on now."""
        if not self.enabled:
            return
        now = dt_util.now()
        on = next((a for a, b, _ in self.intervals() if a <= now < b), None)
        state = self._plug()
        if on is None or state is None or state.state != STATE_OFF or self._held():
            return
        # Respect a manual switch-off during this part of the window; after an HA start we can't tell.
        if self._starting or state.last_changed < on:
            await self._switch(True, "the CO₂ window had already started")

    @callback
    def _tick(self, now: datetime) -> None:
        if self._busy:
            return
        state = self._plug()
        if state is None:
            return
        local = dt_util.as_local(now)
        intervals = self.intervals(local.date())
        starting = next((i for i in intervals if i[0] <= local < i[0] + timedelta(minutes=1)), None)
        if starting and state.state != STATE_ON:
            if self._held():
                _LOGGER.info("CO₂ window starts, but maintenance/photo mode keeps CO₂ off")
            else:
                after_siesta = starting[2]
                self.hass.async_create_task(
                    self._switch(True, "the siesta ends soon" if after_siesta else "the CO₂ window starts",
                                 after_siesta=after_siesta)
                )
        elif state.state == STATE_ON and not self.in_window(local):
            ending = next((i for i in intervals if i[1] <= local < i[1] + timedelta(minutes=1)), None)
            if ending and ending is not intervals[-1]:
                reason = "a siesta starts"
            else:
                reason = "the CO₂ window ends" if ending else t("ctl_outside")
            self.hass.async_create_task(self._switch(False, reason, warn=not ending))

    async def _switch(self, turn_on: bool, reason: str, warn: bool = False, after_siesta: bool = False) -> None:
        self._busy = True
        try:
            _LOGGER.info("CO₂ %s: %s", "on" if turn_on else "off", reason)
            if after_siesta and self.scheduler.co2 is not None:
                # CO₂ was only paused: the interlock needs this lead, not the full one
                self.scheduler.co2.short_lead(self.siesta_on_before)
            await self.hass.services.async_call(
                "homeassistant", "turn_on" if turn_on else "turn_off",
                {"entity_id": self.entity_id}, blocking=True,
            )
            if warn:
                persistent_notification.async_create(
                    self.hass,
                    t("ctl_switched_off_msg", reason=reason, summary=self.summary()),
                    title=t("ctl_title"),
                    notification_id="weekaqua_co2_control",
                )
        except Exception as err:  # noqa: BLE001 - tell the user, the plug's own schedule is the backstop
            _LOGGER.error("Couldn't switch CO₂ %s: %s", "on" if turn_on else "off", err)
            persistent_notification.async_create(
                self.hass,
                t("ctl_failed_msg", what=t("on_word") if turn_on else t("off_word"), error=err),
                title=t("ctl_title"),
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
            "siesta": "off" if self.siesta_off else "keep",
            "siesta_on_before": self.siesta_on_before,
            "window_today": why,
            "pauses_today": [f"{a:%H:%M}–{b:%H:%M}" for a, b in self.pauses()] if self.enabled else [],
            "in_window": self.in_window() if self.enabled else None,
        }
