"""Actions for scripts, automations and dashboard cards.

They work on the running program directly (its progress lives in a Store), so
unlike Configure → Acclimation they don't reload the integration.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN
from .device import WeekAquaDevice
from .texts import t

SERVICE_ACCLIMATION_SHIFT = "acclimation_shift"
SERVICE_ACCLIMATION_PAUSE = "acclimation_pause"
SERVICE_ACCLIMATION_RESUME = "acclimation_resume"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_DAYS = "days"

# Which light: a config entry or a device; neither = the only Week Aqua light
TARGET = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_DEVICE_ID): cv.string,
}
TARGET_SCHEMA = vol.Schema(TARGET)
SHIFT_SCHEMA = vol.Schema(
    {**TARGET, vol.Required(ATTR_DAYS): vol.All(vol.Coerce(int), vol.Range(min=-60, max=60))}
)


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders or None
    )


@callback
def _device(hass: HomeAssistant, call: ServiceCall) -> WeekAquaDevice:
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if device_id := call.data.get(ATTR_DEVICE_ID):
        dev = dr.async_get(hass).async_get(device_id)
        ours = [
            e for e in (dev.config_entries if dev else ())
            if (ce := hass.config_entries.async_get_entry(e)) is not None and ce.domain == DOMAIN
        ]
        if not ours:
            raise _error("unknown_device", device_id=device_id)
        entry_id = ours[0]
    if entry_id is None:
        loaded = hass.config_entries.async_loaded_entries(DOMAIN)
        if len(loaded) != 1:
            raise _error("which_light")
        return loaded[0].runtime_data
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise _error("not_loaded", entry_id=entry_id)
    return entry.runtime_data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions (once, for all lights)."""

    def running(call: ServiceCall) -> WeekAquaDevice:
        device = _device(hass, call)
        if not device.acclimation.running:
            raise _error("acclimation_not_running")
        return device

    async def shift(call: ServiceCall) -> None:
        device = running(call)
        await device.acclimation.async_shift(call.data[ATTR_DAYS])
        # Same as Configure → Acclimation → Move: ease into the new level
        await device.scheduler.apply_current(min_transition=300, source=t("src_acclimation"))

    async def pause(call: ServiceCall) -> None:
        await running(call).acclimation.async_pause()

    async def resume(call: ServiceCall) -> None:
        await running(call).acclimation.async_resume()

    hass.services.async_register(DOMAIN, SERVICE_ACCLIMATION_SHIFT, shift, schema=SHIFT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ACCLIMATION_PAUSE, pause, schema=TARGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ACCLIMATION_RESUME, resume, schema=TARGET_SCHEMA)
