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
- The **Power** sensor shows the current total power.
- **Configure → Light settings → Power limit** can turn it off. Only do this if you know your light can handle it.

## Your own presets

Under **Settings → Devices & services → Week Aqua → Configure → Presets**:

- **Add a preset**: the values start at what the light shows now, so the easiest way is to set the light up on the device page first, then save it with a name. Leave *Fan* empty if the preset shouldn't change the fan.
- **Edit a preset**: pick a preset (the list shows its channels, fan and total power), then either change its values or name in the form (schedule steps follow a renamed preset; tick **Show on the light now** to see the result), or **load it onto the light**, adjust it live on the device page while the **Power** sensor shows the total, and **save what the light shows** back into the preset.
- The forms show how far each channel can go up before the power limit. If you go over it anyway, you can scale all channels down to 100 % or go back.
- **Remove presets**: pick the ones to delete.

Your presets appear at the top of the **Preset** picker (most recently used first) and as light effects (`effect: My Reef`), including with `transition`.

## Built-in schedule

Under **Configure → Schedule → Add or update a step**, choose a time, a preset (or *Off*), a brightness, a fade duration and the days. **On** steps start fading in at their time; **Off** steps are fully off at their time, with the fade starting earlier, so the light period runs from the On time to the Off time. Each step can also use its own fade curve and smoothness instead of the general fade settings. Saving a step at an existing time replaces it. Example photoperiod:

| Time | Preset | Fade | Days |
|---|---|---|---|
| 08:00 | Nature 80 % | 45 min | every day |
| 13:00 | White 100 % | 30 min | every day |
| 21:00 | Off | 60 min | every day |

- Sensors **All steps**, **Current step** and **Next step** show the schedule on the device page, including the actual channel values of On steps (`channels` attribute). The **Step channels** sensor shows those values directly: the current On step's channels (or the next one's at night), with acclimation, the CO₂ fallback and the power limit applied. The step sensors' icons show what a step does: sunrise (on after off), palette (color change while on) or sunset (off).
- With `info` logging (see Troubleshooting), every step logs what it does: preset and channel values, fan, fade duration, curve, smoothness, number of steps and the time between them.
- The **Schedule** switch pauses it. Turning it back on puts the light where the schedule should be right now (continuing a fade in progress).
- After a Home Assistant restart the light is also brought back in line with the schedule.
- Manual changes stay until the next step runs.
- If the light can't be reached when a step runs (e.g. the phone app is connected), the step is retried every 30 s for up to 10 minutes. Every step is written to the log.
- For steps tied to the real sunrise/sunset, use automations (below).

To let the integration (not the light) control timing, set the light's own schedule (app → *Mode* tab) to 00:00–23:59 with no ramp and press **Resume simple schedule** once.

## Acclimation

For a new tank, new plants or new livestock, **Configure → Acclimation** brings the light up slowly:

- **Brightness** starts at a share of your schedule's brightness (e.g. 60 %) and rises by a step (e.g. 10 %) at each interval (e.g. 7 days).
- **Light period** starts shorter (Off steps run e.g. 2 h earlier, never before the previous step's fade has ended) and gets longer by a step (e.g. 30 min) at each interval.
- **Configure → Acclimation** shows the plan date by date. **Go back one step** (e.g. if algae appear) repeats the previous stage for a full interval.
- It stops at your normal schedule and **finishes by itself**, so it can't run away if you forget about it.
- You get a **notification** at every step. The **Acclimation** sensor shows the current level, the next step and the end date. The **Acclimation** switch pauses it (the level is held and the days don't count) and resumes it.

## CO₂ interlock

For CO₂-injected tanks, **Configure → CO₂** keeps the plants from getting full light without CO₂. Choose the entity that switches your CO₂ (e.g. the solenoid's smart plug), a **lead time** and a **fallback brightness**:

- If CO₂ hasn't been on for the lead time when an On step runs, or turns off or becomes unavailable while the light is on, the light is held at the fallback brightness (a share of the step's brightness) and you get a notification.
- When CO₂ has been on for the lead time, the light comes back up by itself over a few minutes.
- The **CO₂ ready** sensor shows whether CO₂ is ready, and why not.

The interlock only checks that the plug is on, not how much CO₂ is in the water (use a drop checker for that) and only ever lowers the light.

### CO₂ control (optional)

The same screen can also **switch the CO₂ plug** from the light schedule: on a set time before the day's first On step, off a set time before the last Off step (the time the light is fully off), never longer than a daily maximum. Every minute, CO₂ is switched off if it's on outside that window, e.g. at night, with the schedule switched off, or turned on by hand. The **CO₂ schedule** sensor shows today's window, and the CO₂ switches also appear in **All steps** and **Next step**.

⚠️ **CO₂ left on without light can kill fish**, and Home Assistant can only switch the plug while it's running. Before enabling CO₂ control, set a **backstop in the plug itself**, e.g. an off-only schedule in the plug's own app shortly after the CO₂ off time (Sonoff/eWeLink: *Schedule*), or auto-off. Also set the plug's power-on state to *Off*. CO₂ isn't switched off when Home Assistant restarts, so CO₂ doesn't drop out (and the interlock doesn't dim the light) after every restart.

## Maintenance and photo modes

The **Maintenance mode** and **Photo mode** switches show a preset for a set time, skipping schedule steps, then fade back to the schedule by themselves. Choose each mode's preset and duration under **Configure → Maintenance and photo modes**.

## Dashboard card

[`dashboard/weekaqua-card.yaml`](dashboard/weekaqua-card.yaml) is a ready-made card using only Home Assistant's standard cards: the light with brightness and preset, the preset picker, Schedule / Maintenance / Photo / Acclimation switches, a **Today** summary (warnings when the light can't be reached, CO₂ isn't ready or a mode is on; what's happening now, the actual channel values, what's next, the day's timeline with CO₂, acclimation progress), a power gauge with a 24-hour graph, and the channel sliders.

To add it: open your dashboard → ⋮ → **Edit dashboard** → **Add card** → **Manual**, and paste the file's contents. If your entity IDs don't start with `b3_0_l600pro_71`, replace that text everywhere in the card (find an ID under **Settings → Entities**).

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

The light can't fade on command, so the integration sends a series of small level changes. Under **Configure → Light settings → Fade smoothness and curve**:

- **Curve** – *Natural* (default) moves evenly in *perceived* brightness (gamma 2.2), so sunrises don't seem to jump up at the start and sunsets don't drop off at the end. *Linear* moves in equal steps of LED power.
- **Smoothness** – *Fine* sends a command for every level change (never more than ~0.4 % per step, at most twice a second). *Medium*, *Coarse* and *Very coarse* send at most one command every 10, 30 or 60 s.

During a fade, entity states are updated every 30 s and at the end (not every step), which keeps the recorder database small. Touching any slider, preset or the light during a fade stops it. If Home Assistant restarts mid-fade, the built-in schedule continues it after startup.

## Troubleshooting

The **Connection** and **Last command** sensors (Diagnostic section of the device page) show whether commands reach the light; the light can't confirm it applied them. If the light has been unreachable for 10 minutes, a notice appears under **Settings → Repairs** and disappears by itself once a command gets through. For bug reports, use **⋮ → Download diagnostics** on the integration.


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

Planned features and ideas: `BACKLOG.md`.


`CLAUDE.md` describes the protocol, the code layout and the design decisions. Tests: `python -m pip install -r requirements_test.txt`, then `python -m pytest` (Python 3.13; on Windows use WSL). Pushing a new `version` in `manifest.json` to `main` runs the tests and publishes the release automatically.
