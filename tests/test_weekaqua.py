from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.weekaqua.const import DOMAIN

ADDR = "C8:47:81:04:CB:24"


def fake_client():
    char = MagicMock()
    char.uuid = "0000fff2-0000-1000-8000-00805f9b34fb"
    char.properties = ["write-without-response"]
    other = MagicMock(); other.uuid = "0000fff1-0000-1000-8000-00805f9b34fb"
    service = MagicMock(); service.characteristics = [other, char]
    client = MagicMock()
    client.services = [service]
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def client():
    c = fake_client()
    with patch("custom_components.weekaqua.device.establish_connection", AsyncMock(return_value=c)), \
         patch("custom_components.weekaqua.device.bluetooth.async_ble_device_from_address", return_value=MagicMock()), \
         patch("custom_components.weekaqua.device.asyncio.sleep", AsyncMock()):
        yield c


def sent(client):
    return [call.args[1].hex().upper() for call in client.write_gatt_char.call_args_list]


async def setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"})
    entry.add_to_hass(hass)
    with patch("homeassistant.components.bluetooth.async_setup", return_value=True), \
         patch("homeassistant.components.bluetooth_adapters.async_setup", return_value=True, create=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_and_commands(hass, client):
    entry = await setup(hass)
    ids = sorted(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
    print(ids)
    light = "light.b3_0_l600pro_71"
    fan = "number.b3_0_l600pro_71_5_fan"
    red, blue = "number.b3_0_l600pro_71_1_r", "number.b3_0_l600pro_71_3_b"
    preset = "select.b3_0_l600pro_71_preset"
    simple = "button.b3_0_l600pro_71_resume_simple_schedule"
    call = hass.services.async_call

    await call("light", "turn_on", {"entity_id": light, "rgbw_color": [255, 102, 161, 255], "brightness": 255}, blocking=True)
    assert hass.states.get(preset).state == "Colorful"          # matches the app preset exactly
    await call("light", "turn_on", {"entity_id": light, "brightness": 128}, blocking=True)
    await call("select", "select_option", {"entity_id": preset, "option": "Nature"}, blocking=True)
    assert hass.states.get(red).state == "51"                     # 0x77 / 235
    assert hass.states.get(light).state == "on"
    await call("number", "set_value", {"entity_id": blue, "value": 70}, blocking=True)
    assert hass.states.get(preset).state == "unknown"
    await call("light", "turn_off", {"entity_id": light}, blocking=True)
    assert hass.states.get(red).state == "0" and hass.states.get(light).state == "off"
    await call("light", "turn_on", {"entity_id": light}, blocking=True)   # restores last color
    await call("number", "set_value", {"entity_id": fan, "value": 50}, blocking=True)
    await call("button", "press", {"entity_id": simple}, blocking=True)
    out = sent(client)
    print(out)
    assert out == ["FBF9EB5E94EB5555", "FBF9762F4A765555", "FBF977EB77005555", "FBF977EBA4005555",
                   "FBF9000000005555", "FBF977EBA4005555", "FC76555555555555", out[7], "FDF1555555555555"]
    assert out[7].startswith("FF") and out[7].endswith("55555555")
    print(hass.states.get(preset).attributes["options"])
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_user_flow_finds_light(hass):
    info = MagicMock()
    info.address = ADDR; info.name = "B3.0-L600pro-71"
    info.manufacturer_data = {0x4657: bytes.fromhex("0001c8478104cb24")}
    with patch("custom_components.weekaqua.config_flow.async_discovered_service_info", return_value=[info]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.weekaqua.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDR})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "B3.0-L600pro-71"


async def test_numbers_are_configuration(hass, client):
    entry = await setup(hass)
    reg = er.async_get(hass)
    nums = sorted((e.original_name, e.entity_category) for e in er.async_entries_for_config_entry(reg, entry.entry_id) if e.domain == "number")
    print(nums)
    assert [n for n, _ in nums] == ["1. R", "2. G", "3. B", "4. UV", "5. Fan"]
    assert all(c == "config" for _, c in nums)


async def test_fades(hass, client):
    entry = await setup(hass)
    light = "light.b3_0_l600pro_71"
    call = hass.services.async_call

    # Fade from off into the "Nature" preset over 60 s
    await call("light", "turn_on", {"entity_id": light, "effect": "Nature", "transition": 60}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    print(len(out), out[:3], out[-1])
    assert out[-1] == "FBF977EB77005555"
    assert 5 <= len(out) <= 7                     # Medium (default): one step per 10 s
    assert out[0] != out[-1]
    st = hass.states.get(light)
    assert st.state == "on" and st.attributes["effect"] == "Nature" and st.attributes["fading"] is False

    # Fade out over 30 s, then a plain turn_on comes back at full Nature (not dim)
    client.write_gatt_char.reset_mock()
    await call("light", "turn_off", {"entity_id": light, "transition": 30}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client)[-1] == "FBF9000000005555"
    assert hass.states.get(light).state == "off"
    client.write_gatt_char.reset_mock()
    await call("light", "turn_on", {"entity_id": light}, blocking=True)
    assert sent(client) == ["FBF977EB77005555"]

    # Brightness + effect: preset at 50 %
    client.write_gatt_char.reset_mock()
    await call("light", "turn_on", {"entity_id": light, "effect": "White", "brightness": 128}, blocking=True)
    print(sent(client))
    assert sent(client) == ["FBF93F76350055 55".replace(" ", "")]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_slider_cancels_fade(hass, client):
    import asyncio
    gate = asyncio.Event()
    quick_sleep = asyncio.sleep  # the fixture's instant sleep

    async def slow_sleep(delay):
        if delay > 1:  # only the fade's step waits are frozen
            await gate.wait()
        else:
            await quick_sleep(delay)

    entry = await setup(hass)
    with patch("custom_components.weekaqua.device.asyncio.sleep", slow_sleep):
        await hass.services.async_call("light", "turn_on",
            {"entity_id": "light.b3_0_l600pro_71", "effect": "Nature", "transition": 600}, blocking=True)
        for _ in range(5):
            await asyncio.sleep(0)
        assert hass.states.get("light.b3_0_l600pro_71").attributes["fading"] is True
        await hass.services.async_call("number", "set_value",
            {"entity_id": "number.b3_0_l600pro_71_1_r", "value": 100}, blocking=True)
        for _ in range(5):
            await asyncio.sleep(0)
        st = hass.states.get("light.b3_0_l600pro_71")
        assert st.attributes["fading"] is False
        assert sent(client) == ["FBF9EB0000005555"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_custom_presets(hass, client):
    entry = await setup(hass)
    call = hass.services.async_call
    sel, fan = "select.b3_0_l600pro_71_preset", "number.b3_0_l600pro_71_5_fan"

    # Dial in a look with the sliders and fan, then open Configure -> Add preset
    await call("select", "select_option", {"entity_id": sel, "option": "Nature"}, blocking=True)
    await call("number", "set_value", {"entity_id": "number.b3_0_l600pro_71_4_uv", "value": 30}, blocking=True)
    await call("number", "set_value", {"entity_id": fan, "value": 40}, blocking=True)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] is FlowResultType.MENU and flow["menu_options"] == ["add_preset", "add_schedule", "acclimation", "fade", "power", "display"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_preset"})
    defaults = {str(k): k.default() for k in flow["data_schema"].schema if hasattr(k, "default") and callable(k.default)}
    print(defaults)
    assert defaults["red"] == 51 and defaults["green"] == 100 and defaults["uv"] == 30

    # A built-in name is rejected
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"name": "Nature", "red": 51, "green": 100, "blue": 51, "uv": 30, "fan": 40})
    assert bad["errors"] == {"name": "name_builtin"}
    done = await hass.config_entries.options.async_configure(bad["flow_id"],
        {"name": "My Reef", "red": 51, "green": 100, "blue": 51, "uv": 30, "fan": 40})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    print(entry.options)
    assert entry.options["presets"]["My Reef"] == {"levels": [120, 235, 120, 70], "fan": 40}

    # After the automatic reload: in the dropdown and the effect list
    assert "My Reef" in hass.states.get(sel).attributes["options"]
    assert hass.states.get("light.b3_0_l600pro_71").attributes["effect_list"][0] == "My Reef"
    assert hass.states.get(sel).state == "unknown" or hass.states.get(sel).state == "My Reef"

    # Pick something else, change fan, then choose My Reef: fan first, then colors
    await call("select", "select_option", {"entity_id": sel, "option": "White"}, blocking=True)
    await call("number", "set_value", {"entity_id": fan, "value": 100}, blocking=True)
    client.write_gatt_char.reset_mock()
    await call("select", "select_option", {"entity_id": sel, "option": "My Reef"}, blocking=True)
    assert sent(client) == ["FC5E555555555555", "FBF978EB78465555"]
    assert hass.states.get(sel).state == "My Reef" and hass.states.get(fan).state == "40.0"

    # Fade into it as an effect
    await call("light", "turn_off", {"entity_id": "light.b3_0_l600pro_71"}, blocking=True)
    client.write_gatt_char.reset_mock()
    await call("light", "turn_on", {"entity_id": "light.b3_0_l600pro_71", "effect": "My Reef", "transition": 20}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    assert out[-1] == "FBF978EB78465555" and len(out) >= 2
    assert hass.states.get("light.b3_0_l600pro_71").attributes["effect"] == "My Reef"

    # Remove it
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["menu_options"] == ["add_preset", "edit_preset", "remove_preset", "add_schedule", "acclimation", "fade", "power", "display"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "remove_preset"})
    await hass.config_entries.options.async_configure(flow["flow_id"], {"remove": ["My Reef"]})
    await hass.async_block_till_done()
    assert "My Reef" not in hass.states.get(sel).attributes["options"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_schedule(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 14, 7, 59, 0, tzinfo=tz))
    steps = [
        {"time": "08:00", "target": "Nature", "brightness": 80, "fade": 30, "days": [0, 1, 2, 3, 4, 5, 6]},
        {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6]},
        {"time": "12:00", "target": "White", "brightness": 100, "fade": 0, "days": [5, 6]},   # weekends only
    ]
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
                            options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sw, nxt = "switch.b3_0_l600pro_71_schedule", "sensor.b3_0_l600pro_71_next_step"
    assert hass.states.get(sw).state == "on"
    print(hass.states.get(nxt).state, hass.states.get(nxt).attributes)
    assert hass.states.get(nxt).attributes["step"] == "08:00 · On · Nature 80% · fade 30 min · every day"

    # 08:00 fires: fade to Nature at 80 %
    freezer.move_to(datetime(2026, 10, 14, 8, 0, 0, tzinfo=tz))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    assert out[-1] == "FBF95FBC5F005555" and len(out) > 10          # 0x77*.8, 0xEB*.8
    # Wednesday: the weekend-only 12:00 step is skipped, next is 21:00
    assert hass.states.get(nxt).attributes["step"].startswith("21:00 · Off")

    # Schedule switched off: 21:00 does nothing
    await hass.services.async_call("switch", "turn_off", {"entity_id": sw}, blocking=True)
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 14, 21, 0, 0, tzinfo=tz))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client) == []
    assert hass.states.get(nxt).state == "unknown"

    # Switched back on at 21:30: catches up, continuing the 60-min fade-out (30 min left)
    freezer.move_to(datetime(2026, 10, 14, 21, 30, 0, tzinfo=tz))
    await hass.services.async_call("switch", "turn_on", {"entity_id": sw}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    print(len(out), out[-1])
    assert out[-1] == "FBF9000000005555" and len(out) > 10
    assert hass.states.get("light.b3_0_l600pro_71").state == "off"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_schedule_and_display_forms(hass, client):
    entry = await setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["menu_options"] == ["add_preset", "add_schedule", "acclimation", "fade", "power", "display"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_schedule"})
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"time": "09:30:00", "target": "Fresh", "brightness": 60, "fade": 45, "days": []})
    assert bad["errors"] == {"days": "no_days"}
    await hass.config_entries.options.async_configure(bad["flow_id"],
        {"time": "09:30:00", "target": "Fresh", "brightness": 60, "fade": 45, "days": ["0", "1", "2", "3", "4"]})
    await hass.async_block_till_done()
    assert entry.options["schedule"] == [{"time": "09:30", "target": "Fresh", "brightness": 60, "fade": 45.0, "days": [0, 1, 2, 3, 4]}]
    st = hass.states.get("switch.b3_0_l600pro_71_schedule")
    assert st.attributes["steps"] == ["09:30 · On · Fresh 60% · fade 45 min · Mon–Fri"]

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert "remove_schedule" in flow["menu_options"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "remove_schedule"})
    await hass.config_entries.options.async_configure(flow["flow_id"], {"remove": ["09:30"]})
    await hass.async_block_till_done()
    assert entry.options["schedule"] == []

    # Number input style
    assert hass.states.get("number.b3_0_l600pro_71_1_r").attributes["mode"] == "slider"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "display"})
    await hass.config_entries.options.async_configure(flow["flow_id"], {"input_mode": "box"})
    await hass.async_block_till_done()
    assert hass.states.get("number.b3_0_l600pro_71_1_r").attributes["mode"] == "box"
    assert hass.states.get("number.b3_0_l600pro_71_5_fan").attributes["mode"] == "box"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_startup_catch_up(hass, client, freezer):
    """HA starting up: the schedule must put the light where it should be."""
    from datetime import datetime
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 14, 23, 13, 0, tzinfo=tz))
    hass.set_state(CoreState.not_running)
    steps = [{"time": "15:30", "target": "Nature", "brightness": 100, "fade": 30, "days": [0, 1, 2, 3, 4, 5, 6]},
             {"time": "22:00", "target": "__off__", "brightness": 100, "fade": 45, "days": [0, 1, 2, 3, 4, 5, 6]}]
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert sent(client) == []
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client) == ["FBF9000000005555"]      # 22:00 Off is the current step
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_schedule_step_retries(hass, client, freezer, caplog):
    """Light unreachable at step time (phone app connected): keep retrying."""
    import logging
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from bleak.exc import BleakError

    caplog.set_level(logging.INFO, logger="custom_components.weekaqua")
    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 14, 23, 34, 0, tzinfo=tz))
    steps = [{"time": "23:35", "target": "__off__", "brightness": 100, "fade": 0, "days": [0, 1, 2, 3, 4, 5, 6]},
             {"time": "15:30", "target": "Nature", "brightness": 100, "fade": 15, "days": [0, 1, 2, 3, 4, 5, 6]}]
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call("select", "select_option",
        {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Nature"}, blocking=True)

    # First 3 writes fail (2 tries each: send() retries once internally), then it works
    fails = {"n": 0}
    orig = client.write_gatt_char.side_effect
    async def flaky(*args, **kwargs):
        if fails["n"] < 6:
            fails["n"] += 1
            raise BleakError("device busy")
    client.write_gatt_char.side_effect = flaky
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 14, 23, 35, 0, tzinfo=tz))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    print(out[-2:], [r.getMessage() for r in caplog.records if "weekaqua" in r.name][-4:])
    assert out[-1] == "FBF9000000005555"
    assert hass.states.get("light.b3_0_l600pro_71").state == "off"
    assert "Running schedule step 23:35 (every day): from R 51% G 100% B 51% UV 0% to Off, instantly" in caplog.text
    assert "retrying in 30 s" in caplog.text and "succeeded after retrying" in caplog.text

    # A fade whose last steps can't be sent still ends at its target
    fails["n"] = -10**9
    async def fail_late(*args, **kwargs):
        data = args[1]
        if data == bytes.fromhex("FBF977EB77005555") and fails["n"] < -10**9 + 4:
            fails["n"] += 1
            raise BleakError("busy at the end")
    client.write_gatt_char.side_effect = fail_late
    client.write_gatt_char.reset_mock()
    await hass.services.async_call("light", "turn_on",
        {"entity_id": "light.b3_0_l600pro_71", "effect": "Nature", "transition": 30}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("select.b3_0_l600pro_71_preset").state == "Nature"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_fade_curve_smoothness_and_state_updates(hass, client):
    """Fake clock: check the curve, the command count per smoothness, and throttled states."""
    import asyncio
    entry = await setup(hass)
    light = "light.b3_0_l600pro_71"
    clock = {"t": 0.0}
    loop = asyncio.get_running_loop()
    real_time = loop.time

    async def fake_sleep(delay):          # advance a fake clock instead of waiting
        clock["t"] += max(0.0, delay)

    states = []
    hass.bus.async_listen("state_changed", lambda e: states.append(e.data["entity_id"]) if e.data["entity_id"] == light else None)

    async def run_fade(seconds, options=None):
        if options:
            flow = await hass.config_entries.options.async_init(entry.entry_id)
            flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "fade"})
            await hass.config_entries.options.async_configure(flow["flow_id"], options)
            await hass.async_block_till_done()
        await hass.services.async_call("light", "turn_off", {"entity_id": light}, blocking=True)
        client.write_gatt_char.reset_mock(); states.clear(); clock["t"] = 0.0
        with patch("custom_components.weekaqua.device.asyncio.sleep", fake_sleep), \
             patch.object(loop, "time", lambda: clock["t"]):
            await hass.services.async_call("light", "turn_on",
                {"entity_id": light, "effect": "White", "transition": seconds}, blocking=True)
            await hass.async_block_till_done(wait_background_tasks=True)
        return sent(client)

    # New setups default to Medium smoothness and the Natural curve
    assert entry.runtime_data.fade_interval == 10.0 and entry.runtime_data.fade_curve == "perceptual"
    out = await run_fade(2700)
    assert out[-1] == "FBF97EEB69005555" and len(out) <= 2700 / 10 + 1
    # Fine + natural curve, 45-minute sunrise into White (7E EB 69 00)
    out = await run_fade(2700, {"fade_interval": "0.5", "fade_curve": "perceptual"})
    levels = [bytes.fromhex(c)[3] for c in out]           # green channel
    print("fine/natural:", len(out), "commands,", len(states), "light state updates; first greens", levels[:8])
    assert out[-1] == "FBF97EEB69005555"
    assert all(b - a >= 0 and b - a <= 1 for a, b in zip(levels, levels[1:]))   # never more than 1 level per step
    assert len(states) <= 2700 / 30 + 3                     # states every 30 s, not every step
    mid = bytes.fromhex(out[len(out) // 2])[3]
    assert mid < 235 / 2                                    # natural curve: dim for longer

    # Coarse: at most one command per 30 s
    out = await run_fade(2700, {"fade_interval": "30", "fade_curve": "perceptual"})
    print("coarse:", len(out), "commands")
    assert len(out) <= 2700 / 30 + 1 and out[-1] == "FBF97EEB69005555"

    # Linear + medium
    out = await run_fade(600, {"fade_interval": "10", "fade_curve": "linear"})
    greens = [bytes.fromhex(c)[3] for c in out]
    print("linear/medium:", len(out), "commands, half-way green", greens[len(greens)//2])
    assert len(out) <= 61 and abs(greens[len(greens) // 2] - 118) <= 5
    assert entry.options["fade_interval"] == "10" and entry.options["fade_curve"] == "linear"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_schedule_step_fade_overrides(hass, client, freezer):
    import asyncio
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 14, 7, 0, 0, tzinfo=tz))
    entry = await setup(hass)

    async def add(values):
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_schedule"})
        labels = [o["label"] for o in next(v for k, v in flow["data_schema"].schema.items() if str(k) == "curve").config["options"]]
        await hass.config_entries.options.async_configure(flow["flow_id"], values)
        await hass.async_block_till_done()
        return labels

    base = {"target": "White", "brightness": 100, "fade": 45, "days": [str(i) for i in range(7)]}
    labels = await add({**base, "time": "08:00:00", "curve": "linear", "smoothness": "30"})
    assert labels[0] == "Use general setting (Natural (follows how eyes see brightness))"
    await add({**base, "time": "09:00:00", "target": "__off__", "curve": "default", "smoothness": "default"})
    steps = entry.options["schedule"]
    assert steps[0] == {"time": "08:00", "target": "White", "brightness": 100, "fade": 45.0,
                        "days": [0, 1, 2, 3, 4, 5, 6], "curve": "linear", "smoothness": "30"}
    assert "curve" not in steps[1] and "smoothness" not in steps[1]
    st = hass.states.get("switch.b3_0_l600pro_71_schedule").attributes["steps"]
    print(st)
    assert st[0] == "08:00 · On · White 100% · fade 45 min (linear, coarse) · every day"
    assert st[1] == "09:00 · Off · fade 45 min · every day"

    # Run the 08:00 step on a fake clock: coarse => <= 91 commands, linear => half-way ~ half
    clock = {"t": 0.0}
    loop = asyncio.get_running_loop()
    async def fake_sleep(delay):
        clock["t"] += max(0.0, delay)
    client.write_gatt_char.reset_mock()
    with patch("custom_components.weekaqua.device.asyncio.sleep", fake_sleep), \
         patch("custom_components.weekaqua.schedule.asyncio.sleep", fake_sleep), \
         patch.object(loop, "time", lambda: clock["t"]):
        scheduler = entry.runtime_data.scheduler
        await scheduler._run(scheduler.steps[0], 45 * 60)
        await hass.async_block_till_done(wait_background_tasks=True)
    out = sent(client)
    greens = [bytes.fromhex(c)[3] for c in out]
    print(len(out), greens[len(greens) // 2])
    assert out[-1] == "FBF97EEB69005555" and len(out) <= 91
    assert abs(greens[len(greens) // 2] - 118) <= 6     # linear, not the natural curve
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_recent_presets_sensors_and_logs(hass, client, freezer, caplog):
    import logging
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    caplog.set_level(logging.INFO, logger="custom_components.weekaqua")
    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 15, 0, 58, 30, tzinfo=tz))
    options = {
        "presets": {"Chat GPT": {"levels": [120, 235, 120, 70], "fan": 40},
                    "Night": {"levels": [0, 0, 40, 20], "fan": None},
                    "Reef": {"levels": [50, 80, 235, 235], "fan": None}},
        "schedule": [
            {"time": "00:59", "target": "Chat GPT", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6]},
            {"time": "15:00", "target": "Green", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6], "curve": "linear", "smoothness": "30"},
            {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6]},
        ],
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sel = "select.b3_0_l600pro_71_preset"
    opts = hass.states.get(sel).attributes["options"]
    assert opts[:4] == ["Chat GPT", "Night", "Reef", "Green"]          # own presets first

    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "Reef"}, blocking=True)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.b3_0_l600pro_71", "effect": "Night"}, blocking=True)
    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "White"}, blocking=True)  # built-in: no reorder
    assert hass.states.get(sel).attributes["options"][:4] == ["Night", "Reef", "Chat GPT", "Green"]
    assert hass.states.get("light.b3_0_l600pro_71").attributes["effect_list"][:3] == ["Night", "Reef", "Chat GPT"]

    # Order survives a reload (e.g. after saving a preset)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(sel).attributes["options"][:3] == ["Night", "Reef", "Chat GPT"]

    # Sensors
    steps = hass.states.get("sensor.b3_0_l600pro_71_all_steps")
    print(steps.state, steps.attributes)
    assert steps.state == "00:59 · On · Chat GPT | 15:00 · On · Green | 21:00 · Off"
    assert steps.attributes["step_2"] == "15:00 · On · Green 100% · fade 60 min (linear, coarse) · every day"
    cur = hass.states.get("sensor.b3_0_l600pro_71_current_step")
    print(cur.state)
    assert cur.state == "21:00 · Off · fade 60 min · every day"

    # Run the 00:59 step and check the log explains everything
    await hass.services.async_call("light", "turn_off", {"entity_id": "light.b3_0_l600pro_71"}, blocking=True)
    caplog.clear()
    scheduler = entry.runtime_data.scheduler
    await scheduler._run(scheduler.steps[0], 3600)
    await hass.async_block_till_done(wait_background_tasks=True)
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("custom_components.weekaqua")]
    for line in lines:
        print(line)
    text = "\n".join(lines)
    assert "Running schedule step 00:59 (every day): from R 0% G 0% B 0% UV 0% to preset 'Chat GPT' at 100% (R 51% G 100% B 51% UV 30%), fan 40%, fading over 60 min, curve natural (general setting), smoothness medium (general setting)" in text
    assert "Fade started: R 0% G 0% B 0% UV 0% -> R 51% G 100% B 51% UV 30% over 60 min, curve natural, smoothness medium" in text
    assert "Fade finished after" in text and "commands sent, now at R 51% G 100% B 51% UV 30%" in text
    assert hass.states.get(sel).attributes["options"][0] == "Chat GPT"     # schedule use counts too
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_power_limit(hass, client):
    entry = await setup(hass)
    call = hass.services.async_call
    light, power = "light.b3_0_l600pro_71", "sensor.b3_0_l600pro_71_power"
    g, b = "number.b3_0_l600pro_71_2_g", "number.b3_0_l600pro_71_3_b"

    # Full white with every channel at 100 % (144 %) is scaled down to <= 100 %
    await call("light", "turn_on", {"entity_id": light, "rgbw_color": [255, 255, 255, 255], "brightness": 255}, blocking=True)
    print(sent(client)[-1], hass.states.get(power).state)
    assert sent(client)[-1] == "FBF9A3A3A3A35555"            # 163 each = same color, 99.9 %
    assert float(hass.states.get(power).state) <= 100

    # App preset Gorgeous (101.8 %) is sent unchanged, like the app does
    await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Gorgeous"}, blocking=True)
    assert sent(client)[-1] == "FBF9C15EBCEB5555"
    assert hass.states.get("select.b3_0_l600pro_71_preset").state == "Gorgeous"
    # ...and lowering a channel from there is always allowed, even if still above 100 %
    await call("number", "set_value", {"entity_id": b, "value": 79}, blocking=True)

    # A single slider that would push past 100 % is refused, like the app
    await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Colorful"}, blocking=True)
    client.write_gatt_char.reset_mock()
    with pytest.raises(Exception, match="Total power would be 1"):
        await call("number", "set_value", {"entity_id": g, "value": 100}, blocking=True)
    assert sent(client) == []

    # Custom preset over 100 % can't be saved
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_preset"})
    res = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"name": "Blinding", "red": 100, "green": 100, "blue": 100, "uv": 100})
    # Not a dead end: the total is shown, with "scale down" or "go back"
    assert res["type"] is FlowResultType.MENU and res["step_id"] == "power_over"
    assert res["description_placeholders"]["power"] == "144"
    assert res["description_placeholders"]["scaled"] == "R 69% G 69% B 69% UV 69%"
    back = await hass.config_entries.options.async_configure(res["flow_id"], {"next_step_id": "power_back"})
    assert back["step_id"] == "add_preset"
    vals = {str(k): k.default() for k in back["data_schema"].schema if callable(getattr(k, "default", None))}
    assert vals["name"] == "Blinding" and vals["red"] == 100           # your values are kept
    res = await hass.config_entries.options.async_configure(back["flow_id"],
        {"name": "Blinding", "red": 100, "green": 100, "blue": 100, "uv": 100})
    done = await hass.config_entries.options.async_configure(res["flow_id"], {"next_step_id": "power_scale"})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["presets"]["Blinding"]["levels"] == [163, 163, 163, 163]

    # Turning the limit off (Configure -> Power limit) allows it
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert "power" in flow["menu_options"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "power"})
    await hass.config_entries.options.async_configure(flow["flow_id"], {"power_limit": False})
    await hass.async_block_till_done()
    await call("light", "turn_on", {"entity_id": light, "rgbw_color": [255, 255, 255, 255], "brightness": 255}, blocking=True)
    assert sent(client)[-1] == "FBF9EBEBEBEB5555"
    assert hass.states.get(power).state == "144.0"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_step_icons(hass, client, freezer):
    """Current/Next step icons: sunrise (on after off), change (on while on), sunset (off)."""
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [
        {"time": "08:00", "target": "Nature", "brightness": 100, "fade": 30, "days": every},
        {"time": "13:00", "target": "White", "brightness": 100, "fade": 30, "days": every},
        {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": every},
    ]
    freezer.move_to(datetime(2026, 10, 15, 10, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    cur, nxt = "sensor.b3_0_l600pro_71_current_step", "sensor.b3_0_l600pro_71_next_step"

    def icons():
        return hass.states.get(cur).attributes.get("icon"), hass.states.get(nxt).attributes.get("icon")

    assert icons() == ("mdi:weather-sunset-up", "mdi:palette")              # 10:00
    assert hass.states.get(cur).attributes["kind"] == "sunrise"
    for when, expected in [
        ((14, 0), ("mdi:palette", "mdi:weather-sunset-down")),              # after the midday change
        ((22, 0), ("mdi:weather-sunset-down", "mdi:weather-sunset-up")),    # night: next is tomorrow's sunrise
    ]:
        freezer.move_to(datetime(2026, 10, 15, *when, 0, tzinfo=tz))
        entry.runtime_data.scheduler._notify()
        await hass.async_block_till_done()
        assert icons() == expected, when

    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.b3_0_l600pro_71_schedule"}, blocking=True)
    assert icons() == ("mdi:calendar-remove", "mdi:calendar-arrow-right")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_edit_preset(hass, client):
    options = {
        "presets": {"Chat GPT": {"levels": [120, 235, 120, 70], "fan": 40},
                    "Night": {"levels": [0, 0, 40, 20], "fan": None}},
        "schedule": [{"time": "15:00", "target": "Chat GPT", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6]},
                     {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": [0, 1, 2, 3, 4, 5, 6]}],
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["menu_options"][:3] == ["add_preset", "edit_preset", "remove_preset"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_preset"})
    labels = [o["label"] for o in next(iter(flow["data_schema"].schema.values())).config["options"]]
    print(labels)
    assert labels[0] == "Chat GPT — R 51% G 100% B 51% UV 30% · fan 40% · power 91%"
    assert labels[1] == "Night — R 0% G 0% B 17% UV 9% · power 10%"

    # Pick Chat GPT: the form shows its values, name included
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"preset": "Chat GPT"})
    assert flow["step_id"] == "edit_preset_values"
    defaults = {str(k): k.default() for k in flow["data_schema"].schema if callable(getattr(k, "default", None))}
    assert defaults["name"] == "Chat GPT" and defaults["red"] == 51 and defaults["green"] == 100 and defaults["uv"] == 30
    assert flow["description_placeholders"]["used_by"] == "15:00"

    # Renaming to an existing preset is refused
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"name": "Night", "red": 51, "green": 100, "blue": 51, "uv": 30, "fan": 40})
    assert bad["errors"] == {"name": "name_exists"}

    # Rename + change UV + show on the light now
    client.write_gatt_char.reset_mock()
    done = await hass.config_entries.options.async_configure(bad["flow_id"],
        {"name": "Afternoon", "red": 51, "green": 100, "blue": 51, "uv": 10, "fan": 40, "apply": True})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    print(sent(client))
    assert sent(client) == ["FC5E555555555555", "FBF978EB78185555"]
    assert list(entry.options["presets"]) == ["Afternoon", "Night"]          # same place, new name
    assert entry.options["presets"]["Afternoon"] == {"levels": [120, 235, 120, 24], "fan": 40}
    assert entry.options["schedule"][0]["target"] == "Afternoon"              # schedule followed the rename
    assert "Afternoon" in hass.states.get("select.b3_0_l600pro_71_preset").attributes["options"]

    # Adding a preset with an existing name is refused (edit is for that)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_preset"})
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"name": "Night", "red": 0, "green": 0, "blue": 20, "uv": 10})
    assert bad["errors"] == {"name": "name_exists"}

    # Remove list shows values too
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "remove_preset"})
    labels = [o["label"] for o in next(iter(flow["data_schema"].schema.values())).config["options"]]
    assert labels[0].startswith("Afternoon — R 51% G 100% B 51% UV 10%")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_acclimation(hass, client, freezer):
    """60 % -> 100 % in 10 % steps and 2 h -> normal in 30 min steps, every 7 days; pause; finish."""
    from datetime import datetime, timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    day0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=tz)
    freezer.move_to(day0)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensor, switch = "sensor.b3_0_l600pro_71_acclimation", "switch.b3_0_l600pro_71_acclimation"
    nxt = "sensor.b3_0_l600pro_71_next_step"
    assert hass.states.get(sensor).state == "Not running"

    # Configure -> Acclimation: preview, then start
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "acclimation"})
    print(flow["description_placeholders"]["plan"])
    assert flow["description_placeholders"]["plan"] == "60% → 100% brightness, light period 2 h shorter → normal: 4 steps, back to normal after 28 days."
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"start_brightness": 60, "brightness_step": 0, "interval_days": 7, "shorten": 120, "shorten_step": 30, "action": "start"})
    assert bad["errors"] == {"brightness_step": "step_zero"}
    await hass.config_entries.options.async_configure(bad["flow_id"],
        {"start_brightness": 60, "brightness_step": 10, "interval_days": 7, "shorten": 120, "shorten_step": 30, "action": "start"})
    await hass.async_block_till_done()
    st = hass.states.get(sensor)
    print(st.state, st.attributes)
    assert st.state == "60% · 2 h shorter"
    assert st.attributes["next_change"] == "2026-10-08" and st.attributes["back_to_normal"] == "2026-10-29"
    assert hass.states.get(switch).state == "on"
    # Off step moved 2 h earlier
    assert hass.states.get(nxt).attributes["step"].startswith("15:00 · On")
    sched = entry.runtime_data.scheduler
    assert sched.effective_time(steps[1]).strftime("%H:%M") == "19:00"

    async def run_on_step():
        client.write_gatt_char.reset_mock()
        await sched._run(sched.steps[0], 0)
        await hass.async_block_till_done()
        return sent(client)[-1]

    # On step at 60 %: Nature (77 EB 77 00) * 0.6 = 47 8D 47 00
    assert await run_on_step() == "FBF9478D47005555"

    # One week later at midnight: 70 %, 1 h 30 min shorter
    freezer.move_to(datetime(2026, 10, 8, 0, 0, 10, tzinfo=tz)); async_fire_time_changed(hass); await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "70% · 1 h 30 min shorter"
    assert sched.effective_time(steps[1]).strftime("%H:%M") == "19:30"
    freezer.move_to(datetime(2026, 10, 8, 16, 0, 0, tzinfo=tz)); sched._notify(); await hass.async_block_till_done()
    assert hass.states.get(nxt).attributes["step"] == "19:30 (acclimation, normally 21:00) · Off · every day"
    assert await run_on_step() == "FBF953A453005555"     # 0.7

    # Pause for 3 days: level held, dates move by 3 days
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    freezer.move_to(datetime(2026, 10, 18, 0, 0, 10, tzinfo=tz)); async_fire_time_changed(hass); await hass.async_block_till_done()
    assert hass.states.get(sensor).state.startswith("Paused · 70%")
    freezer.move_to(datetime(2026, 10, 11, 12, 0, 0, tzinfo=tz))   # back to the 11th: paused 3 days (8th -> 11th)
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(sensor).attributes["back_to_normal"] == "2026-11-01"

    # Long after the end: finishes by itself, normal schedule again
    freezer.move_to(datetime(2026, 11, 2, 0, 0, 10, tzinfo=tz)); async_fire_time_changed(hass); await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "Finished"
    assert hass.states.get(switch).state == "off"
    assert sched.effective_time(steps[1]).strftime("%H:%M") == "21:00"
    assert await run_on_step() == "FBF977EB77005555"     # 100 % again
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_preset_headroom_and_live_editing(hass, client):
    options = {"presets": {"Chat GPT": {"levels": [120, 235, 120, 70], "fan": 40}}}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def open_edit():
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        return await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_preset"})

    # Edit here: headroom for each channel, from the preset's values
    flow = await open_edit()
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"preset": "Chat GPT", "how": "form"})
    print(flow["description_placeholders"]["headroom"])
    assert flow["description_placeholders"]["headroom"] == "With the other channels as shown, R up to 73%, G up to 100%, B up to 67%, UV up to 100%."

    # Load onto the light -> adjust live with a slider -> save the light into the preset
    flow = await open_edit()
    client.write_gatt_char.reset_mock()
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {"preset": "Chat GPT", "how": "load"})
    assert res["type"] is FlowResultType.ABORT and res["reason"] == "loaded"
    assert sent(client) == ["FC5E555555555555", "FBF978EB78465555"]
    assert hass.states.get("sensor.b3_0_l600pro_71_power").state == "91.3"
    await hass.services.async_call("number", "set_value", {"entity_id": "number.b3_0_l600pro_71_4_uv", "value": 60}, blocking=True)
    assert hass.states.get("sensor.b3_0_l600pro_71_power").state == "94.6"   # live
    flow = await open_edit()
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {"preset": "Chat GPT", "how": "save_light"})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["presets"]["Chat GPT"] == {"levels": [120, 235, 120, 141], "fan": 40}
    assert await hass.config_entries.async_unload(entry.entry_id)
