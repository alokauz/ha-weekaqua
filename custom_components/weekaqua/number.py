"""Fan speed and per-channel sliders (like the app's spectral settings)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WeekAquaConfigEntry
from .const import CHANNELS, MAX_LEVEL
from .entity import WeekAquaEntity

CHANNEL_ICONS = {
    "red": "mdi:alpha-r-circle",
    "green": "mdi:alpha-g-circle",
    "blue": "mdi:alpha-b-circle",
    "uv": "mdi:weather-sunny-alert",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [WeekAquaFan(device)]
        + [WeekAquaChannel(device, index, key) for index, key in enumerate(CHANNELS)]
    )


class WeekAquaFan(WeekAquaEntity, RestoreNumber):
    """Fan speed in percent."""

    _attr_translation_key = "fan"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:fan"
    _attr_assumed_state = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device) -> None:
        super().__init__(device, "fan")
        self._attr_mode = NumberMode.BOX if device.input_mode == "box" else NumberMode.SLIDER

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))
        if (last := await self.async_get_last_number_data()) is not None:
            self._device.restore_fan(last.native_value)

    @property
    def native_value(self) -> float | None:
        return self._device.fan

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_fan(value)


class WeekAquaChannel(WeekAquaEntity, NumberEntity):
    """One color channel in percent; changing it sends all four channels."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_assumed_state = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device, index: int, key: str) -> None:
        super().__init__(device, f"channel_{key}")
        self._attr_mode = NumberMode.BOX if device.input_mode == "box" else NumberMode.SLIDER
        self._index = index
        self._attr_translation_key = f"channel_{key}"
        self._attr_icon = CHANNEL_ICONS[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float:
        return round(self._device.levels[self._index] / MAX_LEVEL * 100)

    async def async_set_native_value(self, value: float) -> None:
        levels = list(self._device.levels)
        levels[self._index] = round(value / 100 * MAX_LEVEL)
        # Like the app: refuse instead of changing the other channels
        await self._device.set_levels(tuple(levels), strict=True)
