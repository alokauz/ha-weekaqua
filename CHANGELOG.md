# Changelog

Key changes in each version. Betas (e.g. 0.9.1b1) are pre-releases for testing.

## 0.10.0b3

- Preset forms show how far each channel can go up before reaching the power limit, e.g. "R up to 73%, G up to 100%, B up to 67%, UV up to 100%".
- Going over the power limit is no longer a dead end: you see the total (e.g. 114 %) and can **scale all channels down to 100 %** (same colour, slightly dimmer) or **go back** with your values kept.
- **Edit a preset** can **load the preset onto the light**, so you can adjust it live on the device page while the **Power** sensor shows the total, and then **save what the light shows** into the preset.

## 0.10.0b2

- **Acclimation** (Configure): for a new tank, new plants or new livestock. The schedule starts at lower brightness (e.g. 60 %) and a shorter light period (Off steps up to e.g. 2 h earlier), and steps up every few days until it's back at your normal schedule. It never goes beyond your normal schedule and finishes by itself.
- A notification at every step, an **Acclimation** sensor (current level, next step, end date) and an **Acclimation** switch to pause it (holds the level and stops the day count).

## 0.10.0b1

- **Edit a preset** (Configure): pick a preset from a list that shows its values (channels, fan, total power), then change them in a form filled with that preset, including its name. Renaming keeps schedule steps that use the preset working. **Show on the light now** sends the new values to the light when you save.
- **Add a preset** is only for new presets now and warns about an existing name instead of overwriting it.
- **Remove presets** shows each preset's values.
- Includes everything from the 0.9.1 betas (0.9.1 itself won't be released separately).

## 0.9.1b5

- New integration icon: an aquarium with the light bar on its rim, shining its red, green, blue and UV channels onto a plant (Home Assistant 2026.3 or newer). The HACS list doesn't show integration icons of this kind yet.

## 0.9.1b4

- First integration icon: the light bar with its four channels shining into the water.

## 0.9.1b3

- **Current step** and **Next step** show what a step does with their icon: sunrise (on after off), palette (colour change while on) or sunset (off).
- New `kind` attribute on both sensors (`sunrise`, `change` or `sunset`) for automations.

## 0.9.1b2

- **All steps** sensor is easier to read: `15:00 · On · Chat GPT | 21:00 · Off`.

## 0.9.1b1

- **Medium** is now the default fade smoothness (at most one command every 10 s). A smoothness you chose yourself is kept.
- Schedule step descriptions show **On** for steps that turn the light on, like **Off** for the others: `15:00 · On · Chat GPT 100% · fade 60 min · every day`.

## 0.9.0

First public release.

- Light with brightness and colour (R, G, B and UV as the white channel), the app's 12 presets as effects, and smooth fades (`transition`).
- Sliders for each channel and the fan, a preset picker with your own presets on top.
- Your own presets with name, channels and fan speed.
- Built-in schedule: fade to a preset or off at set times on chosen days, with per-step fade curve and smoothness, retries when the light can't be reached, and catch-up after a restart.
- Natural (perceptual) fade curve and adjustable fade smoothness.
- Power limit like the app (total power at most 100 %), with a **Power** sensor.
- Sensors for the schedule: **All steps**, **Current step**, **Next step**.
