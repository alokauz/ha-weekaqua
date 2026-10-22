"""When the next schedule step runs, and what it does."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.util import dt as dt_util

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
            WeekAquaLastCommand(device),
            WeekAquaCO2Schedule(device),
            WeekAquaStepChannels(device),
            WeekAquaLightPlan(device),
            WeekAquaLightToday(device),
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

    def _next(self):
        """('step', step, when) or ('co2', 'on'/'off', when), whichever comes first."""
        if not self._scheduler.enabled:
            return None
        step, when = self._scheduler.next_step()
        co2 = self._device.co2_control.next_event() if self._device.co2_control else None
        if co2 and (when is None or co2[0] < when):
            return ("co2", co2[1], co2[0])
        return ("step", step, when) if step is not None else None

    @property
    def native_value(self) -> datetime | None:
        nxt = self._next()
        return nxt[2] if nxt else None

    @property
    def icon(self) -> str:
        nxt = self._next()
        if nxt is None:
            return "mdi:calendar-arrow-right"
        if nxt[0] == "co2":
            return "mdi:molecule-co2"
        return STEP_ICONS[self._scheduler.step_kind(nxt[1], nxt[2])]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self._next()
        if nxt is None:
            return {}
        if nxt[0] == "co2":
            control = self._device.co2_control
            what = "CO₂ on" if nxt[1] == "on" else "CO₂ off"
            when = nxt[2].strftime("%H:%M")
            detail = (
                f"{control.on_before} min before the first On step"
                if nxt[1] == "on" else f"{control.off_before} min before the light is off"
            )
            return {"step": f"{when} · {what} ({detail})", "kind": f"co2_{nxt[1]}"}
        step, when = nxt[1], nxt[2]
        attrs = {"step": self._scheduler.describe(step), "kind": self._scheduler.step_kind(step, when)}
        if step["target"] != OFF_TARGET:
            attrs["channels"] = self._scheduler.describe_levels(step)
        # A CO₂ switch at the same minute is mentioned alongside the light step
        co2 = self._device.co2_control.next_event() if self._device.co2_control else None
        if co2 and co2[0] == when:
            attrs["also"] = f"{when:%H:%M} · CO₂ {co2[1]}"
        return attrs


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
        attrs = {"started": when.isoformat(), "kind": self._scheduler.step_kind(step, when)}
        if step["target"] != OFF_TARGET:
            attrs["channels"] = self._scheduler.describe_levels(step)
        return attrs


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
        control = self._device.co2_control
        if control is not None and control.enabled:
            on, off, _ = control.window()
            if on is not None:
                timed = [(p.split(" · ")[0], p) for p in parts]
                timed += [(f"{on:%H:%M}", f"{on:%H:%M} · CO₂ on"), (f"{off:%H:%M}", f"{off:%H:%M} · CO₂ off")]
                # CO₂ on before a light step at the same minute, CO₂ off after it
                order = {"CO₂ on": 0, "CO₂ off": 2}
                parts = [p for _, p in sorted(timed, key=lambda tp: (tp[0], order.get(tp[1].split(" · ", 1)[1], 1)))]
        summary = " | ".join(parts)
        acc = self._device.acclimation
        if acc is not None and acc.running:
            summary += " (acclimation)"
        return summary if len(summary) <= 255 else summary[:252] + "..."

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            f"step_{i + 1}": self._scheduler.describe(step)
            for i, step in enumerate(self._scheduler.steps)
        }
        control = self._device.co2_control
        if control is not None and control.enabled:
            on, off, why = control.window()
            attrs["co2"] = why if on is None else f"on {on:%H:%M}, off {off:%H:%M}"
        return attrs


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
            # What each On step uses now, e.g. "15:00 Nature 70%": "R 36% G 70% B 36% UV 0% · power 61%"
            "on_steps": {
                f"{s['time']} {s['target']} {s.get('brightness', 100) * acc.brightness() / 100:g}%":
                    self._device.scheduler.describe_levels(s)
                for s in self._device.scheduler.steps
                if s["target"] != OFF_TARGET
            },
        }


class WeekAquaLastCommand(WeekAquaEntity, SensorEntity):
    """When a command last reached the light (diagnostic)."""

    _attr_translation_key = "last_command"
    _attr_icon = "mdi:bluetooth-transfer"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device) -> None:
        super().__init__(device, "last_command")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.add_connection_listener(self.async_write_ha_state))

    @property
    def native_value(self):
        return self._device.last_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        return {
            "last_attempt": dt_util.as_local(d.last_attempt).isoformat() if d.last_attempt else None,
            "last_attempt_command": d.last_attempt_what,
            "last_attempt_result": None if d.last_attempt_ok is None else ("delivered" if d.last_attempt_ok else f"failed: {d.last_error}"),
            "delivered_since_start": d.sent_ok,
            "failed_since_start": d.sent_failed,
            "retries_since_start": d.retries,
            "note": "delivered = the Bluetooth write went through; the light can't confirm it applied it",
        }


class WeekAquaCO2Schedule(WeekAquaEntity, SensorEntity):
    """Today's CO₂ window when CO₂ control is on, e.g. '14:00–20:00 (6 h)'."""

    _attr_translation_key = "co2_schedule"
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, device) -> None:
        super().__init__(device, "co2_schedule")
        self._control = device.co2_control

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._device.scheduler.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._control.enabled

    @property
    def native_value(self) -> str:
        return self._control.summary()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        on, off, _ = self._control.window()
        return {
            "on_at": on.isoformat() if on else None,
            "off_at": off.isoformat() if off else None,
            "on_before_first_on_step_minutes": self._control.on_before,
            "off_before_last_off_step_minutes": self._control.off_before,
            "max_hours": self._control.max_hours,
            "co2_entity": self._control.entity_id,
        }


class WeekAquaStepChannels(WeekAquaEntity, SensorEntity):
    """The channel values of the current On step (or the next one), e.g. 'R 31% G 60% B 31% UV 0%'.

    Includes the step's brightness, acclimation, the CO₂ fallback (current step
    only) and the power limit: exactly what the light gets.
    """

    _attr_translation_key = "step_channels"
    _attr_icon = "mdi:palette-swatch-variant"

    def __init__(self, device) -> None:
        super().__init__(device, "step_channels")
        self._scheduler = device.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self.async_write_ha_state))
        if self._device.acclimation is not None:
            self.async_on_remove(self._device.acclimation.add_listener(self.async_write_ha_state))

    def _pick(self):
        """(step, 'now' or 'next', when) for the On step to show."""
        sched = self._scheduler
        if not sched.steps:
            return None
        step, when = sched.last_step()
        if step is not None and step["target"] != OFF_TARGET:
            return step, "now", when
        # During an Off step (or before the first step): the next On step
        for nstep, nwhen in sched._occurrences(dt_util.now(), False):
            if nstep["target"] != OFF_TARGET:
                return nstep, "next", nwhen
        return None

    @property
    def native_value(self) -> str | None:
        picked = self._pick()
        if picked is None:
            return None
        from .device import describe_levels

        step, which, _ = picked
        return describe_levels(self._scheduler.step_levels(step, include_co2=which == "now"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        picked = self._pick()
        if picked is None:
            return {}
        sched = self._scheduler
        step, which, when = picked
        levels = sched.step_levels(step, include_co2=which == "now")
        normal = step.get("brightness", 100)
        acc = sched.acclimation_factor()
        co2 = sched.co2_factor() if which == "now" else 1.0
        reasons = []
        if acc < 1:
            uv = sched.acclimation_uv_factor()
            reasons.append(f"acclimation {acc * 100:g}%" + (f", UV held back to {round(uv * 100):g}%" if uv < acc else ""))
        if co2 < 1:
            reasons.append(f"CO₂ fallback {self._device.co2.fallback}%")
        brightness = f"{round(normal * acc * co2, 1):g}%"
        if reasons:
            brightness += f" ({', '.join(reasons)} of {normal}%)"
        attrs = {
            "applies": "current step" if which == "now" else "next On step",
            "step": f"{step['time']} · {step['target']}",
            "starts": dt_util.as_local(when).isoformat(),
            "brightness": brightness,
            "power": f"{total_power(levels):.0f}%",
            "levels": {"R": levels[0], "G": levels[1], "B": levels[2], "UV": levels[3]},
            "levels_note": "raw values sent to the light, 0-235 (235 = 100 %)",
        }
        if which == "next" and sched.co2 is not None and sched.co2.enabled:
            attrs["co2_note"] = "a CO₂ fallback isn't included for a step that hasn't started"
        return attrs


class WeekAquaLightPlan(WeekAquaEntity, SensorEntity):
    """Today's planned light in full-power hours, with the day's curve for charts."""

    _attr_translation_key = "light_plan"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_unit_of_measurement = "h"
    _attr_suggested_display_precision = 1
    # The curve is large and only useful for today: keep it out of the database
    _unrecorded_attributes = frozenset({"curve"})

    def __init__(self, device) -> None:
        super().__init__(device, "light_plan")
        self._scheduler = device.scheduler
        self._summary: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.add_listener(self._refresh))
        if self._device.acclimation is not None:
            self.async_on_remove(self._device.acclimation.add_listener(self._refresh))
        # A new day can have other steps (weekdays) and acclimation stages
        self.async_on_remove(
            async_track_time_change(self.hass, self._new_day, hour=0, minute=0, second=30)
        )
        self._refresh()

    @callback
    def _new_day(self, _now) -> None:
        self._refresh()

    @callback
    def _refresh(self) -> None:
        from .lightplan import summary

        self._summary = summary(self._scheduler)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._summary.get("planned_full_power_hours")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = dict(self._summary)
        s.pop("planned_full_power_hours", None)
        s["note"] = "full-power hours: 1 h at 100 % power = 1; relative light, not PAR/DLI. CO₂ fallback not included."
        return s


class WeekAquaLightToday(WeekAquaEntity, SensorEntity, RestoreEntity):
    """Light actually delivered today, in full-power hours (resets at midnight)."""

    _attr_translation_key = "light_today"
    _attr_icon = "mdi:white-balance-sunny"
    _attr_native_unit_of_measurement = "h"
    _attr_suggested_display_precision = 2
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, device) -> None:
        super().__init__(device, "light_today")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self._device.restore_light(float(last.state), last.attributes.get("date"))
            except ValueError:
                pass
        self.async_on_remove(self._device.add_listener(self.async_write_ha_state))
        # Keep counting while the light stays the same
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=5))
        )

    @callback
    def _tick(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._device.light_so_far(), 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        from .lightplan import planned_until_now

        return {
            "date": dt_util.now().date().isoformat(),
            "planned_until_now": round(planned_until_now(self._device.scheduler), 2),
            "note": "full-power hours: 1 h at 100 % power = 1; relative light, not PAR/DLI",
        }
