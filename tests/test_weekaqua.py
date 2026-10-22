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


async def let_loop_run(times: int = 5) -> None:
    """Give the event loop real turns, so state-change events get delivered.

    The client fixture fakes asyncio.sleep (also used by block_till_done),
    which would otherwise never yield to the loop.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    for _ in range(times):
        fut = loop.create_future()
        loop.call_soon(fut.set_result, None)
        await fut


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
    assert flow["type"] is FlowResultType.MENU and flow["menu_options"] == ["presets", "schedule", "acclimation", "co2", "modes", "light_settings"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
    assert flow["menu_options"] == ["add_preset"]                  # no own presets yet
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
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
    assert flow["menu_options"] == ["add_preset", "edit_preset", "remove_preset"]
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
    # Wednesday: the weekend-only 12:00 step is skipped, next is the 21:00 Off,
    # whose 60-min sunset starts at 20:00 so the light is off at 21:00
    assert hass.states.get(nxt).attributes["step"] == "21:00 · Off · fade 60 min from 20:00 · every day"
    assert dt_util.as_local(dt_util.parse_datetime(hass.states.get(nxt).state)).strftime("%H:%M") == "20:00"

    # Schedule switched off: the 20:00 sunset start does nothing
    await hass.services.async_call("switch", "turn_off", {"entity_id": sw}, blocking=True)
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 14, 20, 0, 0, tzinfo=tz))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client) == []
    assert hass.states.get(nxt).state == "unknown"

    # Switched back on at 20:30: catches up, continuing the sunset (30 min left, off at 21:00)
    freezer.move_to(datetime(2026, 10, 14, 20, 30, 0, tzinfo=tz))
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
    assert flow["menu_options"] == ["presets", "schedule", "acclimation", "co2", "modes", "light_settings"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "schedule"})
    assert flow["menu_options"] == ["add_schedule"]
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
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "schedule"})
    assert flow["menu_options"] == ["add_schedule", "remove_schedule"]
    assert "09:30 · On · Fresh 60%" in flow["description_placeholders"]["steps"]
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "remove_schedule"})
    await hass.config_entries.options.async_configure(flow["flow_id"], {"remove": ["09:30"]})
    await hass.async_block_till_done()
    assert entry.options["schedule"] == []

    # Number input style
    assert hass.states.get("number.b3_0_l600pro_71_1_r").attributes["mode"] == "slider"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "light_settings"})
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
            flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "light_settings"})
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
        flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "schedule"})
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
    assert st[1] == "09:00 · Off · fade 45 min from 08:15 · every day"

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
    assert cur.state == "21:00 · Off · fade 60 min from 20:00 · every day"

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

    # App preset Gorgeous (101.8 %) is scaled slightly to stay within 100 %, and still recognised
    await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Gorgeous"}, blocking=True)
    assert sent(client)[-1] == "FBF9BD5CB8E65555"
    assert float(hass.states.get(power).state) <= 100
    assert hass.states.get("select.b3_0_l600pro_71_preset").state == "Gorgeous"
    # ...and lowering a channel from there is allowed
    await call("number", "set_value", {"entity_id": b, "value": 70}, blocking=True)

    # A single slider that would push past 100 % is refused, like the app
    await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Colorful"}, blocking=True)
    client.write_gatt_char.reset_mock()
    with pytest.raises(Exception, match="Total power would be 1"):
        await call("number", "set_value", {"entity_id": g, "value": 100}, blocking=True)
    assert sent(client) == []

    # Custom preset over 100 % can't be saved
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
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
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "light_settings"})
    assert flow["menu_options"] == ["fade", "power", "display"]
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
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
    assert flow["menu_options"] == ["add_preset", "edit_preset", "remove_preset"]
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
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_preset"})
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"name": "Night", "red": 0, "green": 0, "blue": 20, "uv": 10})
    assert bad["errors"] == {"name": "name_exists"}

    # Remove list shows values too
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
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
    # Every step sensor shows what actually happens, not the normal schedule
    assert hass.states.get("sensor.b3_0_l600pro_71_current_step").state == "15:00 · On · Nature 70% (acclimation, normally 100%) · every day"
    assert hass.states.get("sensor.b3_0_l600pro_71_all_steps").state == "15:00 · On · Nature 70% | 19:30 · Off (acclimation)"
    assert hass.states.get("sensor.b3_0_l600pro_71_all_steps").attributes["step_2"] == "19:30 (acclimation, normally 21:00) · Off · every day"
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
    assert hass.states.get("sensor.b3_0_l600pro_71_all_steps").state == "15:00 · On · Nature | 21:00 · Off"
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
        flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "presets"})
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


async def test_off_time_is_end_and_acclimation_channels(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 60, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 17, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "acclimation": {"start_brightness": 70, "brightness_step": 10, "interval_days": 7, "shorten": 60, "shorten_step": 30}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sched = entry.runtime_data.scheduler

    # Normal schedule: Off at 21:00 means the sunset runs 20:00-21:00
    assert sched.run_time(steps[1]).strftime("%H:%M") == "20:00" and sched.run_fade(steps[1]) == 60

    await entry.runtime_data.acclimation.async_start()
    await hass.async_block_till_done()
    # Acclimation 1 h shorter: off at 20:00, sunset from 19:00
    assert sched.effective_time(steps[1]).strftime("%H:%M") == "20:00"
    assert sched.run_time(steps[1]).strftime("%H:%M") == "19:00"
    nxt = hass.states.get("sensor.b3_0_l600pro_71_next_step")
    assert nxt.attributes["step"] == "20:00 (acclimation, normally 21:00) · Off · fade 60 min from 19:00 · every day"
    assert dt_util.as_local(dt_util.parse_datetime(nxt.state)).strftime("%H:%M") == "19:00"

    # The actual channel values of the current iteration
    cur = hass.states.get("sensor.b3_0_l600pro_71_current_step")
    print(cur.attributes)
    assert cur.attributes["channels"] == "R 35% G 70% B 35% UV 0% · power 61%"
    acc = hass.states.get("sensor.b3_0_l600pro_71_acclimation")
    assert acc.attributes["on_steps"] == {"15:00 Nature 70%": "R 35% G 70% B 35% UV 0% · power 61%"}

    # An Off step whose sunset would overlap the sunrise is shortened, still ending on time
    overlap = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 60, "days": every},
               {"time": "16:30", "target": "__off__", "brightness": 100, "fade": 60, "days": every}]
    await entry.runtime_data.acclimation.async_stop()
    sched.steps = overlap
    assert sched.run_window(overlap[1]) == (16 * 60, 30)       # starts after the sunrise ends, 30 min
    assert sched.describe(overlap[1]) == "16:30 · Off · fade 30 min from 16:00 · every day"

    # The form refuses an Off fade that would start before midnight
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "schedule"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_schedule"})
    bad = await hass.config_entries.options.async_configure(flow["flow_id"],
        {"time": "00:30:00", "target": "__off__", "brightness": 100, "fade": 60, "curve": "default", "smoothness": "default", "days": [str(i) for i in every]})
    assert bad["errors"] == {"fade": "fade_before_midnight"}
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_connection_diagnostics_and_repairs(hass, client, freezer):
    from datetime import datetime, timedelta
    from bleak.exc import BleakError
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.util import dt as dt_util
    from custom_components.weekaqua.diagnostics import async_get_config_entry_diagnostics

    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 16, 12, 0, 0, tzinfo=tz))
    entry = await setup(hass)
    conn, last = "binary_sensor.b3_0_l600pro_71_connection", "sensor.b3_0_l600pro_71_last_command"
    assert hass.states.get(conn).state == "unknown"             # nothing sent yet
    await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Nature"}, blocking=True)
    assert hass.states.get(conn).state == "on"
    assert hass.states.get(last).state.startswith("2026-10-16T")

    # The light becomes unreachable: off at once, Repairs notice after 3 failures over 10 min
    client.write_gatt_char.side_effect = BleakError("busy")
    for minutes in (0, 5, 11):
        freezer.move_to(datetime(2026, 10, 16, 12, minutes, 30, tzinfo=tz))
        with pytest.raises(Exception):
            await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "White"}, blocking=True)
        if minutes == 5:
            assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_{ADDR}") is None
    assert hass.states.get(conn).state == "off"
    assert hass.states.get(conn).attributes["failed_in_a_row"] == 3
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_{ADDR}")
    assert issue is not None and issue.translation_key == "light_unreachable"

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["address"] == "**REDACTED**"
    assert diag["connection"]["failed_in_a_row"] == 3 and "busy" in diag["connection"]["last_error"]
    assert diag["light"]["levels"] == [0x77, 0xEB, 0x77, 0]

    # Back in range: notice disappears by itself
    client.write_gatt_char.side_effect = None
    await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "White"}, blocking=True)
    assert hass.states.get(conn).state == "on"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_{ADDR}") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_maintenance_mode(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "16:00", "target": "Fresh", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 15, 30, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "modes": {"maintenance": {"preset": "White", "minutes": 45}, "photo": {"preset": "Colorful", "minutes": 30}}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sw = "switch.b3_0_l600pro_71_maintenance_mode"

    client.write_gatt_char.reset_mock()
    await hass.services.async_call("switch", "turn_on", {"entity_id": sw}, blocking=True)
    assert sent(client)[-1] == "FBF97EEB69005555"                       # White
    st = hass.states.get(sw)
    assert st.state == "on" and st.attributes["ends_at"].startswith("2026-10-16T16:15")

    # The 16:00 step is skipped while maintenance mode is on
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 16, 16, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client) == []

    # At 16:15 it ends by itself and fades back to where the schedule is (16:00 Fresh)
    freezer.move_to(datetime(2026, 10, 16, 16, 15, 1, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(sw).state == "off"
    assert sent(client)[-1] == "FBF959EB60005555"                       # Fresh
    assert len(sent(client)) > 1                                        # faded, not jumped

    # Photo mode can be ended early
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.b3_0_l600pro_71_photo_mode"}, blocking=True)
    assert sent(client)[-1] == "FBF9EB5E94EB5555"                       # Colorful
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.b3_0_l600pro_71_photo_mode"}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client)[-1] == "FBF959EB60005555"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_co2_interlock(hass, client, freezer, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="custom_components.weekaqua")
    """CO₂ plug off at the On step -> fallback; on for the lead time -> full; off during the day -> fallback."""
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 14, 50, 0, tzinfo=tz))
    hass.states.async_set("switch.co2_plug", "off")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "co2": {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ready = "binary_sensor.b3_0_l600pro_71_co2_ready"
    assert hass.states.get(ready).state == "off"
    assert hass.states.get(ready).attributes["reason"].startswith("CO₂ is off")

    # 15:00 On step while CO₂ is off: Nature at 50 % (77 EB 77 * 0.5 = 3C 76 3C), notification
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 16, 15, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client)[-1] == "FBF93C763C005555"
    cur = hass.states.get("sensor.b3_0_l600pro_71_current_step")
    assert cur.state == "15:00 · On · Nature 50% (CO₂ not ready, normally 100%) · every day"
    assert "to preset 'Nature' at 50% (CO₂ not ready: CO₂ is off (since 14:50), fallback 50%; normally 100%)" in caplog.text

    # CO₂ switched on at 15:10: not ready yet (60 min lead), light stays at 50 %
    freezer.move_to(datetime(2026, 10, 16, 15, 10, 0, tzinfo=tz))
    client.write_gatt_char.reset_mock()
    hass.states.async_set("switch.co2_plug", "on")
    await let_loop_run()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client) == []
    assert hass.states.get(ready).attributes["ready_at"].startswith("2026-10-16T16:10")

    # 16:10: ready -> back to full over 5 minutes
    freezer.move_to(datetime(2026, 10, 16, 16, 10, 1, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ready).state == "on"
    assert sent(client)[-1] == "FBF977EB77005555" and len(sent(client)) > 1

    # 18:00 CO₂ plug goes unavailable: light lowers to 50 % again
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 16, 18, 0, 0, tzinfo=tz))
    hass.states.async_set("switch.co2_plug", "unavailable")
    await let_loop_run()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client)[-1] == "FBF93C763C005555"
    assert hass.states.get(ready).attributes["reason"] == "the CO₂ plug is unavailable"

    # Off steps are never affected
    client.write_gatt_char.reset_mock()
    freezer.move_to(datetime(2026, 10, 16, 21, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sent(client)[-1] == "FBF9000000005555"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_co2_on_at_restart_counts_as_ready(hass, client, freezer):
    """After an HA restart every entity looks freshly changed; a plug already on must not dim the light for an hour."""
    from datetime import datetime
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 17, 0, 0, tzinfo=tz))
    hass.set_state(CoreState.not_running)
    hass.states.async_set("switch.co2_plug", "on")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "co2": {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("binary_sensor.b3_0_l600pro_71_co2_ready").state == "on"
    assert sent(client)[-1] == "FBF977EB77005555"                   # full Nature, not 50 %
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_acclimation_step_back_and_plan(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "15:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 1, 10, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "acclimation": {"start_brightness": 60, "brightness_step": 10, "interval_days": 7, "shorten": 120, "shorten_step": 30}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    acc = entry.runtime_data.acclimation
    await acc.async_start()
    freezer.move_to(datetime(2026, 10, 16, 10, 0, 0, tzinfo=tz))          # day 15: stage 3 (80 %)
    await acc.async_check()
    assert acc.summary() == "80% · 1 h shorter"

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "acclimation"})
    lines = flow["description_placeholders"]["plan_lines"]
    print(lines)
    assert "15 Oct: 80% · 1 h shorter ← now" in lines and "29 Oct: normal schedule" in lines
    values = {k: acc.settings[k] for k in ("start_brightness", "brightness_step", "interval_days", "shorten", "shorten_step")}
    await hass.config_entries.options.async_configure(flow["flow_id"], {**values, "action": "back"})
    await hass.async_block_till_done(wait_background_tasks=True)
    acc = entry.runtime_data.acclimation          # reloaded
    assert acc.summary() == "70% · 1 h 30 min shorter"
    assert acc.next_change().isoformat() == "2026-10-23"                 # a full week at 70 % from today
    assert acc.ends().isoformat() == "2026-11-06"
    assert await hass.config_entries.async_unload(entry.entry_id)


def _co2_entry(hass, extra=None, schedule=None):
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = schedule or [
        {"time": "15:00", "target": "Nature", "brightness": 100, "fade": 60, "days": every},
        {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": every},
    ]
    co2 = {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50,
           "control": True, "on_before": 60, "off_before": 60, "max_hours": 10, **(extra or {})}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
                            data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
                            options={"schedule": steps, "co2": co2})
    entry.add_to_hass(hass)
    return entry


async def test_co2_control_day(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

    tz = dt_util.get_default_time_zone()
    on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    off_calls = async_mock_service(hass, "homeassistant", "turn_off")
    freezer.move_to(datetime(2026, 10, 16, 12, 0, 0, tzinfo=tz))
    hass.states.async_set("switch.co2_plug", "off")
    entry = _co2_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensor = "sensor.b3_0_l600pro_71_co2_schedule"
    # CO₂ 60 min before the 15:00 On step, off 60 min before the light is fully off at 21:00
    assert hass.states.get(sensor).state == "14:00–20:00 (6 h)"
    # CO₂ switches are part of the timeline, and the next thing to happen is CO₂ on at 14:00
    assert hass.states.get("sensor.b3_0_l600pro_71_all_steps").state == "14:00 · CO₂ on | 15:00 · On · Nature | 20:00 · CO₂ off | 21:00 · Off"
    nxt = hass.states.get("sensor.b3_0_l600pro_71_next_step")
    assert nxt.attributes["step"] == "14:00 · CO₂ on (60 min before the first On step)"
    assert nxt.attributes["kind"] == "co2_on" and nxt.attributes["icon"] == "mdi:molecule-co2"
    assert dt_util.as_local(dt_util.parse_datetime(nxt.state)).strftime("%H:%M") == "14:00"

    async def at(h, m):
        freezer.move_to(datetime(2026, 10, 16, h, m, 0, tzinfo=tz))
        async_fire_time_changed(hass)
        await let_loop_run()
        await hass.async_block_till_done(wait_background_tasks=True)

    await at(13, 59); assert len(on_calls) == 0
    await at(14, 0);  assert len(on_calls) == 1 and on_calls[0].data["entity_id"] == "switch.co2_plug"
    hass.states.async_set("switch.co2_plug", "on"); await let_loop_run()
    await hass.async_block_till_done()
    # After CO₂ on, the next thing is the 15:00 sunrise
    assert hass.states.get("sensor.b3_0_l600pro_71_next_step").attributes["step"].startswith("15:00 · On · Nature")
    # Interlock: CO₂ on since 14:00 -> ready at 15:00, so the 15:00 sunrise goes to full Nature
    await at(15, 0)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("binary_sensor.b3_0_l600pro_71_co2_ready").state == "on"
    assert sent(client)[-1] == "FBF977EB77005555"
    # The sunset starts at 20:00, the same minute CO₂ goes off: both are shown
    nxt = hass.states.get("sensor.b3_0_l600pro_71_next_step").attributes
    assert nxt["step"] == "21:00 · Off · fade 60 min from 20:00 · every day" and nxt["also"] == "20:00 · CO₂ off"
    await at(19, 59); assert len(off_calls) == 0
    await at(20, 0);  assert len(off_calls) == 1
    hass.states.async_set("switch.co2_plug", "off"); await let_loop_run()

    # Someone turns CO₂ on at night: switched off within a minute, with a warning
    hass.states.async_set("switch.co2_plug", "on"); await let_loop_run()
    await at(23, 0)
    assert len(off_calls) == 2
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_co2_control_limits(hass, client, freezer):
    from datetime import datetime
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

    tz = dt_util.get_default_time_zone()
    on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    off_calls = async_mock_service(hass, "homeassistant", "turn_off")

    # HA starts at 16:00 with CO₂ off (it was down at 14:00): catch up, CO₂ on
    freezer.move_to(datetime(2026, 10, 16, 16, 0, 0, tzinfo=tz))
    hass.set_state(CoreState.not_running)
    hass.states.async_set("switch.co2_plug", "off")
    entry = _co2_entry(hass, {"max_hours": 4})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    # The 4 h maximum shortens the window: 16:00-20:00
    assert hass.states.get("sensor.b3_0_l600pro_71_co2_schedule").state == "16:00–20:00 (shortened to the 4 h maximum) (4 h)"
    assert len(on_calls) == 1
    hass.states.async_set("switch.co2_plug", "on"); await let_loop_run()

    # Schedule switched off: CO₂ off too
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.b3_0_l600pro_71_schedule"}, blocking=True)
    assert len(off_calls) == 1
    assert hass.states.get("sensor.b3_0_l600pro_71_co2_schedule").state == "Off today (the schedule is switched off)"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_co2_control_form_safety(hass, client):
    entry = await setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "co2"})
    base = {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50,
            "control": True, "on_before": 60, "off_before": 60, "max_hours": 9}
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {**base, "backstop": False})
    assert res["errors"] == {"backstop": "co2_backstop_required"}
    res = await hass.config_entries.options.async_configure(res["flow_id"], {**base, "entity_id": "binary_sensor.co2", "backstop": True})
    assert res["errors"] == {"entity_id": "co2_not_switchable"}
    res = await hass.config_entries.options.async_configure(res["flow_id"], {**base, "backstop": True})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["co2"]["control"] is True and entry.options["co2"]["max_hours"] == 9
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_step_channels_sensor(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "14:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 23, 0, 0, tzinfo=tz))           # night
    hass.states.async_set("switch.co2_plug", "off")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps,
                 "acclimation": {"start_brightness": 60, "brightness_step": 10, "interval_days": 7, "shorten": 60, "shorten_step": 30},
                 "co2": {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.acclimation.async_start()
    await hass.async_block_till_done()
    ch = "sensor.b3_0_l600pro_71_step_channels"

    # Night: tomorrow's 14:00 step at 60 % (Nature 77 EB 77 00 -> 47 8D 47 00), CO₂ fallback not counted
    st = hass.states.get(ch)
    print(st.state, st.attributes)
    assert st.state == "R 30% G 60% B 30% UV 0%"
    assert st.attributes["applies"] == "next On step" and st.attributes["step"] == "14:00 · Nature"
    assert st.attributes["brightness"] == "60% (acclimation 60% of 100%)"
    assert st.attributes["levels"] == {"R": 71, "G": 141, "B": 71, "UV": 0}
    assert "co2_note" in st.attributes

    # 14:00 with CO₂ still off: the current step at 60 % x 50 % fallback = 30 %
    freezer.move_to(datetime(2026, 10, 17, 14, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    st = hass.states.get(ch)
    assert st.attributes["applies"] == "current step"
    assert st.attributes["brightness"] == "30% (acclimation 60%, CO₂ fallback 50% of 100%)"
    assert st.attributes["levels"] == {"R": 36, "G": 70, "B": 36, "UV": 0}
    assert sent(client)[-1] == "FBF9244624005555"                          # what the light got
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_resend_and_attempt_diagnostics(hass, client):
    from bleak.exc import BleakError
    from custom_components.weekaqua.device import describe_command
    from custom_components.weekaqua.const import clock_cmd, fan_cmd, levels_cmd, CMD_SIMPLE_SCHEDULE

    # Commands in words
    assert describe_command(levels_cmd((120, 235, 120, 70))) == "R 51% G 100% B 51% UV 30%"
    assert describe_command(fan_cmd(40)) == "fan 40%"
    assert describe_command(clock_cmd(14, 30, 5)) == "clock 14:30:05"
    assert describe_command(CMD_SIMPLE_SCHEDULE) == "light's own simple schedule"

    entry = await setup(hass)
    call = hass.services.async_call
    last = "sensor.b3_0_l600pro_71_last_command"
    await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Nature"}, blocking=True)
    await call("number", "set_value", {"entity_id": "number.b3_0_l600pro_71_5_fan", "value": 40}, blocking=True)
    a = hass.states.get(last).attributes
    assert a["last_attempt_command"] == "fan 40%" and a["last_attempt_result"] == "delivered"
    assert a["delivered_since_start"] == 2 and a["failed_since_start"] == 0 and a["retries_since_start"] == 0

    # Re-send: fan, then channels, exactly what HA believes; nothing else changes
    client.write_gatt_char.reset_mock()
    await call("button", "press", {"entity_id": "button.b3_0_l600pro_71_re_send_current_state"}, blocking=True)
    assert sent(client) == ["FC5E555555555555", "FBF977EB77005555"]
    assert hass.states.get(last).attributes["last_attempt_command"] == "fan 40% + R 51% G 100% B 51% UV 0%"
    assert hass.states.get("select.b3_0_l600pro_71_preset").state == "Nature"

    # A write that fails once and succeeds on the retry: delivered, 1 retry
    fails = {"n": 1}
    async def flaky(*args, **kwargs):
        if fails["n"]:
            fails["n"] -= 1
            raise BleakError("busy")
    client.write_gatt_char.side_effect = flaky
    await call("button", "press", {"entity_id": "button.b3_0_l600pro_71_re_send_current_state"}, blocking=True)
    a = hass.states.get(last).attributes
    assert a["last_attempt_result"] == "delivered" and a["retries_since_start"] == 1

    # A command that doesn't get through at all
    client.write_gatt_char.side_effect = BleakError("out of range")
    with pytest.raises(Exception):
        await call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "White"}, blocking=True)
    a = hass.states.get(last).attributes
    assert a["last_attempt_command"] == "R 54% G 100% B 45% UV 0%"
    assert a["last_attempt_result"].startswith("failed:") and "out of range" in a["last_attempt_result"]
    assert a["failed_since_start"] == 1 and a["delivered_since_start"] == 4
    client.write_gatt_char.side_effect = None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_acclimation_uv_holdback(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "14:00", "target": "Colorful", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 1, 15, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "acclimation": {"start_brightness": 60, "brightness_step": 20, "interval_days": 7,
                                                    "shorten": 0, "shorten_step": 0, "uv_holdback": True}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    acc, sched = entry.runtime_data.acclimation, entry.runtime_data.scheduler
    await acc.async_start()
    await hass.async_block_till_done()

    # Colorful = EB 5E 94 EB. At 60 %: R/G/B x 0.6, UV x 0.36 (0.6 squared)
    assert acc.summary() == "60% (UV 36%)"
    assert sched.step_levels(steps[0]) == (141, 56, 89, 85)
    client.write_gatt_char.reset_mock()
    await sched._run(sched.steps[0], 0)
    assert bytes.fromhex(sent(client)[-1])[2:6] == bytes([141, 56, 89, 85])
    st = hass.states.get("sensor.b3_0_l600pro_71_step_channels")
    assert st.attributes["brightness"] == "60% (acclimation 60%, UV held back to 36% of 100%)"
    assert hass.states.get("sensor.b3_0_l600pro_71_current_step").state == "14:00 · On · Colorful 60% (acclimation, UV 36%, normally 100%) · every day"

    # The plan shows UV per stage, and the last stage is the normal schedule (UV 100 % too)
    lines = acc.plan()
    assert lines[0].startswith("01 Oct: 60% (UV 36%)") and lines[1].startswith("08 Oct: 80% (UV 64%)")
    assert lines[-1] == "15 Oct: normal schedule"
    freezer.move_to(datetime(2026, 10, 15, 15, 0, 0, tzinfo=tz))
    await acc.async_check()
    assert acc.summary() == "Finished"
    assert sched.step_levels(steps[0]) == (0xEB, 0x5E, 0x94, 0xEB)
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_no_lambdas_as_timer_callbacks():
    """A plain lambda passed to HA's event/timer helpers runs in a thread: twice a real bug here."""
    import pathlib, re
    root = pathlib.Path(__file__).parent.parent / "custom_components" / "weekaqua"
    bad = []
    for path in root.glob("*.py"):
        text = path.read_text()
        for m in re.finditer(r"(async_track_\w+|async_at_started|async_call_later)\([^\n]*lambda", text):
            bad.append(f"{path.name}: {m.group(0)}")
    assert not bad, bad


async def test_light_plan_and_light_today(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "14:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": every, "curve": "linear"}]
    freezer.move_to(datetime(2026, 10, 16, 10, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"}, options={"schedule": steps})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Plan: Nature (87.6 % power) 14:00-20:00, then a linear 1 h sunset to off at 21:00
    plan = hass.states.get("sensor.b3_0_l600pro_71_light_plan")
    print(plan.state, {k: v for k, v in plan.attributes.items() if k != "curve"})
    assert abs(float(plan.state) - (6 * 0.876 + 0.876 / 2)) < 0.03
    assert plan.attributes["light_from"] == "14:00" and plan.attributes["light_until"] == "21:00"
    assert plan.attributes["light_hours"] == 7.0 and plan.attributes["peak_power"] == 87.6
    curve = {p["t"]: p for p in plan.attributes["curve"]}
    assert curve["13:55"]["power"] == 0 and curve["15:00"]["power"] == 87.6
    assert curve["15:00"]["g"] == 100.0 and curve["15:00"]["r"] == 50.6
    assert 40 < curve["20:30"]["power"] < 47                       # halfway through the sunset
    assert len(plan.attributes["curve"]) == 289

    # Light today: 2 h of Nature = 1.75 full-power hours
    freezer.move_to(datetime(2026, 10, 16, 14, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.move_to(datetime(2026, 10, 16, 16, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done()
    today = hass.states.get("sensor.b3_0_l600pro_71_light_today")
    assert abs(float(today.state) - 2 * 0.876) < 0.01
    assert abs(today.attributes["planned_until_now"] - 2 * 0.876) < 0.02   # on plan

    # Survives a reload (e.g. saving a preset)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime(2026, 10, 16, 17, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert abs(float(hass.states.get("sensor.b3_0_l600pro_71_light_today").state) - 3 * 0.876) < 0.01

    # New day: starts from 0 again
    await hass.services.async_call("light", "turn_off", {"entity_id": "light.b3_0_l600pro_71"}, blocking=True)
    freezer.move_to(datetime(2026, 10, 17, 9, 0, 0, tzinfo=tz)); async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.b3_0_l600pro_71_light_today").state) == 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_light_plan_with_acclimation(hass, client, freezer):
    from datetime import datetime
    from homeassistant.util import dt as dt_util

    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    steps = [{"time": "14:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
             {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 0, "days": every}]
    freezer.move_to(datetime(2026, 10, 16, 10, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={"schedule": steps, "acclimation": {"start_brightness": 60, "brightness_step": 10, "interval_days": 7, "shorten": 60, "shorten_step": 30}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    plan = "sensor.b3_0_l600pro_71_light_plan"
    normal = float(hass.states.get(plan).state)
    await entry.runtime_data.acclimation.async_start()
    await hass.async_block_till_done()
    st = hass.states.get(plan)
    # 6 h (off 1 h earlier) at 60 %: about 6/7 x 0.6 of the normal amount
    assert st.attributes["light_until"] == "20:00"
    assert abs(float(st.state) - normal * 6 / 7 * 0.6) < 0.05
    assert await hass.config_entries.async_unload(entry.entry_id)
