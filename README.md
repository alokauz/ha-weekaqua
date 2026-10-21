# Week Aqua for Home Assistant

Control Week Aqua Bluetooth aquarium lights from Home Assistant, locally, using Home Assistant's own Bluetooth (a built-in adapter, a USB dongle, or an ESPHome Bluetooth proxy). No cloud, no ESP32 firmware to write.

Made by Flint. Not affiliated with or endorsed by Week Aqua.

## Supported lights

Lights that advertise **model code 5746** ("WEK" protocol) with a 4-channel R / G / B / UV spectrum and a fan. Tested with:

| Light | Bluetooth board | Status |
|---|---|---|
| L600 Pro | B3.0 (`B3.0-L600pro-…`) | Working |

Other Week Aqua lights use different protocols (model codes 5745 and 5747–5752) and are **not supported yet**. If you have one, please open an issue with your light's model and the Bluetooth name it advertises.

## Features

- **Light** with brightness and color. The "white" channel is the **UV** channel.
- **Smooth fades** (`transition`) of any length, for sunrise and sunset automations.
- The app's presets as light **effects**, so automations can fade straight into a preset.
- **A built-in schedule** set up under *Configure*: fade to a preset (or off) at set times on chosen days, with an on/off switch and a *Next step* sensor.
- **Slider or number input** for the channel and fan controls.
- **Your own presets** with a name, all four channels and optionally a fan speed. They appear in the Preset picker and as effects.
- **1. R, 2. G, 3. B, 4. UV** sliders (0–100 %) and **5. Fan**, in the device page's Configuration section.
- **Preset** picker with the app's 12 presets: Green, Red, Mixed, Gorgeous, Colorful, Algae, Nature, Elegant, Brisk, Fresh, Enjoy, White.
- **Resume simple schedule** / **Resume advanced schedule**: sync the light's clock and hand control back to the schedule stored on the light (the app's *Mode* or *Advanced* tab).
- **Sync clock** button.
- Automatic Bluetooth discovery.

## Installation

### HACS (recommended)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/alokauz/ha-weekaqua` with type **Integration**.
3. Search for **Week Aqua**, download it, and restart Home Assistant.

### Manual

Copy `custom_components/weekaqua` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

1. Close the WEEK AQUA phone app (the light accepts only one Bluetooth connection).
2. The light should appear under **Settings → Devices & services → Discovered**. If not, click **Add integration** and search for **Week Aqua**.

## Good to know

- The light can't report its state, so Home Assistant shows the last values *it* sent. Changes made by the light's own schedule or the phone app aren't visible.
- Setting a color or preset overrides the light's schedule until you press one of the **Resume** buttons.
- Home Assistant disconnects 30 seconds after the last command, so the phone app can still be used in between.

## Power limit

Like the app's *Total power* slider, the integration keeps the light's total power at or below 100 %. Each channel counts differently at full: R 39 %, G 41 %, B 53 %, UV 11 % — so all four at 100 % would be 144 %, which the light isn't designed for.

- Colors, presets, schedules and fades above 100 % are scaled down proportionally (same color, slightly dimmer); the log says when this happens.
- A single channel slider refuses a change that would exceed 100 %, like the app. Lowering is always allowed.
- Custom presets above 100 % can't be saved.
- The app's own presets are sent unchanged (*Gorgeous* is 101.8 %), as the app does.
- The **Power** sensor shows the current total power.
- **Configure → Power limit** can turn it off. Only do this if you know your light can handle it.

## Your own presets

Under **Settings → Devices & services → Week Aqua → Configure**:

- **Add a preset**: the values start at what the light shows now, so the easiest way is to set the light up on the device page first, then save it with a name. Leave *Fan* empty if the preset shouldn't change the fan.
- **Edit a preset**: pick a preset (the list shows its channels, fan and total power) and change its values or its name. Schedule steps follow a renamed preset. Tick **Show on the light now** to see the result when you save.
- **Remove presets**: pick the ones to delete.

Your presets appear at the top of the **Preset** picker (most recently used first) and as light effects (`effect: My Reef`), including with `transition`.

## Built-in schedule

Under **Configure → Add or update a schedule step**, choose a time, a preset (or *Off*), a brightness, a fade duration and the days. Each step can also use its own fade curve and smoothness instead of the general fade settings. Saving a step at an existing time replaces it. Example photoperiod:

| Time | Preset | Fade | Days |
|---|---|---|---|
| 08:00 | Nature 80 % | 45 min | every day |
| 13:00 | White 100 % | 30 min | every day |
| 21:00 | Off | 60 min | every day |

- Sensors **All steps**, **Current step** and **Next step** show the schedule on the device page. The step sensors' icons show what a step does: sunrise (on after off), palette (color change while on) or sunset (off).
- With `info` logging (see Troubleshooting), every step logs what it does: preset and channel values, fan, fade duration, curve, smoothness, number of steps and the time between them.
- The **Schedule** switch pauses it. Turning it back on puts the light where the schedule should be right now (continuing a fade in progress).
- After a Home Assistant restart the light is also brought back in line with the schedule.
- Manual changes stay until the next step runs.
- If the light can't be reached when a step runs (e.g. the phone app is connected), the step is retried every 30 s for up to 10 minutes. Every step is written to the log.
- For steps tied to the real sunrise/sunset, use automations (below).

To let the integration (not the light) control timing, set the light's own schedule (app → *Mode* tab) to 00:00–23:59 with no ramp and press **Resume simple schedule** once.

## Sunrise and sunset with automations

Automations give the most flexibility (e.g. following the real sun). Use them like this:

```yaml
automation:
  - alias: Aquarium sunrise
    triggers:
      - trigger: time
        at: "08:00:00"
    actions:
      - action: light.turn_on
        target:
          entity_id: light.b3_0_l600pro_71
        data:
          effect: Nature        # any preset, or use rgbw_color / brightness
          transition: 2700      # 45 minutes

  - alias: Aquarium sunset
    triggers:
      - trigger: time
        at: "21:00:00"
    actions:
      - action: light.turn_off
        target:
          entity_id: light.b3_0_l600pro_71
        data:
          transition: 3600      # 1 hour
```

### How fades work

The light can't fade on command, so the integration sends a series of small level changes. Under **Configure → Fade smoothness and curve**:

- **Curve** – *Natural* (default) moves evenly in *perceived* brightness (gamma 2.2), so sunrises don't seem to jump up at the start and sunsets don't drop off at the end. *Linear* moves in equal steps of LED power.
- **Smoothness** – *Fine* sends a command for every level change (never more than ~0.4 % per step, at most twice a second). *Medium*, *Coarse* and *Very coarse* send at most one command every 10, 30 or 60 s.

During a fade, entity states are updated every 30 s and at the end (not every step), which keeps the recorder database small. Touching any slider, preset or the light during a fade stops it. If Home Assistant restarts mid-fade, the built-in schedule continues it after startup.

## Troubleshooting

Enable debug logging and include the `weekaqua` log lines when opening an issue:

```yaml
logger:
  logs:
    custom_components.weekaqua: info   # or debug for even more detail
```

## Protocol

Commands are 8 bytes written to characteristic `FFF2` (service `FFF0`; older boards use `FFE1`), padded with `0x55`:

| Command | Bytes |
|---|---|
| Color | `FB F9 R G B UV 55 55` (each `00`–`EB`, `EB` = 100 %) |
| Fan | `FC XX 55 55 55 55 55 55` |
| Clock | `FF HH MM SS 55 55 55 55` (decimal digits written as hex) |
| Simple / advanced schedule | `FD F1 55…` / `FD F2 55…` |

## Icon

The integration ships its own icon (`custom_components/weekaqua/brand/`, Home Assistant 2026.3 or newer): an aquarium with the light bar on its rim, its four channels (red, green, blue, UV) shining into the water onto a plant. Source: `assets/icon.svg`. The HACS dashboard doesn't show icons of this kind yet (a HACS limitation); Home Assistant itself does.

## Development

`CLAUDE.md` describes the protocol, the code layout and the design decisions. Tests: `python -m pip install -r requirements_test.txt`, then `python -m pytest` (Python 3.13; on Windows use WSL). Pushing a new `version` in `manifest.json` to `main` runs the tests and publishes the release automatically.
