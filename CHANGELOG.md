# Changelog

Key changes in each version. Betas (e.g. 0.9.1b1) are pre-releases for testing.

## 0.10.0b9

- With CO₂ control on, the CO₂ switches are part of the schedule sensors: **All steps** shows them in the timeline (e.g. `11:00 · CO₂ on | 14:00 · On · Chat GPT Max 60% | 20:00 · CO₂ off | 21:00 · Off`), and **Next step** shows a CO₂ switch when it comes next (with a CO₂ icon). If a CO₂ switch and a light step happen in the same minute, the light step is shown with the CO₂ switch in its `also` attribute.

## 0.10.0b8

- **Configure** is grouped: **Presets** (add, edit, remove), **Schedule** (add or update a step, remove steps; shows the current schedule), **Acclimation**, **CO₂**, **Maintenance and photo modes**, and **Light settings** (fade smoothness and curve, power limit, slider or number input).

## 0.10.0b7

- **CO₂ control** (Configure → CO₂, optional): switches the CO₂ plug from the light schedule. On a set time before the day's first On step, off a set time before the last Off step, never longer than a daily maximum. A watchdog switches CO₂ off within a minute whenever it is on outside that window (at night, with the schedule switched off, or turned on by hand) and notifies you. If Home Assistant wasn't running when the window started, CO₂ is switched on when it starts.
- Requires confirming a **backstop in the plug itself** (an off-only schedule or auto-off), because Home Assistant can't switch the plug while it isn't running. CO₂ is deliberately not switched off on restarts.
- New **CO₂ schedule** sensor, e.g. `14:00–20:00 (6 h)`.

## 0.10.0b6

- **CO₂ interlock** (Configure): choose the entity that switches your CO₂ (e.g. the solenoid's smart plug). If it hasn't been on for the lead time when an On step runs, or turns off or becomes unavailable while the light is on, the light is held at a fallback brightness and you get a notification; it comes back up by itself once CO₂ is ready. A plug that is already on when Home Assistant restarts counts as ready. New **CO₂ ready** sensor with the reason.
- **Maintenance mode** and **Photo mode** switches: a preset for a set time (Configure: preset and minutes), skipping schedule steps, then back to the schedule by itself.
- **Connection diagnostics**: **Connection** and **Last command** sensors (Diagnostic section), a notice under Settings → Repairs when the light has been unreachable for 10 minutes (it disappears by itself), and **Download diagnostics** for bug reports.
- **Acclimation**: a date-by-date plan in Configure → Acclimation, and **Go back one step** (e.g. if algae appear), which repeats the previous stage for a full interval.
- The app's *Gorgeous* preset (101.8 %) is now scaled slightly to stay within the power limit, like everything else.

## 0.10.0b5

- **Off steps now end at their time**: `21:00 · Off · fade 60 min` means the light is fully off at 21:00, and the sunset starts at 20:00. On steps still start fading in at their time, so a light period runs from the On time to the Off time, like most aquarium lights. **If you have Off steps with a fade, they now finish earlier than before**: move them later by the fade time to keep the old timing.
- Off steps show when their fade starts (`fade 60 min from 20:00`). A sunset that would overlap the previous step's fade is shortened so it still ends on time. The form refuses an Off fade that would have to start before midnight.
- The actual channel values of each On step are shown: **Current step** and **Next step** have a `channels` attribute (e.g. `R 35% G 70% B 35% UV 0% · power 61%`), and during acclimation the **Acclimation** sensor and **Configure → Acclimation** list what each On step uses in the current iteration.

## 0.10.0b4

- While acclimation runs, **Current step** and **All steps** show what actually happens, like **Next step** already did: the moved Off time and the reduced brightness, with the normal values alongside, e.g. `15:00 · On · Nature 70% (acclimation, normally 100%)`.
- The schedule form notes when acclimation is running (it lists your normal values).

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
