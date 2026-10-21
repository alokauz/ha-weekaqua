"""Settings → Devices & services → Week Aqua → ⋮ → Download diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import WeekAquaConfigEntry
from .const import total_power


def _iso(value) -> str | None:
    return dt_util.as_local(value).isoformat() if value else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WeekAquaConfigEntry
) -> dict[str, Any]:
    device = entry.runtime_data
    sched = device.scheduler
    acc = device.acclimation
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), {CONF_ADDRESS}),
            "options": dict(entry.options),
            "version": entry.version,
        },
        "light": {
            "levels": list(device.levels),
            "target": list(device.target),
            "fading": device.fading,
            "fan": device.fan,
            "power_percent": round(total_power(device.levels), 1),
            "power_limit": device.power_limit,
            "fade_interval": device.fade_interval,
            "fade_curve": device.fade_curve,
        },
        "connection": {
            "last_success": _iso(device.last_success),
            "failed_in_a_row": device.failures,
            "failing_since": _iso(device.first_failure),
            "last_error": device.last_error,
            "last_error_time": _iso(device.last_error_time),
        },
        "schedule": {
            "enabled": sched.enabled,
            "override": sched.override_info(),
            "steps": [
                {
                    "step": s,
                    "describe": sched.describe(s),
                    "runs_at": sched.run_time(s).strftime("%H:%M"),
                    "fade_minutes": sched.run_fade(s),
                    "channels": sched.describe_levels(s),
                }
                for s in sched.steps
            ],
            "next": _iso(sched.next_step()[1]),
        },
        "acclimation": {"settings": acc.settings, "state": acc.state, "summary": acc.summary()},
        "co2": device.co2.diagnostics(),
    }
