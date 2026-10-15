"""Config flow: Bluetooth discovery or manual pick."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)

from .const import (
    CHANNELS,
    CONF_FADE_CURVE,
    CONF_FADE_INTERVAL,
    CURVE_LABELS,
    DEFAULT_FADE_INTERVAL,
    FADE_SMOOTHNESS,
    CONF_INPUT_MODE,
    CONF_POWER_LIMIT,
    CONF_PRESETS,
    CONF_SCHEDULE,
    DOMAIN,
    MAX_LEVEL,
    PRESETS,
    total_power,
)
from .schedule import ALL_DAYS, DAY_NAMES, OFF_TARGET, describe_step, step_time

CONF_FAN = "fan"
CONF_REMOVE = "remove"
PERCENT_SLIDER = NumberSelector(
    NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%", mode=NumberSelectorMode.SLIDER)
)

WEK_MANUFACTURER_ID = 0x4657  # advertised bytes 57 46 = model code 5746


def _is_week_aqua(info: BluetoothServiceInfoBleak) -> bool:
    return WEK_MANUFACTURER_ID in info.manufacturer_data or (
        info.name or ""
    ).startswith("B3.0-")


class WeekAquaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WeekAquaOptionsFlow()

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        name = self._discovery.name or self._discovery.address
        if user_input is not None:
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: self._discovery.address, CONF_NAME: name},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders={"name": name}
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            name = self._found.get(address, address)
            return self.async_create_entry(
                title=name, data={CONF_ADDRESS: address, CONF_NAME: name}
            )

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or not _is_week_aqua(info):
                continue
            self._found[info.address] = info.name or info.address
        if not self._found:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {addr: f"{name} ({addr})" for addr, name in self._found.items()}
                    )
                }
            ),
        )


class WeekAquaOptionsFlow(OptionsFlow):
    """Add or remove the user's own presets."""

    def _custom(self) -> dict[str, dict]:
        return dict(self.config_entry.options.get(CONF_PRESETS, {}))

    def _steps(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_SCHEDULE, []))

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_preset"]
        if self._custom():
            menu.append("remove_preset")
        menu.append("add_schedule")
        if self._steps():
            menu.append("remove_schedule")
        menu.append("fade")
        menu.append("power")
        menu.append("display")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input["days"]:
                errors["days"] = "no_days"
            else:
                step = {
                    "time": user_input["time"][:5],
                    "target": user_input["target"],
                    "brightness": int(user_input.get("brightness", 100)),
                    "fade": float(user_input.get("fade", 0)),
                    "days": sorted(int(d) for d in user_input["days"]),
                }
                # "default" = follow the general fade settings
                if user_input.get("curve", "default") != "default":
                    step["curve"] = user_input["curve"]
                if user_input.get("smoothness", "default") != "default":
                    step["smoothness"] = user_input["smoothness"]
                # One step per time: saving the same time again replaces it.
                steps = [s for s in self._steps() if s["time"] != step["time"]] + [step]
                steps.sort(key=step_time)
                return self._save(**{CONF_SCHEDULE: steps})

        presets = self.config_entry.runtime_data.ordered_presets()
        targets = [SelectOptionDict(value=OFF_TARGET, label="Off")] + [
            SelectOptionDict(value=name, label=name) for name in presets
        ]
        days = [SelectOptionDict(value=str(i), label=DAY_NAMES[i]) for i in ALL_DAYS]
        general_curve = self.config_entry.options.get(CONF_FADE_CURVE, "perceptual")
        general_smooth = self.config_entry.options.get(CONF_FADE_INTERVAL, DEFAULT_FADE_INTERVAL)
        curve_options = [
            SelectOptionDict(value="default", label=f"Use general setting ({CURVE_LABELS[general_curve]})"),
            *(SelectOptionDict(value=k, label=v) for k, v in CURVE_LABELS.items()),
        ]
        smoothness_options = [
            SelectOptionDict(value="default", label=f"Use general setting ({FADE_SMOOTHNESS[general_smooth]})"),
            *(SelectOptionDict(value=k, label=v) for k, v in FADE_SMOOTHNESS.items()),
        ]
        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required("time", default=defaults.get("time", "08:00:00")): TimeSelector(),
                vol.Required("target", default=defaults.get("target", presets[0])): SelectSelector(
                    SelectSelectorConfig(options=targets, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("brightness", default=defaults.get("brightness", 100)): NumberSelector(
                    NumberSelectorConfig(min=1, max=100, step=1, unit_of_measurement="%", mode=NumberSelectorMode.BOX)
                ),
                vol.Required("fade", default=defaults.get("fade", 30)): NumberSelector(
                    NumberSelectorConfig(min=0, max=480, step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
                vol.Required("curve", default=defaults.get("curve", "default")): SelectSelector(
                    SelectSelectorConfig(options=curve_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("smoothness", default=defaults.get("smoothness", "default")): SelectSelector(
                    SelectSelectorConfig(options=smoothness_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("days", default=defaults.get("days", [str(i) for i in ALL_DAYS])): SelectSelector(
                    SelectSelectorConfig(options=days, multiple=True, mode=SelectSelectorMode.LIST)
                ),
            }
        )
        current = "\n".join(describe_step(s, presets) for s in self._steps()) or "(none yet)"
        return self.async_show_form(
            step_id="add_schedule",
            data_schema=schema,
            errors=errors,
            description_placeholders={"steps": current},
        )

    async def async_step_remove_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        steps = self._steps()
        if user_input is not None:
            remove = set(user_input["remove"])
            return self._save(**{CONF_SCHEDULE: [s for s in steps if s["time"] not in remove]})
        presets = self.config_entry.runtime_data.presets
        options = [
            SelectOptionDict(value=s["time"], label=describe_step(s, presets)) for s in steps
        ]
        return self.async_show_form(
            step_id="remove_schedule",
            data_schema=vol.Schema(
                {
                    vol.Required("remove", default=[]): SelectSelector(
                        SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_fade(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(**user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="fade",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FADE_INTERVAL, default=options.get(CONF_FADE_INTERVAL, DEFAULT_FADE_INTERVAL)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=value, label=label)
                                for value, label in FADE_SMOOTHNESS.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(
                        CONF_FADE_CURVE, default=options.get(CONF_FADE_CURVE, "perceptual")
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=k, label=v) for k, v in CURVE_LABELS.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(**{CONF_POWER_LIMIT: user_input[CONF_POWER_LIMIT]})
        return self.async_show_form(
            step_id="power",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POWER_LIMIT,
                        default=self.config_entry.options.get(CONF_POWER_LIMIT, True),
                    ): bool
                }
            ),
        )

    async def async_step_display(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(**{CONF_INPUT_MODE: user_input[CONF_INPUT_MODE]})
        return self.async_show_form(
            step_id="display",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INPUT_MODE,
                        default=self.config_entry.options.get(CONF_INPUT_MODE, "slider"),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value="slider", label="Slider"),
                                SelectOptionDict(value="box", label="Type a number"),
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_add_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        custom = self._custom()
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_empty"
            elif name in PRESETS:
                errors[CONF_NAME] = "name_builtin"
            elif self.config_entry.options.get(CONF_POWER_LIMIT, True) and total_power(
                [round(user_input[key] / 100 * MAX_LEVEL) for key in CHANNELS]
            ) > 100.05:
                errors["base"] = "too_much_power"
            else:
                levels = [round(user_input[key] / 100 * MAX_LEVEL) for key in CHANNELS]
                custom[name] = {"levels": levels, "fan": user_input.get(CONF_FAN)}
                return self._save(**{CONF_PRESETS: custom})

        # Pre-fill with what the light is doing now, so "adjust sliders, then save" works.
        device = self.config_entry.runtime_data
        current = user_input or {
            **{key: round(level / MAX_LEVEL * 100) for key, level in zip(CHANNELS, device.levels)},
            **({CONF_FAN: device.fan} if device.fan is not None else {}),
        }
        fields: dict[Any, Any] = {
            vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, "")): TextSelector(),
        }
        for key in CHANNELS:
            fields[vol.Required(key, default=current.get(key, 0))] = PERCENT_SLIDER
        fan_key = (
            vol.Optional(CONF_FAN, description={"suggested_value": current[CONF_FAN]})
            if current.get(CONF_FAN) is not None
            else vol.Optional(CONF_FAN)
        )
        fields[fan_key] = PERCENT_SLIDER
        power = total_power(
            [round(current.get(key, 0) / 100 * MAX_LEVEL) for key in CHANNELS]
        )
        return self.async_show_form(
            step_id="add_preset",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={"power": f"{power:.0f}"},
        )

    async def async_step_remove_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        custom = self._custom()
        if user_input is not None:
            for name in user_input[CONF_REMOVE]:
                custom.pop(name, None)
            return self._save(**{CONF_PRESETS: custom})
        return self.async_show_form(
            step_id="remove_preset",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOVE, default=[]): SelectSelector(
                        SelectSelectorConfig(options=list(custom), multiple=True)
                    )
                }
            ),
        )
