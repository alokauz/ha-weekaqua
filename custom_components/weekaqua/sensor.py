"""When the next schedule step runs, and what it does."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WeekAquaConfigEntry
from .entity import WeekAquaEntity
from .const import total_power
from .schedule import OFF_TARGET, describe_step


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [
            WeekAquaPower(device),
            WeekAquaNextStep(device),
            WeekAquaCurrentStep(device),
            WeekAquaScheduleSteps(device),
        ]
    )


class WeekAquaNextStep(WeekAquaEntity, SensorEntity):
    _attr_translation_key = "next_step"
    _attr_icon = "mdi:calendar-arrow-right"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, device) -> None:
        super().__init__(device, "next_step")
        self._scheduler = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        if not self._scheduler.enabled:
            return None
        return self._scheduler.next_step()[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        step, _ = self._scheduler.next_step()
        if not self._scheduler.enabled or step is None:
            return {}
        return {"step": describe_step(step, self._device.presets)}


class WeekAquaCurrentStep(WeekAquaEntity, SensorEntity):
    """The schedule step that's in effect now (the last one that ran)."""

    _attr_translation_key = "current_step"
    _attr_icon = "mdi:calendar-check"

    def __init__(self, device) -> None:
        super().__init__(device, "current_step")
        self._scheduler = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str | None:
        if not self._scheduler.enabled:
            return "Schedule off"
        step, _ = self._scheduler.last_step()
        if step is None:
            return None
        return describe_step(step, self._device.presets)[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        step, when = self._scheduler.last_step()
        if not self._scheduler.enabled or step is None:
            return {}
        return {"started": when.isoformat()}


class WeekAquaScheduleSteps(WeekAquaEntity, SensorEntity):
    """The whole schedule: the state is a short summary, each step is an attribute."""

    _attr_translation_key = "schedule_steps"
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, device) -> None:
        super().__init__(device, "schedule_steps")
        self._scheduler = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        steps = self._scheduler.steps
        if not steps:
            return "No steps"
        parts = []
        for step in steps:
            target = "Off" if step["target"] == OFF_TARGET else f"On {step['target']}"
            parts.append(f"{step['time']} {target}")
        summary = " → ".join(parts)
        return summary if len(summary) <= 255 else summary[:252] + "..."

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            f"step_{i + 1}": describe_step(step, self._device.presets)
            for i, step in enumerate(self._scheduler.steps)
        }


class WeekAquaPower(WeekAquaEntity, SensorEntity):
    """Total power like the app's 'Total power' slider (100 % = maximum)."""

    _attr_translation_key = "power"
    _attr_icon = "mdi:lightning-bolt"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, device) -> None:
        super().__init__(device, "power")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float:
        return round(total_power(self._device.levels), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"limit_active": self._device.power_limit}
