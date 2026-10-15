"""Light entity: R, G, B and UV (shown as the white channel)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGBW_COLOR,
    ATTR_TRANSITION,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WeekAquaConfigEntry
from .const import MAX_LEVEL, PRESETS
from .entity import WeekAquaEntity

ATTR_LEVELS = "channel_levels"
ATTR_TARGET = "target_levels"
ATTR_LAST_ON = "last_on_levels"
ATTR_FADING = "fading"
DEFAULT_LEVELS = PRESETS["Mixed"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([WeekAquaLight(entry.runtime_data)])


class WeekAquaLight(WeekAquaEntity, LightEntity, RestoreEntity):
    """The aquarium light. The light can't report its state, so it is assumed.

    The app's presets are offered as effects, so an automation can fade into one:
    light.turn_on with effect: Nature, transition: 2700
    """

    _attr_name = None
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.RGBW
    _attr_supported_color_modes = {ColorMode.RGBW}
    _attr_supported_features = LightEntityFeature.TRANSITION | LightEntityFeature.EFFECT
    def __init__(self, device) -> None:
        super().__init__(device, "light")
        self._last_on: tuple[int, int, int, int] = DEFAULT_LEVELS

    async def async_added_to_hass(self) -> None:
        """Remember the last levels across restarts (nothing is sent)."""
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self._handle_update))
        if (last := await self.async_get_last_state()) is None:
            return
        if last_on := last.attributes.get(ATTR_LAST_ON):
            self._last_on = tuple(last_on)
        # Restore what the light actually showed; a fade interrupted by a restart
        # stopped there (the schedule continues it after startup, if enabled).
        levels = last.attributes.get(ATTR_LEVELS)
        if levels is not None:
            self._device.restore_levels(tuple(levels))

    @callback
    def _handle_update(self) -> None:
        if any(self._device.target):
            self._last_on = self._device.target
        self.async_write_ha_state()

    def _shown_levels(self) -> tuple[int, int, int, int]:
        return self._device.levels if any(self._device.levels) else self._last_on

    @property
    def effect_list(self) -> list[str]:
        return self._device.ordered_presets()

    @property
    def is_on(self) -> bool:
        return any(self._device.levels)

    @property
    def brightness(self) -> int:
        return max(1, round(max(self._shown_levels()) / MAX_LEVEL * 255))

    @property
    def rgbw_color(self) -> tuple[int, int, int, int]:
        levels = self._shown_levels()
        peak = max(levels) or 1
        return tuple(round(v / peak * 255) for v in levels)

    @property
    def effect(self) -> str | None:
        return self._device.preset_for(self._device.target) or EFFECT_OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_LEVELS: list(self._device.levels),
            ATTR_TARGET: list(self._device.target),
            ATTR_LAST_ON: list(self._last_on),
            ATTR_FADING: self._device.fading,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        transition = kwargs.get(ATTR_TRANSITION, 0)
        effect = kwargs.get(ATTR_EFFECT)
        if effect in self._device.presets:
            # Brightness, if given, scales the preset (255 = as saved).
            scale = kwargs.get(ATTR_BRIGHTNESS, 255) / 255
            await self._device.apply_preset(effect, transition, scale)
            return
        else:
            if ATTR_RGBW_COLOR in kwargs:
                rgbw = kwargs[ATTR_RGBW_COLOR]
            else:
                # Keep the color of where we're heading (or the last color if off)
                base = self._device.target if any(self._device.target) else self._last_on
                peak = max(base) or 1
                rgbw = tuple(round(v / peak * 255) for v in base)
            if not any(rgbw):
                rgbw = (255, 255, 255, 255)
            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
            else:
                base = self._device.target if any(self._device.target) else self._last_on
                brightness = max(1, round(max(base) / MAX_LEVEL * 255))
            scale = brightness / 255 * MAX_LEVEL / 255
            levels = tuple(round(c * scale) for c in rgbw)
        await self._device.set_levels(levels, transition)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.set_levels((0, 0, 0, 0), kwargs.get(ATTR_TRANSITION, 0))
