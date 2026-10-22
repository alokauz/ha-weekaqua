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
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    EntitySelector,
    EntitySelectorConfig,
    TimeSelector,
)

from .const import (
    CHANNELS,
    CONF_ACCLIMATION,
    CONF_CO2,
    CONF_MODES,
    DEFAULT_MODES,
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
    POWER_WEIGHTS,
    PRESETS,
    limit_power,
    total_power,
)
from .device import describe_levels
from .co2 import DEFAULTS as CO2_DEFAULTS
from .co2_control import CONTROLLABLE_DOMAINS as CO2_CONTROLLABLE, DEFAULTS as CO2_CONTROL_DEFAULTS
from .acclimation import DEFAULTS as ACCLIMATION_DEFAULTS, Acclimation, describe_minutes
from .schedule import ALL_DAYS, DAY_NAMES, OFF_TARGET, describe_step, resolve_sun_time, step_key, step_time

CONF_FAN = "fan"
CONF_APPLY = "apply"
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
    """The Configure menu: presets, schedule and settings."""

    _editing: str = ""
    _prefill: dict[str, Any] | None = None
    _pending: dict[str, Any] = {}

    def _custom(self) -> dict[str, dict]:
        return dict(self.config_entry.options.get(CONF_PRESETS, {}))

    def _resolved(self, step: dict[str, Any]) -> dict[str, Any]:
        """A step with today's time filled in (for sun-based steps)."""
        if step.get("anchor"):
            return {**step, "time": resolve_sun_time(self.hass, step, dt_util.now().date()) or "--:--"}
        return step

    def _steps(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_SCHEDULE, []))

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Top level: related settings grouped together."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["presets", "schedule", "acclimation", "co2", "modes", "light_settings"],
        )

    async def async_step_presets(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_preset"]
        if self._custom():
            menu += ["edit_preset", "remove_preset"]
        return self.async_show_menu(step_id="presets", menu_options=menu)

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_schedule"]
        if self._steps():
            menu.append("remove_schedule")
        presets = self.config_entry.runtime_data.presets
        current = "\n".join(describe_step(self._resolved(s), presets) for s in self._steps()) or "(no steps yet)"
        return self.async_show_menu(
            step_id="schedule", menu_options=menu, description_placeholders={"steps": current}
        )

    async def async_step_light_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="light_settings", menu_options=["fade", "power", "display"])

    async def async_step_add_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            when = user_input.get("when", "time")
            sun_step = {"anchor": when, "offset": int(user_input.get("offset", 0))} if when != "time" else None
            at = (
                resolve_sun_time(self.hass, sun_step, dt_util.now().date()) if sun_step else user_input["time"][:5]
            ) or "12:00"
            hh, mm = (int(x) for x in at.split(":")[:2])
            if not user_input["days"]:
                errors["days"] = "no_days"
            elif user_input["target"] == "__off__" and hh * 60 + mm < float(user_input.get("fade", 0)):
                errors["fade"] = "fade_before_midnight"
            else:
                step = {
                    **({"anchor": sun_step["anchor"], "offset": sun_step["offset"]} if sun_step else {"time": user_input["time"][:5]}),
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
                # One step per time (or per sun anchor + offset): saving it again replaces it
                steps = [s for s in self._steps() if step_key(s) != step_key(step)] + [step]
                steps.sort(key=lambda s: s.get("time") or "")
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
                vol.Required("when", default=defaults.get("when", "time")): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value="time", label="At a fixed time"),
                            SelectOptionDict(value="sunrise", label="Relative to sunrise"),
                            SelectOptionDict(value="sunset", label="Relative to sunset"),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("time", default=defaults.get("time", "08:00:00")): TimeSelector(),
                vol.Required("offset", default=defaults.get("offset", 0)): NumberSelector(
                    NumberSelectorConfig(min=-360, max=360, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
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
        current = "\n".join(describe_step(self._resolved(s), presets) for s in self._steps()) or "(none yet)"
        acc = self.config_entry.runtime_data.acclimation
        if acc is not None and acc.running:
            current += f"\n(Acclimation is running: {acc.summary()}. These are your normal values; see Configure → Acclimation.)"
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
            return self._save(**{CONF_SCHEDULE: [s for s in steps if step_key(s) not in remove]})
        presets = self.config_entry.runtime_data.presets
        options = [
            SelectOptionDict(value=step_key(s), label=describe_step(self._resolved(s), presets)) for s in steps
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

    async def async_step_acclimation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Settings and start/stop of the acclimation program."""
        device = self.config_entry.runtime_data
        acc = device.acclimation
        errors: dict[str, str] = {}
        if user_input is not None:
            settings = {k: user_input.get(k, ACCLIMATION_DEFAULTS[k]) for k in ACCLIMATION_DEFAULTS}
            for key in ("start_brightness", "brightness_step", "interval_days", "shorten", "shorten_step"):
                settings[key] = int(settings[key])
            settings["uv_holdback"] = bool(settings["uv_holdback"])
            action = user_input.get("action", "save")
            if settings["start_brightness"] < 100 and settings["brightness_step"] <= 0:
                errors["brightness_step"] = "step_zero"
            elif settings["shorten"] > 0 and settings["shorten_step"] <= 0:
                errors["shorten_step"] = "step_zero"
            elif action == "start" and settings["start_brightness"] >= 100 and settings["shorten"] <= 0:
                errors["base"] = "nothing_to_do"
            if not errors:
                if action == "start":
                    acc.settings = {**acc.settings, **settings}
                    await acc.async_start()
                    await device.scheduler.apply_current()
                elif action == "stop":
                    await acc.async_stop()
                    await device.scheduler.apply_current()
                elif action == "back":
                    await acc.async_step_back()
                    await device.scheduler.apply_current(min_transition=300)
                return self._save(**{CONF_ACCLIMATION: settings})

        values = user_input or acc.settings
        def number(maximum: int, unit: str, minimum: int = 0) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(min=minimum, max=maximum, step=1, unit_of_measurement=unit, mode=NumberSelectorMode.BOX)
            )
        actions = [SelectOptionDict(value="save", label="Save settings only")]
        actions.append(SelectOptionDict(value="start", label="Restart from the beginning now" if acc.running else "Start now"))
        if acc.running and acc.stage() > 0:
            actions.append(SelectOptionDict(value="back", label="Go back one step (e.g. algae appeared), and stay there a full interval"))
        if acc.running:
            actions.append(SelectOptionDict(value="stop", label="Stop: back to the normal schedule now"))
        schema = vol.Schema(
            {
                vol.Required("start_brightness", default=values["start_brightness"]): number(100, "%", 10),
                vol.Required("brightness_step", default=values["brightness_step"]): number(50, "%"),
                vol.Required("interval_days", default=values["interval_days"]): number(60, "days", 1),
                vol.Required("shorten", default=values["shorten"]): number(480, "min"),
                vol.Required("shorten_step", default=values["shorten_step"]): number(240, "min"),
                vol.Required("uv_holdback", default=bool(values.get("uv_holdback", False))): bool,
                vol.Required("action", default="save"): SelectSelector(
                    SelectSelectorConfig(options=actions, mode=SelectSelectorMode.LIST)
                ),
            }
        )
        # Preview of what the shown settings do
        preview = Acclimation(self.hass, self.config_entry.entry_id, {k: values.get(k, ACCLIMATION_DEFAULTS[k]) for k in ACCLIMATION_DEFAULTS})
        stages = preview.total_stages()
        days = stages * int(values["interval_days"])
        plan = (
            f"{values['start_brightness']:g}% → 100% brightness"
            + (f", light period {describe_minutes(values['shorten'])} shorter → normal" if values["shorten"] else "")
            + f": {stages} steps, back to normal after {days} days."
            if stages else "These settings change nothing."
        )
        status = acc.summary()
        if acc.running and acc.ends():
            status += f" (back to normal on {acc.ends():%d %b %Y})"
        if acc.running:
            sched = device.scheduler
            for s in sched.steps:
                if s["target"] != "__off__":
                    status += f"\n• {s['time']} {s['target']} at {s.get('brightness', 100) * acc.brightness() / 100:g}%: {sched.describe_levels(s)}"
        has_off = any(s["target"] == "__off__" for s in self._steps())
        return self.async_show_form(
            step_id="acclimation",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "status": status,
                "plan": plan,
                "plan_lines": "\n".join(
                    acc.plan() if acc.running and user_input is None
                    else acc.plan({k: values.get(k, ACCLIMATION_DEFAULTS[k]) for k in ACCLIMATION_DEFAULTS})
                ),
                "off_note": "" if has_off else "\n\nNote: your schedule has no Off step, so the light period can't be shortened.",
            },
        )

    async def async_step_co2(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """CO₂ interlock: hold On steps at a fallback brightness until CO₂ is ready."""
        current = {**CO2_DEFAULTS, **CO2_CONTROL_DEFAULTS, **self.config_entry.options.get(CONF_CO2, {})}
        errors: dict[str, str] = {}
        if user_input is not None:
            entity = user_input.get("entity_id")
            if (user_input.get("enabled") or user_input.get("control")) and not entity:
                errors["entity_id"] = "co2_entity_missing"
            elif user_input.get("control") and entity.split(".")[0] not in CO2_CONTROLLABLE:
                errors["entity_id"] = "co2_not_switchable"
            elif user_input.get("control") and not user_input.get("backstop"):
                errors["backstop"] = "co2_backstop_required"
            else:
                return self._save(**{CONF_CO2: {
                    "enabled": bool(user_input.get("enabled")),
                    "entity_id": entity,
                    "lead": int(user_input["lead"]),
                    "fallback": int(user_input["fallback"]),
                    "control": bool(user_input.get("control")),
                    "on_before": int(user_input["on_before"]),
                    "off_before": int(user_input["off_before"]),
                    "max_hours": float(user_input["max_hours"]),
                }})
            current = {**current, **user_input}
        entity_key = (
            vol.Optional("entity_id", description={"suggested_value": current["entity_id"]})
            if current.get("entity_id") else vol.Optional("entity_id")
        )
        status = self.config_entry.runtime_data.co2.ready()[1] if current.get("enabled") else "off"
        return self.async_show_form(
            step_id="co2",
            data_schema=vol.Schema({
                vol.Required("enabled", default=current["enabled"]): bool,
                entity_key: EntitySelector(EntitySelectorConfig(domain=["switch", "input_boolean", "binary_sensor", "light"])),
                vol.Required("lead", default=current["lead"]): NumberSelector(NumberSelectorConfig(min=0, max=240, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)),
                vol.Required("fallback", default=current["fallback"]): NumberSelector(NumberSelectorConfig(min=0, max=100, step=5, unit_of_measurement="%", mode=NumberSelectorMode.BOX)),
                vol.Required("control", default=current["control"]): bool,
                vol.Required("on_before", default=current["on_before"]): NumberSelector(NumberSelectorConfig(min=0, max=240, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)),
                vol.Required("off_before", default=current["off_before"]): NumberSelector(NumberSelectorConfig(min=0, max=240, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)),
                vol.Required("max_hours", default=current["max_hours"]): NumberSelector(NumberSelectorConfig(min=1, max=16, step=0.5, unit_of_measurement="h", mode=NumberSelectorMode.BOX)),
                vol.Required("backstop", default=bool(current["control"])): bool,
            }),
            errors=errors,
            description_placeholders={
                "status": status,
                "control_status": self.config_entry.runtime_data.co2_control.summary(),
            },
        )

    async def async_step_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Preset and duration of the maintenance and photo modes."""
        device = self.config_entry.runtime_data
        modes = {**DEFAULT_MODES, **self.config_entry.options.get(CONF_MODES, {})}
        if user_input is not None:
            return self._save(**{CONF_MODES: {
                m: {"preset": user_input[f"{m}_preset"], "minutes": int(user_input[f"{m}_minutes"])}
                for m in ("maintenance", "photo")
            }})
        presets = [SelectOptionDict(value=n, label=n) for n in device.ordered_presets()]
        fields: dict[Any, Any] = {}
        for m in ("maintenance", "photo"):
            preset = modes[m]["preset"] if modes[m]["preset"] in device.presets else device.ordered_presets()[0]
            fields[vol.Required(f"{m}_preset", default=preset)] = SelectSelector(
                SelectSelectorConfig(options=presets, mode=SelectSelectorMode.DROPDOWN)
            )
            fields[vol.Required(f"{m}_minutes", default=modes[m]["minutes"])] = NumberSelector(
                NumberSelectorConfig(min=5, max=480, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
            )
        return self.async_show_form(step_id="modes", data_schema=vol.Schema(fields))

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

    # ---- presets -------------------------------------------------------

    def _describe_preset(self, preset: dict[str, Any]) -> str:
        """'R 51% G 100% B 51% UV 30% · fan 40% · power 91%'"""
        levels = preset["levels"]
        text = " ".join(
            f"{label} {round(v / MAX_LEVEL * 100)}%"
            for label, v in zip(("R", "G", "B", "UV"), levels)
        )
        if preset.get("fan") is not None:
            text += f" · fan {preset['fan']:g}%"
        return f"{text} · power {total_power(levels):.0f}%"

    def _headroom(self, values: dict[str, Any]) -> str:
        """How far each channel can go up, with the others as they are."""
        if not self.config_entry.options.get(CONF_POWER_LIMIT, True):
            return "Power limit is off."
        fractions = [values.get(key, 0) / 100 for key in CHANNELS]
        parts = []
        for i, (label, weight) in enumerate(zip(("R", "G", "B", "UV"), POWER_WEIGHTS)):
            others = sum(w * f for j, (w, f) in enumerate(zip(POWER_WEIGHTS, fractions)) if j != i)
            limit = max(0.0, min(1.0, (1 - others) / weight))
            parts.append(f"{label} up to {int(limit * 100)}%")
        return "With the other channels as shown, " + ", ".join(parts) + "."

    def _preset_schema(
        self, values: dict[str, Any], name: str, with_apply: bool
    ) -> vol.Schema:
        fields: dict[Any, Any] = {vol.Required(CONF_NAME, default=name): TextSelector()}
        for key in CHANNELS:
            fields[vol.Required(key, default=values.get(key, 0))] = PERCENT_SLIDER
        fan_key = (
            vol.Optional(CONF_FAN, description={"suggested_value": values[CONF_FAN]})
            if values.get(CONF_FAN) is not None
            else vol.Optional(CONF_FAN)
        )
        fields[fan_key] = PERCENT_SLIDER
        if with_apply:
            fields[vol.Optional(CONF_APPLY, default=values.get(CONF_APPLY, False))] = bool
        return vol.Schema(fields)

    def _check_preset(
        self, user_input: dict[str, Any], editing: str | None
    ) -> tuple[dict[str, str], str, list[int]]:
        """Validate a preset form. Returns (errors, name, levels)."""
        errors: dict[str, str] = {}
        name = user_input[CONF_NAME].strip()
        levels = [round(user_input[key] / 100 * MAX_LEVEL) for key in CHANNELS]
        if not name:
            errors[CONF_NAME] = "name_empty"
        elif name in PRESETS:
            errors[CONF_NAME] = "name_builtin"
        elif name != editing and name in self._custom():
            errors[CONF_NAME] = "name_exists"
        return errors, name, levels

    def _over_limit(self, levels: list[int]) -> bool:
        return self.config_entry.options.get(CONF_POWER_LIMIT, True) and total_power(levels) > 100.05

    async def _finish_add(self, name: str, levels: list[int], fan: float | None) -> ConfigFlowResult:
        custom = self._custom()
        custom[name] = {"levels": levels, "fan": fan}
        return self._save(**{CONF_PRESETS: custom})

    @staticmethod
    def _as_form_values(preset: dict[str, Any]) -> dict[str, Any]:
        values = {key: round(v / MAX_LEVEL * 100) for key, v in zip(CHANNELS, preset["levels"])}
        if preset.get("fan") is not None:
            values[CONF_FAN] = preset["fan"]
        return values

    async def async_step_add_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """New preset, pre-filled with what the light shows now."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, name, levels = self._check_preset(user_input, None)
            if not errors and self._over_limit(levels):
                return await self._ask_power(user_input, "add_preset", name, levels)
            if not errors:
                return await self._finish_add(name, levels, user_input.get(CONF_FAN))

        device = self.config_entry.runtime_data
        prefill, self._prefill = self._prefill, None
        values = user_input or prefill or self._as_form_values(
            {"levels": list(device.levels), "fan": device.fan}
        )
        levels = [round(values.get(key, 0) / 100 * MAX_LEVEL) for key in CHANNELS]
        return self.async_show_form(
            step_id="add_preset",
            data_schema=self._preset_schema(values, values.get(CONF_NAME, ""), False),
            errors=errors,
            description_placeholders={
                "power": f"{total_power(levels):.0f}",
                "headroom": self._headroom(values),
            },
        )

    async def async_step_edit_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of your presets (the list shows its values) and how to edit it."""
        custom = self._custom()
        device = self.config_entry.runtime_data
        if user_input is not None:
            name = user_input["preset"]
            self._editing = name
            how = user_input.get("how", "form")
            if how == "load":
                preset = custom[name]
                try:
                    if preset.get("fan") is not None:
                        await device.set_fan(preset["fan"])
                    await device.set_levels(tuple(preset["levels"]))
                except HomeAssistantError:
                    return self.async_abort(reason="cannot_apply")
                return self.async_abort(reason="loaded", description_placeholders={"name": name})
            if how == "save_light":
                levels = list(device.levels)
                if not any(levels):
                    return self.async_abort(reason="light_off")
                fan = device.fan if device.fan is not None else custom[name].get("fan")
                result = await self._finish_edit(name, levels, fan, False)
                return result if not isinstance(result, str) else self.async_abort(reason=result)
            return await self.async_step_edit_preset_values()
        order = [n for n in device.ordered_presets() if n in custom]
        options = [
            SelectOptionDict(value=n, label=f"{n} — {self._describe_preset(custom[n])}")
            for n in order
        ]
        hows = [
            SelectOptionDict(value="form", label="Edit the values here"),
            SelectOptionDict(value="load", label="Load it onto the light, to adjust it live on the device page"),
            SelectOptionDict(
                value="save_light",
                label=f"Save what the light shows now into it ({describe_levels(device.levels)}, power {total_power(device.levels):.0f}%)",
            ),
        ]
        return self.async_show_form(
            step_id="edit_preset",
            data_schema=vol.Schema(
                {
                    vol.Required("preset", default=order[0]): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    ),
                    vol.Required("how", default="form"): SelectSelector(
                        SelectSelectorConfig(options=hows, mode=SelectSelectorMode.LIST)
                    ),
                }
            ),
        )

    async def async_step_edit_preset_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the picked preset: name, channels, fan; optionally show it on the light."""
        old_name = self._editing
        preset = self._custom()[old_name]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, name, levels = self._check_preset(user_input, old_name)
            if not errors and self._over_limit(levels):
                return await self._ask_power(user_input, "edit_preset_values", name, levels)
            if not errors:
                result = await self._finish_edit(name, levels, user_input.get(CONF_FAN), bool(user_input.get(CONF_APPLY)))
                if isinstance(result, str):
                    errors["base"] = result
                else:
                    return result

        prefill, self._prefill = self._prefill, None
        values = user_input or prefill or self._as_form_values(preset)
        used_by = [describe_step(self._resolved(s)).split(" · ")[0] for s in self._steps() if s["target"] == old_name]
        return self.async_show_form(
            step_id="edit_preset_values",
            data_schema=self._preset_schema(values, values.get(CONF_NAME, old_name), True),
            errors=errors,
            description_placeholders={
                "name": old_name,
                "current": self._describe_preset(preset),
                "used_by": ", ".join(used_by) if used_by else "no schedule steps",
                "headroom": self._headroom(values),
            },
        )

    async def _finish_edit(
        self, name: str, levels: list[int], fan: float | None, apply: bool
    ) -> ConfigFlowResult | str:
        """Save the edited preset (renaming in place). Returns an error key on failure."""
        old_name = self._editing
        if apply:
            device = self.config_entry.runtime_data
            try:
                if fan is not None:
                    await device.set_fan(fan)
                await device.set_levels(tuple(levels))
            except HomeAssistantError:
                return "cannot_apply"
        custom = self._custom()
        updated = {
            (name if n == old_name else n): ({"levels": levels, "fan": fan} if n == old_name else p)
            for n, p in custom.items()
        }
        changes: dict[str, Any] = {CONF_PRESETS: updated}
        if name != old_name:
            # Keep schedule steps that use this preset working
            changes[CONF_SCHEDULE] = [
                {**step, "target": name} if step["target"] == old_name else step
                for step in self._steps()
            ]
        return self._save(**changes)

    # ---- 2. over the power limit: scale down or go back ----------------

    async def _ask_power(
        self, user_input: dict[str, Any], back_to: str, name: str, levels: list[int]
    ) -> ConfigFlowResult:
        self._pending = {"input": dict(user_input), "back_to": back_to, "name": name, "levels": levels}
        scaled = list(limit_power(levels))
        return self.async_show_menu(
            step_id="power_over",
            menu_options=["power_scale", "power_back"],
            description_placeholders={
                "power": f"{total_power(levels):.0f}",
                "asked": describe_levels(levels),
                "scaled": describe_levels(scaled),
                "scaled_power": f"{total_power(scaled):.0f}",
            },
        )

    async def async_step_power_over(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        p = self._pending
        return await self._ask_power(p["input"], p["back_to"], p["name"], p["levels"])

    async def async_step_power_scale(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        pending = self._pending
        levels = list(limit_power(pending["levels"]))
        fan = pending["input"].get(CONF_FAN)
        if pending["back_to"] == "add_preset":
            return await self._finish_add(pending["name"], levels, fan)
        result = await self._finish_edit(pending["name"], levels, fan, bool(pending["input"].get(CONF_APPLY)))
        if isinstance(result, str):
            # Couldn't reach the light: back to the form, scaled values filled in
            self._prefill = {**pending["input"], **{k: round(v / MAX_LEVEL * 100) for k, v in zip(CHANNELS, levels)}, CONF_APPLY: False}
            return await self.async_step_edit_preset_values()
        return result

    async def async_step_power_back(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        pending = self._pending
        self._prefill = pending["input"]
        if pending["back_to"] == "add_preset":
            return await self.async_step_add_preset()
        return await self.async_step_edit_preset_values()

    async def async_step_remove_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        custom = self._custom()
        if user_input is not None:
            for name in user_input[CONF_REMOVE]:
                custom.pop(name, None)
            return self._save(**{CONF_PRESETS: custom})
        options = [
            SelectOptionDict(value=n, label=f"{n} — {self._describe_preset(p)}")
            for n, p in custom.items()
        ]
        return self.async_show_form(
            step_id="remove_preset",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOVE, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )
