"""The dashboard card in dashboard/weekaqua-card.yaml must match the integration."""

from datetime import datetime
from pathlib import Path
import re

from bleak.exc import BleakError
import pytest
import yaml
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.weekaqua.const import DOMAIN
from .test_weekaqua import ADDR, client, let_loop_run, sent  # noqa: F401

CARD = Path(__file__).parent.parent / "dashboard" / "weekaqua-card.yaml"


def _card():
    return yaml.safe_load(CARD.read_text())


def _entities(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "entity" and isinstance(value, str):
                yield value
            else:
                yield from _entities(value)
    elif isinstance(node, list):
        for item in node:
            yield from _entities(item)


def _markdown(card):
    return next(c["content"] for c in card["cards"] if c["type"] == "markdown")


def _links(card):
    return [c["content"] for c in card["cards"] if c["type"] == "markdown"][-1]


async def _setup(hass, freezer):
    tz = dt_util.get_default_time_zone()
    every = [0, 1, 2, 3, 4, 5, 6]
    freezer.move_to(datetime(2026, 10, 16, 12, 0, 0, tzinfo=tz))
    hass.states.async_set("switch.co2_plug", "on")            # on since 12:00
    freezer.move_to(datetime(2026, 10, 16, 16, 0, 0, tzinfo=tz))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="B3.0-L600pro-71",
        data={CONF_ADDRESS: ADDR, CONF_NAME: "B3.0-L600pro-71"},
        options={
            "schedule": [{"time": "14:00", "target": "Nature", "brightness": 100, "fade": 0, "days": every},
                         {"time": "21:00", "target": "__off__", "brightness": 100, "fade": 60, "days": every}],
            "co2": {"enabled": True, "entity_id": "switch.co2_plug", "lead": 60, "fallback": 50,
                    "control": True, "on_before": 60, "off_before": 60, "max_hours": 9},
        })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_card_entities_exist(hass, client, freezer):
    entry = await _setup(hass, freezer)
    missing = [e for e in _entities(_card()) if hass.states.get(e) is None]
    assert not missing, f"card uses entities that don't exist: {missing}"
    # Every entity the Today summary reads exists too
    prefix = "b3_0_l600pro_71"
    used = set(re.findall(r"'(\w+)\.' ~ p ~ '(_\w+)'", _markdown(_card())))
    missing = [f"{d}.{prefix}{s}" for d, s in used if hass.states.get(f"{d}.{prefix}{s}") is None]
    assert not missing, f"summary reads entities that don't exist: {missing}"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_summary_normal_day(hass, client, freezer):
    entry = await _setup(hass, freezer)
    await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Nature"}, blocking=True)
    text = Template(_markdown(_card()), hass).async_render(parse_result=False)
    print(text)
    assert "<ha-alert" not in text                                     # nothing wrong
    assert "**Now:** 14:00 · On · Nature 100% · every day" in text
    assert "**Channels** (current step): R 51% G 100% B 51% UV 0% · power 88%" in text
    assert "**Next at 20:00:** 21:00 · Off · fade 60 min from 20:00 · every day · also 20:00 · CO₂ off" in text
    assert "**Day:** 13:00 · CO₂ on | 14:00 · On · Nature | 20:00 · CO₂ off | 21:00 · Off" in text
    assert "**CO₂:** 13:00–20:00 (7 h)" in text
    # Natural sunset: the last minutes round to dark, so light ends just before 21:00
    assert "full-power hours today" in text and "light 14:00–20:5" in text
    assert "Acclimation" not in text
    assert not any(line.startswith("    ") for line in text.splitlines())   # nothing renders as code
    assert text.count("\n\n") >= 3                                       # separate paragraphs
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_summary_when_things_go_wrong(hass, client, freezer):
    entry = await _setup(hass, freezer)
    await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "Nature"}, blocking=True)
    await entry.runtime_data.acclimation.async_start()
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.b3_0_l600pro_71_maintenance_mode"}, blocking=True)
    hass.states.async_set("switch.co2_plug", "off"); await let_loop_run()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.write_gatt_char.side_effect = BleakError("busy")
    with pytest.raises(Exception):
        await hass.services.async_call("select", "select_option", {"entity_id": "select.b3_0_l600pro_71_preset", "option": "White"}, blocking=True)
    await hass.async_block_till_done()
    text = Template(_markdown(_card()), hass).async_render(parse_result=False)
    print(text)
    assert '<ha-alert alert-type="error">The light can\'t be reached' in text
    assert '<ha-alert alert-type="warning">CO₂ isn\'t ready (CO₂ is off (since 16:00))' in text
    assert '<ha-alert alert-type="info">Maintenance mode until 17:00' in text
    assert "**Acclimation:** 60% · 2 h shorter · next step 23 Oct · normal from 13 Nov" in text
    client.write_gatt_char.side_effect = None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_links(hass, client, freezer):
    from homeassistant.helpers import device_registry as dr
    entry = await _setup(hass, freezer)
    text = Template(_links(_card()), hass).async_render(parse_result=False)
    print(text)
    device = dr.async_get(hass).async_get_device(connections={(dr.CONNECTION_BLUETOOTH, ADDR)})
    assert "[Settings (Configure)](/config/integrations/integration/weekaqua)" in text
    assert f"[Device page](/config/devices/device/{device.id})" in text
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_chart_card(hass, client, freezer):
    entry = await _setup(hass, freezer)
    chart = yaml.safe_load((CARD.parent / "weekaqua-chart.yaml").read_text())
    assert chart["type"] == "custom:apexcharts-card"
    for series in chart["series"]:
        assert hass.states.get(series["entity"]) is not None
        key = series["data_generator"].split("p.")[-1].split("]")[0]
        # each generator reads a key that the curve really has
        assert key in hass.states.get(series["entity"]).attributes["curve"][0], key
    assert await hass.config_entries.async_unload(entry.entry_id)
