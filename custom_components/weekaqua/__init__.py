"""Week Aqua aquarium light integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_ACCLIMATION,
    CONF_FADE_CURVE,
    CONF_FADE_INTERVAL,
    CONF_INPUT_MODE,
    CONF_POWER_LIMIT,
    CONF_PRESETS,
    CONF_SCHEDULE,
    DEFAULT_FADE_INTERVAL,
)
from .acclimation import Acclimation
from .device import WeekAquaDevice
from .schedule import WeekAquaScheduler

PLATFORMS = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SENSOR,
]

type WeekAquaConfigEntry = ConfigEntry[WeekAquaDevice]


async def async_setup_entry(hass: HomeAssistant, entry: WeekAquaConfigEntry) -> bool:
    """Set up a light from a config entry."""
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME) or entry.title
    device = WeekAquaDevice(hass, address, name, entry.options.get(CONF_PRESETS, {}))
    device.input_mode = entry.options.get(CONF_INPUT_MODE, "slider")
    device.fade_interval = float(entry.options.get(CONF_FADE_INTERVAL, DEFAULT_FADE_INTERVAL))
    device.fade_curve = entry.options.get(CONF_FADE_CURVE, "perceptual")
    device.power_limit = entry.options.get(CONF_POWER_LIMIT, True)
    device.scheduler = WeekAquaScheduler(hass, device, entry.options.get(CONF_SCHEDULE, []))
    # Acclimation program: scales On steps and moves Off steps earlier until it
    # reaches the normal schedule, then finishes by itself.
    device.acclimation = Acclimation(hass, entry.entry_id, entry.options.get(CONF_ACCLIMATION))
    await device.acclimation.async_load()
    device.scheduler.acclimation = device.acclimation
    entry.runtime_data = device
    # Remember whether HA is starting up before entities restore their state.
    starting = hass.state is not CoreState.running
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    device.scheduler.start()
    entry.async_on_unload(device.scheduler.stop)
    entry.async_on_unload(device.acclimation.add_listener(device.scheduler.reschedule))
    await device.acclimation.async_check()  # step up / finish if days passed while off
    device.acclimation.start_daily_check()
    entry.async_on_unload(device.acclimation.stop_daily_check)
    if starting:
        # After a restart, put the light where the schedule says it should be
        # (continuing a fade that was in progress). Not on reloads, so saving a
        # preset doesn't undo a manual change.
        async def _catch_up(_hass: HomeAssistant) -> None:
            await device.scheduler.apply_current()

        entry.async_on_unload(async_at_started(hass, _catch_up))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: WeekAquaConfigEntry) -> None:
    """Reload so the preset list and effects pick up added or removed presets."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WeekAquaConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
