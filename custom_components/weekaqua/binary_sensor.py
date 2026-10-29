"""Connection status and CO₂ readiness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import WeekAquaConfigEntry
from .entity import WeekAquaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities([WeekAquaConnection(device), WeekAquaCO2Ready(device)])


class WeekAquaConnection(WeekAquaEntity, BinarySensorEntity, RestoreEntity):
    """On when the last command reached the light (the light can't confirm it applied it).

    Until the first command after a restart or reload, it keeps showing how the
    last one went, instead of "unknown".
    """

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _ATTRS = ("failed_in_a_row", "failing_since", "last_error")

    def __init__(self, device) -> None:
        super().__init__(device, "connection")
        self._restored: State | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state in (STATE_ON, STATE_OFF):
            self._restored = last
        self.async_on_remove(self._device.add_connection_listener(self.async_write_ha_state))

    def _sent_nothing_yet(self) -> bool:
        d = self._device
        return d.last_success is None and not d.failures

    @property
    def is_on(self) -> bool | None:
        if self._sent_nothing_yet():
            # nothing sent yet since start: the last known result, if any
            return self._restored.state == STATE_ON if self._restored else None
        return self._device.failures == 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._sent_nothing_yet() and self._restored:
            return {k: self._restored.attributes.get(k) for k in self._ATTRS}
        d = self._device
        return {
            "failed_in_a_row": d.failures,
            "failing_since": dt_util.as_local(d.first_failure).isoformat() if d.first_failure else None,
            "last_error": d.last_error,
        }


class WeekAquaCO2Ready(WeekAquaEntity, BinarySensorEntity):
    """CO₂ interlock: on when the CO₂ entity has been on for the lead time."""

    _attr_translation_key = "co2_ready"
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, device) -> None:
        super().__init__(device, "co2_ready")
        self._co2 = device.co2

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._co2.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._co2.enabled

    @property
    def is_on(self) -> bool:
        return self._co2.ready()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ready, reason = self._co2.ready()
        ready_at = self._co2.ready_at()
        return {
            "reason": reason,
            "co2_entity": self._co2.entity_id,
            "lead_time_minutes": self._co2.lead,
            "fallback_brightness": self._co2.fallback,
            "ready_at": dt_util.as_local(ready_at).isoformat() if ready_at and not ready else None,
        }
