"""Turns the integration's own schedule on or off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WeekAquaConfigEntry
from .entity import WeekAquaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([WeekAquaScheduleSwitch(entry.runtime_data)])


class WeekAquaScheduleSwitch(WeekAquaEntity, SwitchEntity, RestoreEntity):
    """When turned on, the light jumps to where the schedule should be."""

    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, device) -> None:
        super().__init__(device, "schedule")
        self._scheduler = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self.async_write_ha_state))
        if (last := await self.async_get_last_state()) is not None:
            self._scheduler.enabled = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self._scheduler.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        from .schedule import describe_step

        return {
            "steps": [describe_step(s, self._device.presets) for s in self._scheduler.steps]
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._scheduler.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._scheduler.set_enabled(False)
