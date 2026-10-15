"""Buttons: return to the light's own schedule, sync its clock."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WeekAquaConfigEntry
from .const import CMD_ADVANCED_SCHEDULE, CMD_SIMPLE_SCHEDULE, clock_cmd
from .entity import WeekAquaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [
            WeekAquaButton(device, "sync_clock", "mdi:clock-check", None),
            WeekAquaButton(device, "simple_schedule", "mdi:calendar-clock", CMD_SIMPLE_SCHEDULE),
            WeekAquaButton(device, "advanced_schedule", "mdi:calendar-clock-outline", CMD_ADVANCED_SCHEDULE),
        ]
    )


class WeekAquaButton(WeekAquaEntity, ButtonEntity):
    """Syncs the clock, then optionally switches schedule mode (like the app)."""

    def __init__(self, device, key: str, icon: str, mode_cmd: bytes | None) -> None:
        super().__init__(device, key)
        self._attr_translation_key = key
        self._attr_icon = icon
        self._mode_cmd = mode_cmd

    async def async_press(self) -> None:
        now = dt_util.now()
        payloads = [clock_cmd(now.hour, now.minute, now.second)]
        if self._mode_cmd:
            # Handing control back to the light's schedule stops any fade.
            self._device.cancel_fade()
            payloads.append(self._mode_cmd)
        await self._device.send(*payloads)
