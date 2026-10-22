"""CO₂ interlock: don't give plants full light without CO₂.

Watches a Home Assistant entity that switches the CO₂ (e.g. the solenoid's smart
plug). It counts as *ready* when it has been on for at least the lead time. If
it isn't ready when an On step runs, or turns off during the light period, the
light is held at a fallback brightness until CO₂ is ready again.

An entity being "on" only shows the plug is switched on, not that there is
enough CO₂ in the water: this protects against a plug that didn't switch, a
forgotten timer or an unavailable plug, not against an empty bottle.
The interlock never switches CO₂ itself and only ever lowers the light.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .texts import t

_LOGGER = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {"enabled": False, "entity_id": None, "lead": 60, "fallback": 50}
# If the plug is already on when Home Assistant starts, its "last changed" time
# is the restart, not when it really switched on: treat it as on since before.
RESTART_GRACE = timedelta(minutes=2)


class CO2Interlock:
    def __init__(self, hass: HomeAssistant, settings: dict | None, starting: bool) -> None:
        self.hass = hass
        s = {**DEFAULTS, **(settings or {})}
        self.enabled: bool = bool(s["enabled"] and s["entity_id"])
        self.entity_id: str | None = s["entity_id"]
        self.lead: int = int(s["lead"])
        self.fallback: int = int(s["fallback"])
        self._loaded_at = dt_util.utcnow()
        self._starting = starting
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._timer: Callable[[], None] | None = None

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def start(self) -> None:
        if not self.enabled:
            return
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.entity_id], self._state_changed)
        )
        self._arm_timer()

    @callback
    def stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()
        if self._timer:
            self._timer()
            self._timer = None

    @callback
    def _state_changed(self, _event: Event) -> None:
        self._arm_timer()
        self._notify()

    @callback
    def _arm_timer(self) -> None:
        """Wake up when the lead time has passed, so the light can come up."""
        if self._timer:
            self._timer()
            self._timer = None
        ready_at = self.ready_at()
        if ready_at and ready_at > dt_util.utcnow():
            self._timer = async_track_point_in_utc_time(self.hass, self._lead_passed, ready_at)

    @callback
    def _lead_passed(self, _now: datetime) -> None:
        self._timer = None
        self._notify()

    def _on_since(self) -> datetime | None:
        state = self.hass.states.get(self.entity_id) if self.entity_id else None
        if state is None or state.state != STATE_ON:
            return None
        since = state.last_changed
        if self._starting and since <= self._loaded_at + RESTART_GRACE:
            # Already on when Home Assistant started: count it as ready
            return since - timedelta(minutes=self.lead)
        return since

    def ready_at(self) -> datetime | None:
        since = self._on_since()
        return since + timedelta(minutes=self.lead) if since else None

    def ready(self) -> tuple[bool, str]:
        """(ready, human-readable reason)."""
        if not self.enabled:
            return True, t("co2_interlock_off")
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return False, t("co2_missing", entity=self.entity_id)
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False, t("co2_plug_state", state=t("state_unavailable") if state.state == STATE_UNAVAILABLE else t("state_unknown"))
        if state.state != STATE_ON:
            since = dt_util.as_local(state.last_changed).strftime("%H:%M")
            return False, t("co2_is_off", time=since)
        ready_at = self.ready_at()
        since = dt_util.as_local(self._on_since()).strftime("%H:%M")
        if ready_at > dt_util.utcnow():
            return False, t("co2_waiting", since=since, ready=f"{dt_util.as_local(ready_at):%H:%M}", lead=self.lead)
        return True, t("co2_on_since", since=since)

    def factor(self) -> float:
        """1.0 when ready, else the fallback share (never more than 1)."""
        return 1.0 if self.ready()[0] else min(1.0, self.fallback / 100)

    def diagnostics(self) -> dict[str, Any]:
        ready, reason = self.ready()
        return {
            "enabled": self.enabled,
            "entity_id": self.entity_id,
            "lead_minutes": self.lead,
            "fallback_percent": self.fallback,
            "ready": ready,
            "reason": reason,
        }
