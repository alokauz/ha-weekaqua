"""Bluetooth connection handling for a Week Aqua light."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
import math

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .texts import t
from .const import (
    DISCONNECT_DELAY,
    DOMAIN,
    MAX_LEVEL,
    PRESETS,
    WRITE_CHAR_PREFIXES,
    limit_power,
    total_power,
    fan_cmd,
    levels_cmd,
)

# A Repairs notice appears after this many failed commands over this long
UNREACHABLE_FAILURES = 3
UNREACHABLE_AFTER = timedelta(minutes=10)

# Shortest time between two steps of a fade (the app also waits 500 ms between writes).
MIN_STEP_INTERVAL = 0.5
SMOOTHNESS_NAMES = {0.5: "fine", 10.0: "medium", 30.0: "coarse", 60.0: "very coarse"}

# Perceived brightness ~ level ** (1 / GAMMA)
GAMMA = 2.2
# During a fade, entity states are refreshed at most this often (plus at the end).
STATE_UPDATE_INTERVAL = 30
# If a fade's final level couldn't be sent, retry it this often, this many times.
FADE_END_RETRY_INTERVAL = 30
FADE_END_RETRIES = 20

_LOGGER = logging.getLogger(__name__)


class WeekAquaDevice:
    """Sends commands to the light, connecting on demand."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        custom_presets: dict[str, dict] | None = None,
    ) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._char: BleakGATTCharacteristic | None = None
        self._disconnect_handle: asyncio.TimerHandle | None = None
        # Last channel levels sent (R, G, B, UV as 0-235). The light can't be read back.
        self.levels: tuple[int, int, int, int] = (0, 0, 0, 0)
        # Where the light is heading (equals levels unless a fade is running).
        self.target: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._listeners: list[Callable[[], None]] = []
        self._fade_task: asyncio.Task | None = None
        self.input_mode = "slider"
        # The running fade, for the Fade sensor (None when no fade runs)
        self.fade_info: dict | None = None
        self.last_fade: dict | None = None
        # Light delivered today, in full-power hours (see lightplan.py)
        self.light_today = 0.0
        self.light_date = None
        self._light_since = None
        # Connection diagnostics
        self.last_success = None
        self.last_error: str | None = None
        self.last_error_time = None
        self.failures = 0
        self.first_failure = None
        self._connection_listeners: list[Callable[[], None]] = []
        # What was last tried (whether or not it got through), and counters since start
        self.last_attempt = None
        self.last_attempt_what: str | None = None
        self.last_attempt_ok: bool | None = None
        self.sent_ok = 0
        self.sent_failed = 0
        self.retries = 0
        # Keep total power at or below 100 %, like the app (Configure can turn it off)
        self.power_limit = True
        # Fade settings (from Configure): shortest seconds between commands, and curve
        self.fade_interval = 10.0  # Medium; set from options in __init__.py
        self.fade_curve = "perceptual"
        self.scheduler = None  # set in __init__.py
        self.acclimation = None  # set in __init__.py
        self.co2 = None  # set in __init__.py
        self.co2_control = None  # set in __init__.py
        self.modes: dict[str, dict] = {}  # set in __init__.py
        # Fan speed in percent, None until it has been set once.
        self.fan: float | None = None
        # App presets first, then the user's own. Custom presets may also set the fan.
        self.presets: dict[str, tuple[int, int, int, int]] = dict(PRESETS)
        self.preset_fans: dict[str, float] = {}
        self.custom_names: list[str] = list(custom_presets or {})
        # Custom presets, most recently used first (restored by the select entity).
        self.recent: list[str] = []
        for preset_name, preset in (custom_presets or {}).items():
            self.presets[preset_name] = _clamp(preset["levels"])
            if preset.get("fan") is not None:
                self.preset_fans[preset_name] = float(preset["fan"])

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener whenever the channel levels change."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def restore_levels(self, levels: tuple[int, int, int, int]) -> None:
        """Set the remembered levels without sending anything (after a restart)."""
        self.levels = self.target = _clamp(levels)
        self._notify()

    @callback
    def restore_fan(self, value: float | None) -> None:
        self.fan = value
        self._notify()

    async def set_fan(self, value: float) -> None:
        await self.send(fan_cmd(value))
        self.fan = value
        self._notify()

    def ordered_presets(self) -> list[str]:
        """Own presets first (last used on top), then the app's presets."""
        recent = [n for n in self.recent if n in self.custom_names]
        rest = [n for n in self.custom_names if n not in recent]
        return recent + rest + list(PRESETS)

    @callback
    def mark_used(self, preset_name: str) -> None:
        if preset_name in self.custom_names:
            self.recent = [preset_name] + [n for n in self.recent if n != preset_name]

    def preset_for(self, levels) -> str | None:
        """Name of the preset with exactly these levels, if any."""
        levels = tuple(levels)
        for preset_name, preset_levels in self.presets.items():
            if preset_levels == levels or (self.power_limit and limit_power(preset_levels) == levels):
                return preset_name
        return None

    async def apply_preset(
        self,
        preset_name: str,
        transition: float = 0,
        scale: float | tuple[float, float, float, float] = 1.0,
        fade_interval: float | None = None,
        fade_curve: str | None = None,
        source: str | None = None,
    ) -> None:
        """Go to a preset (fading if requested) and set its fan speed, if it has one.

        scale is one factor for all channels, or one per channel (R, G, B, UV).
        """
        self.mark_used(preset_name)
        if (fan := self.preset_fans.get(preset_name)) is not None and fan != self.fan:
            await self.set_fan(fan)
        scales = scale if isinstance(scale, tuple) else (scale,) * 4
        levels = tuple(round(v * f) for v, f in zip(self.presets[preset_name], scales))
        await self.set_levels(levels, transition, fade_interval, fade_curve, source=source)

    @property
    def fading(self) -> bool:
        return self._fade_task is not None and not self._fade_task.done()

    @callback
    def cancel_fade(self) -> None:
        """Stop a running fade where it is."""
        was_fading = self.fading
        if was_fading:
            self._fade_task.cancel()
            self._end_fade_info(completed=False)
        self._fade_task = None
        self.target = self.levels
        if was_fading:
            self._notify()  # states may be up to 30 s behind during a fade

    async def set_levels(
        self,
        levels: tuple[int, int, int, int],
        transition: float = 0,
        fade_interval: float | None = None,
        fade_curve: str | None = None,
        strict: bool = False,
        source: str | None = None,
    ) -> None:
        """Go to new channel levels, instantly or fading over `transition` seconds.

        source says what started it (for the Fade sensor), e.g. "schedule step 14:00".

        fade_interval / fade_curve override the general fade settings for this fade.
        Above 100 % total power the levels are scaled down, or with strict=True
        (single channel sliders, like the app) the change is refused.
        """
        target = _clamp(levels)
        power = total_power(target)
        # Lowering power is always allowed (e.g. from a level set before the
        # limit was turned on). Everything else, app presets included, is held
        # to 100 % (the app's Gorgeous preset is 101.8 % and is scaled slightly).
        exempt = power <= total_power(self.levels)
        if self.power_limit and power > 100.05 and not exempt:
            if strict:
                raise HomeAssistantError(t("err_power", power=f"{power:.0f}"))
            limited = limit_power(target)
            _LOGGER.info(
                "Power limit: %s would draw %.0f%%, scaled down to %s (%.0f%%)",
                describe_levels(target), power, describe_levels(limited), total_power(limited),
            )
            target = limited
        self.cancel_fade()
        if transition and transition > 0 and target != self.levels:
            self.target = target
            interval = self.fade_interval if fade_interval is None else fade_interval
            curve = fade_curve or self.fade_curve
            # What the Fade sensor shows while this runs
            self.fade_info = {
                "from": self.levels,
                "to": target,
                "began": dt_util.utcnow(),
                "duration": float(transition),
                "curve": curve,
                "interval": interval,
                "source": source or t("src_light"),
            }
            self._fade_task = self.hass.async_create_background_task(
                self._fade(
                    self.levels,
                    target,
                    float(transition),
                    interval,
                    curve,
                ),
                f"weekaqua fade {self.address}",
            )
            self._notify()
            return
        await self._apply(target)
        self.target = target
        self._notify()

    @callback
    def _end_fade_info(self, completed: bool) -> None:
        """Keep a short note of the fade that just ended (interrupted or completed)."""
        if self.fade_info is not None:
            self.last_fade = {**self.fade_info, "ended": dt_util.utcnow(), "completed": completed}
        self.fade_info = None

    async def _apply(self, levels: tuple[int, int, int, int]) -> None:
        await self.send(levels_cmd(levels))
        self._accumulate_light()  # the old levels up to now
        self.levels = levels

    # ---- light delivered today (full-power hours) -----------------------

    @callback
    def _accumulate_light(self) -> None:
        now = dt_util.now()
        if self._light_since is None or self.light_date != now.date():
            if self._light_since is not None and self.light_date != now.date():
                # New day: count from midnight with the levels the light had
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                self._light_since = midnight
                self.light_today = 0.0
            else:
                self._light_since = now
            self.light_date = now.date()
        hours = (now - self._light_since).total_seconds() / 3600
        self.light_today += total_power(self.levels) / 100 * max(0.0, hours)
        self._light_since = now

    def light_so_far(self) -> float:
        """Full-power hours delivered today (1 h at 100 % power = 1)."""
        self._accumulate_light()
        return self.light_today

    @callback
    def restore_light(self, value: float, day: str | None) -> None:
        """After a restart: keep counting today's light (not yesterday's)."""
        now = dt_util.now()
        if day == now.date().isoformat():
            self.light_today = float(value)
            self.light_date = now.date()
            self._light_since = now

    async def _fade(
        self,
        start: tuple[int, int, int, int],
        target: tuple[int, int, int, int],
        duration: float,
        interval: float,
        curve: str,
    ) -> None:
        """Fade in steps, following the clock so slow writes don't stretch the fade.

        With the perceptual curve, channels move evenly in *perceived* brightness
        (gamma 2.2): small steps where the light is dim, bigger ones where it's
        bright. Fade smoothness sets the shortest time between two commands.
        Entity states are only updated every STATE_UPDATE_INTERVAL seconds, to
        keep the recorder database small.
        """
        perceptual = curve == "perceptual"
        delta = max(abs(t - s) for s, t in zip(start, target))
        # Enough steps that no step is bigger than one level (at the steep end
        # of the curve that needs ~GAMMA times more), capped by the smoothness.
        wanted = math.ceil(delta * (GAMMA if perceptual else 1))
        steps = max(1, min(wanted, int(duration / max(MIN_STEP_INTERVAL, interval))))
        loop = asyncio.get_running_loop()
        began = last_state_update = loop.time()
        warned = False
        sent_count = 0
        _LOGGER.info(
            "Fade started: %s -> %s over %s, curve %s, smoothness %s, "
            "%s steps planned, one step every %.1f s (steps with no visible "
            "change are skipped)",
            describe_levels(start),
            describe_levels(target),
            describe_duration(duration),
            "natural" if perceptual else "linear",
            SMOOTHNESS_NAMES.get(interval, f"{interval:g} s"),
            steps,
            duration / steps,
        )
        for step in range(1, steps + 1):
            await asyncio.sleep(max(0.0, began + duration * step / steps - loop.time()))
            levels = _interpolate(start, target, step / steps, perceptual)
            if levels == self.levels and step != steps:
                continue  # no visible change at this point of the curve
            try:
                await self._apply(levels)
                sent_count += 1
            except HomeAssistantError as err:
                if not warned:
                    _LOGGER.warning("Fade step failed, will keep trying: %s", err)
                    warned = True
                continue
            now = loop.time()
            if step == steps or now - last_state_update >= STATE_UPDATE_INTERVAL:
                last_state_update = now
                self._notify()
        _LOGGER.info(
            "Fade finished after %s: %s commands sent, now at %s",
            describe_duration(loop.time() - began),
            sent_count,
            describe_levels(self.levels),
        )
        # Make sure the fade really ends at its target, even if the last step(s)
        # couldn't be sent (e.g. the phone app was connected for a moment).
        for _attempt in range(FADE_END_RETRIES):
            if self.levels == target:
                break
            await asyncio.sleep(FADE_END_RETRY_INTERVAL)
            try:
                await self._apply(target)
            except HomeAssistantError as err:
                _LOGGER.debug("Retrying end of fade failed: %s", err)
                continue
            self._notify()
        else:
            if self.levels != target:
                _LOGGER.warning("Fade could not reach its target %s", target)
        self._end_fade_info(completed=self.levels == target)
        self._fade_task = None
        self._notify()  # final state, and "fading" is now false

    async def send(self, *payloads: bytes) -> None:
        """Send one or more commands, 500 ms apart (like the app)."""
        async with self._lock:
            self.last_attempt = dt_util.utcnow()
            self.last_attempt_what = " + ".join(describe_command(p) for p in payloads)
            try:
                try:
                    await self._write(payloads)
                except (BleakError, TimeoutError) as err:
                    _LOGGER.debug("Write failed (%s), reconnecting and retrying", err)
                    self.retries += 1
                    await self._disconnect()
                    try:
                        await self._write(payloads)
                    except (BleakError, TimeoutError) as err2:
                        await self._disconnect()
                        raise HomeAssistantError(
                            t("err_send", name=self.name, error=err2)
                        ) from err2
            except HomeAssistantError as err:
                self._record_failure(str(err))
                raise
            self._record_success()
            self._schedule_disconnect()

    async def resend(self) -> None:
        """Send what Home Assistant believes the light shows (fan, then channels).

        For when the phone app changed the light, or a command may have been
        missed. Doesn't change any state; a running fade continues.
        """
        payloads = []
        if self.fan is not None:
            payloads.append(fan_cmd(self.fan))
        payloads.append(levels_cmd(self.levels))
        _LOGGER.info("Re-sending current state: %s", " + ".join(describe_command(p) for p in payloads))
        await self.send(*payloads)

    # ---- connection diagnostics ---------------------------------------
    # The light never answers, so "success" means the Bluetooth write went
    # through, not that the light confirmed the change.

    @callback
    def _record_success(self) -> None:
        self.sent_ok += 1
        self.last_attempt_ok = True
        recovered = self.failures > 0
        self.last_success = dt_util.utcnow()
        self.failures = 0
        self.first_failure = None
        if recovered:
            _LOGGER.info("%s is reachable again", self.name)
            ir.async_delete_issue(self.hass, DOMAIN, f"unreachable_{self.address}")
        self._notify_connection()

    @callback
    def _record_failure(self, error: str) -> None:
        self.sent_failed += 1
        self.last_attempt_ok = False
        now = dt_util.utcnow()
        self.failures += 1
        self.last_error = error
        self.last_error_time = now
        if self.first_failure is None:
            self.first_failure = now
        # Tell the user (Settings → Repairs) once it has been failing for a while
        if self.failures >= UNREACHABLE_FAILURES and now - self.first_failure >= UNREACHABLE_AFTER:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"unreachable_{self.address}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="light_unreachable",
                translation_placeholders={
                    "name": self.name,
                    "since": dt_util.as_local(self.first_failure).strftime("%H:%M"),
                    "error": error[:200],
                },
            )
        self._notify_connection()

    @callback
    def add_connection_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._connection_listeners.append(listener)
        return lambda: self._connection_listeners.remove(listener)

    @callback
    def _notify_connection(self) -> None:
        for listener in list(self._connection_listeners):
            listener()

    async def _write(self, payloads: tuple[bytes, ...]) -> None:
        await self._ensure_connected()
        assert self._client is not None and self._char is not None
        response = "write-without-response" not in self._char.properties
        for index, payload in enumerate(payloads):
            if index:
                await asyncio.sleep(0.5)
            _LOGGER.debug("Sending %s", payload.hex().upper())
            await self._client.write_gatt_char(self._char, payload, response=response)

    async def _ensure_connected(self) -> None:
        if self._client is not None and self._client.is_connected:
            return
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise HomeAssistantError(t("err_not_in_range", name=self.name, address=self.address))
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.name,
            disconnected_callback=self._on_disconnected,
        )
        char = None
        for prefix in WRITE_CHAR_PREFIXES:
            for service in client.services:
                for candidate in service.characteristics:
                    if candidate.uuid.startswith(prefix):
                        char = candidate
                        break
                if char:
                    break
            if char:
                break
        if char is None:
            await client.disconnect()
            raise HomeAssistantError(t("err_no_characteristic", name=self.name))
        self._client = client
        self._char = char
        _LOGGER.debug("Connected to %s, using %s", self.name, char.uuid)

    @callback
    def _on_disconnected(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("%s disconnected", self.name)
        self._client = None
        self._char = None

    @callback
    def _schedule_disconnect(self) -> None:
        if self._disconnect_handle:
            self._disconnect_handle.cancel()
        self._disconnect_handle = self.hass.loop.call_later(
            DISCONNECT_DELAY,
            lambda: self.hass.async_create_task(self._disconnect_when_idle()),
        )

    async def _disconnect_when_idle(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def _disconnect(self) -> None:
        if self._disconnect_handle:
            self._disconnect_handle.cancel()
            self._disconnect_handle = None
        client, self._client, self._char = self._client, None, None
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except BleakError:
                pass

    async def async_shutdown(self) -> None:
        """Stop fades and disconnect when the integration unloads."""
        self.cancel_fade()
        async with self._lock:
            await self._disconnect()


def _clamp(levels) -> tuple[int, int, int, int]:
    return tuple(max(0, min(MAX_LEVEL, int(round(v)))) for v in levels)


def _interpolate(start, target, fraction: float, perceptual: bool) -> tuple[int, int, int, int]:
    """Levels at `fraction` (0-1) of the way from start to target."""
    if not perceptual:
        return tuple(round(s + (t - s) * fraction) for s, t in zip(start, target))
    result = []
    for s, t in zip(start, target):
        ps = (s / MAX_LEVEL) ** (1 / GAMMA)
        pt = (t / MAX_LEVEL) ** (1 / GAMMA)
        result.append(round((ps + (pt - ps) * fraction) ** GAMMA * MAX_LEVEL))
    return tuple(result)


def describe_levels(levels) -> str:
    """'R 51% G 100% B 51% UV 30%'"""
    return " ".join(
        f"{name} {round(v / MAX_LEVEL * 100)}%" for name, v in zip(("R", "G", "B", "UV"), levels)
    )


def describe_duration(seconds: float) -> str:
    if seconds >= 60:
        return f"{seconds / 60:.1f} min".replace(".0 min", " min")
    return f"{seconds:.0f} s"


def describe_command(payload: bytes) -> str:
    """A command in words, e.g. 'R 51% G 100% B 51% UV 0%' or 'fan 40%'."""
    if payload[:2] == b"\xfb\xf9":
        return describe_levels(payload[2:6])
    if payload[:1] == b"\xfc":
        return t("cmd_fan", percent=round(payload[1] / MAX_LEVEL * 100))
    if payload[:1] == b"\xff":
        return t("cmd_clock", time=f"{payload[1]:02x}:{payload[2]:02x}:{payload[3]:02x}")
    if payload[:2] == b"\xfd\xf1":
        return t("cmd_simple")
    if payload[:2] == b"\xfd\xf2":
        return t("cmd_advanced")
    return payload.hex().upper()
