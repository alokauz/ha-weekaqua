"""Buttons: return to the light's own schedule, sync its clock."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WeekAquaConfigEntry
from .const import CMD_ADVANCED_SCHEDULE, CMD_SIMPLE_SCHEDULE, clock_cmd
from .entity import WeekAquaEntity
from .texts import t


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeekAquaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [
            WeekAquaResendButton(device),
            WeekAquaBackToScheduleButton(device),
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


class WeekAquaResendButton(WeekAquaEntity, ButtonEntity):
    """Send what Home Assistant believes the light shows, e.g. after using the phone app."""

    _attr_translation_key = "resend"
    _attr_icon = "mdi:sync"

    def __init__(self, device) -> None:
        super().__init__(device, "resend")

    async def async_press(self) -> None:
        await self._device.resend()


class WeekAquaBackToScheduleButton(WeekAquaEntity, ButtonEntity):
    """After a manual change: put the light where the schedule says it should be now.

    Continues an interrupted fade for its remaining time, otherwise fades there
    over a minute. Ends maintenance/photo mode too.
    """

    _attr_translation_key = "back_to_schedule"
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, device) -> None:
        super().__init__(device, "back_to_schedule")

    async def async_press(self) -> None:
        sched = self._device.scheduler
        if sched.override:
            await sched.end_override()
        else:
            await sched.apply_current(min_transition=60, source=t("src_back"))
