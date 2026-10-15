"""Preset picker with the app's built-in modes."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WeekAquaConfigEntry
from .entity import WeekAquaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([WeekAquaPreset(entry.runtime_data)])


class WeekAquaPreset(WeekAquaEntity, SelectEntity, RestoreEntity):
    """Shows the preset when the current levels match one exactly."""

    _attr_translation_key = "preset"
    _attr_icon = "mdi:palette"
    _attr_assumed_state = True
    def __init__(self, device) -> None:
        super().__init__(device, "preset")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))
        if (last := await self.async_get_last_state()) is not None:
            recent = last.attributes.get("recent_presets") or []
            self._device.recent = [n for n in recent if n in self._device.custom_names]
            self.async_write_ha_state()

    @property
    def options(self) -> list[str]:
        """Own presets on top, most recently used first."""
        return self._device.ordered_presets()

    @property
    def extra_state_attributes(self) -> dict:
        return {"recent_presets": list(self._device.recent)}

    @property
    def current_option(self) -> str | None:
        return self._device.preset_for(self._device.levels)

    async def async_select_option(self, option: str) -> None:
        await self._device.apply_preset(option)
