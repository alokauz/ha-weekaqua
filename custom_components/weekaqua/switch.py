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
    device = entry.runtime_data
    async_add_entities(
        [
            WeekAquaScheduleSwitch(device),
            WeekAquaAcclimationSwitch(device),
            WeekAquaModeSwitch(device, "maintenance", "mdi:wrench-clock"),
            WeekAquaModeSwitch(device, "photo", "mdi:camera"),
        ]
    )


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


class WeekAquaAcclimationSwitch(WeekAquaEntity, SwitchEntity):
    """On = acclimation running. Off pauses it (holds the current level).

    Turning it on when no program is running starts one with the settings from
    Configure. Stopping (back to normal) is done under Configure.
    """

    _attr_translation_key = "acclimation"
    _attr_icon = "mdi:sprout"

    def __init__(self, device) -> None:
        super().__init__(device, "acclimation")
        self._acc = device.acclimation

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._acc.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self._acc.running and not self._acc.paused

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._acc.paused:
            await self._acc.async_resume()
        elif not self._acc.running:
            await self._acc.async_start()
            await self._device.scheduler.apply_current()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._acc.async_pause()


class WeekAquaModeSwitch(WeekAquaEntity, SwitchEntity):
    """Maintenance / photo mode: a preset for a while, then back to the schedule by itself."""

    def __init__(self, device, mode: str, icon: str) -> None:
        super().__init__(device, f"{mode}_mode")
        self._mode = mode
        self._attr_translation_key = f"{mode}_mode"
        self._attr_icon = icon
        self._sched = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._sched.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return bool(self._sched.override and self._sched.override["mode"] == self._mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        settings = self._device.modes[self._mode]
        attrs = {"preset": settings["preset"], "minutes": settings["minutes"]}
        if self.is_on:
            attrs["ends_at"] = self._sched.override_info()["until"]
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        settings = self._device.modes[self._mode]
        await self._sched.start_override(self._mode, settings["preset"], settings["minutes"])

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self._sched.end_override()
