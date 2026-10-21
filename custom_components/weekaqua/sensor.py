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

# Icons for what a step does: sun rising, sun setting, or a color change
STEP_ICONS = {
    "sunrise": "mdi:weather-sunset-up",
    "sunset": "mdi:weather-sunset-down",
    "change": "mdi:palette",
}


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
            WeekAquaAcclimationSensor(device),
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
    def icon(self) -> str:
        step, when = self._scheduler.next_step()
        if not self._scheduler.enabled or step is None:
            return "mdi:calendar-arrow-right"
        return STEP_ICONS[self._scheduler.step_kind(step, when)]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        step, when = self._scheduler.next_step()
        if not self._scheduler.enabled or step is None:
            return {}
        return {"step": self._scheduler.describe(step), "kind": self._scheduler.step_kind(step, when)}


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
        return self._scheduler.describe(step)[:255]

    @property
    def icon(self) -> str:
        if not self._scheduler.enabled:
            return "mdi:calendar-remove"
        step, when = self._scheduler.last_step()
        if step is None:
            return "mdi:calendar-check"
        return STEP_ICONS[self._scheduler.step_kind(step, when)]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        step, when = self._scheduler.last_step()
        if not self._scheduler.enabled or step is None:
            return {}
        return {"started": when.isoformat(), "kind": self._scheduler.step_kind(step, when)}


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
        sched = self._scheduler
        factor = sched.acclimation_factor()
        parts = []
        for step in steps:
            at = sched.effective_time(step).strftime("%H:%M")
            if step["target"] == OFF_TARGET:
                parts.append(f"{at} · Off")
            elif factor < 1:
                parts.append(f"{at} · On · {step['target']} {step.get('brightness', 100) * factor:g}%")
            else:
                parts.append(f"{at} · On · {step['target']}")
        summary = " | ".join(parts)
        acc = self._device.acclimation
        if acc is not None and acc.running:
            summary += " (acclimation)"
        return summary if len(summary) <= 255 else summary[:252] + "..."

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            f"step_{i + 1}": self._scheduler.describe(step)
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


class WeekAquaAcclimationSensor(WeekAquaEntity, SensorEntity):
    """'70% · 1 h 30 min shorter', 'Paused · …', 'Not running' or 'Finished'."""

    _attr_translation_key = "acclimation"
    _attr_icon = "mdi:sprout"

    def __init__(self, device) -> None:
        super().__init__(device, "acclimation_status")
        self._acc = device.acclimation

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._acc.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        return self._acc.summary()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        acc = self._acc
        if not acc.running:
            return {"finished": acc.state["finished"]} if acc.state["finished"] else {}
        nxt, ends = acc.next_change(), acc.ends()
        return {
            "brightness": acc.brightness(),
            "light_period_shorter_minutes": acc.shorter_minutes(),
            "day": acc.days() + 1,
            "stage": f"{acc.stage() + 1} of {acc.total_stages() + 1}",
            "next_change": nxt.isoformat() if nxt else None,
            "back_to_normal": ends.isoformat() if ends else None,
            "started": acc.state["started"],
            "paused": acc.paused,
        }
