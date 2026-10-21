# Week Aqua for Home Assistant — notes for Claude Code

Custom Home Assistant integration (`custom_components/weekaqua`) that controls a
Week Aqua L600 Pro aquarium light over Bluetooth LE, using Home Assistant's own
Bluetooth stack (a Raspberry Pi's built-in adapter in the owner's setup).
Installed by users through HACS from this repository. Owner: Flint.

## The light's protocol (reverse-engineered from the WEEK AQUA Android app 3.0.28)

- Advertises service `FFF0` and a model code in the advertisement. This
  integration supports model code **5746** ("WEK" protocol): manufacturer data
  key `0x4657`, Bluetooth name `B3.0-L600pro-…`. Other model codes (5745,
  5747–5752) use *different* protocols and are not supported.
- Commands are written to characteristic **`FFF2`** (write without response) on
  B3.0 boards; older boards use `FFE1`. 8 bytes, padded with `0x55`. No checksum,
  no encryption, no responses — the light's state **cannot be read back**.

| Command | Bytes |
|---|---|
| Channels | `FB F9 R G B UV 55 55` — each `00`–`EB` (235 = 100 %) |
| Fan | `FC XX 55 55 55 55 55 55` (`00`–`EB`) |
| Clock | `FF HH MM SS 55 55 55 55` — decimal digits written as hex (14:30 → `14 30`) |
| Light's own simple schedule | `FD F1 55…` |
| Light's own advanced schedule | `FD F2 55…` |

- The light accepts **one** Bluetooth connection at a time. The integration
  connects on demand and disconnects 30 s after the last command so the phone
  app can still connect.
- The app's 12 presets (names and raw levels) are in `const.py` → `PRESETS`.
- **Power limit**: the app computes total power = 0.39·R + 0.41·G + 0.53·B +
  0.11·UV (each as a fraction of 235) and never allows more than 100 %. All four
  channels at 100 % would be 144 %. The app's own *Gorgeous* preset is 101.8 %
  and is sent unchanged by the app, so app presets are exempt here too.
- The owner sets the light's *own* schedule (in the app) to 00:00–23:59 with no
  ramp, so this integration controls all timing.

## Code layout

| File | What it does |
|---|---|
| `const.py` | Protocol constants, command builders, presets, power formula, option keys |
| `device.py` | `WeekAquaDevice`: BLE connection, channel state (`levels`, `target`), fades, fan, presets, power limit, listeners |
| `schedule.py` | `WeekAquaScheduler`: schedule steps from options, firing, retries, startup catch-up, log text |
| `acclimation.py` | Acclimation program: ramps brightness and light period up to the normal schedule, then finishes; progress in a `Store`, notifications |
| `co2.py` | CO₂ interlock: watches the CO₂ plug entity, ready after the lead time, fallback factor; treats a plug already on at HA start as ready |
| `binary_sensor.py` | Connection, CO₂ ready |
| `diagnostics.py` | Download diagnostics |
| `light.py` | RGBW light (white = UV), transitions, presets as effects |
| `number.py` | Sliders 1. R / 2. G / 3. B / 4. UV / 5. Fan (Configuration section, slider or box) |
| `select.py` | Preset picker (own presets first, most recently used on top) |
| `button.py` | Sync clock, resume the light's own simple/advanced schedule |
| `switch.py` | Schedule on/off |
| `sensor.py` | Power, Next step, Current step, All steps |
| `config_flow.py` | Bluetooth discovery + the **Configure** menu (options flow) |
| `strings.json` + `translations/en.json` | UI texts — **keep both identical** |
| `brand/icon.png`, `brand/icon@2x.png` | Integration icon (256 / 512 px), rendered from `assets/icon.svg` |

## Design decisions to keep

- Fades are done by the integration (the light can't fade on command): steps
  follow the clock; *Natural* curve = gamma 2.2 in perceived brightness;
  *smoothness* = shortest time between commands; entity states update at most
  every 30 s during a fade (recorder database size). Any manual change cancels
  a fade. A fade retries its final level if the last steps failed.
- Step timing: On steps start fading in at their time; Off steps are fully off at their time (fade starts `fade` minutes earlier, shortened if it would overlap the previous step's fade). `Scheduler.effective_time` = target time (with acclimation), `run_window`/`run_time`/`run_fade` = when and how long it actually runs.
- Schedule steps are keyed by time (saving the same time replaces a step).
  Failed steps retry every 30 s for 10 min. After HA starts, the light is put
  where the schedule says (continuing a fade). Not on reloads.
- Options (presets, schedule, settings) live in the config entry's `options`;
  saving them reloads the entry.
- Brightness factors multiply: step brightness × acclimation × CO₂ fallback. The CO₂ interlock and acclimation only ever lower the light. Maintenance/photo mode (`Scheduler.override`) skips steps and fades back to the schedule when it ends.
- The power limit applies to everything, app presets included (no exemptions). Single channel sliders refuse changes above the power limit (like the app);
  everything else scales down proportionally. Lowering is always allowed.
- Acclimation never goes beyond the normal schedule (brightness ≤ 100 % of each step, Off steps only ever earlier, never before the previous step's fade ends) and always finishes by itself. Keep it that way.
- Never change entity `unique_id`s (users' entity IDs and automations depend on
  them). Device manufacturer stays "Week Aqua".
- `async_at_started` and similar callbacks must be `async def` or `@callback`
  functions — a plain lambda runs in a thread (this was a real bug, see
  `test_startup_catch_up`).

## Tests

```
python -m pip install -r requirements_test.txt   # Python 3.13
python -m pytest
```

`requirements_test.txt` also pins the requirements of HA's `bluetooth`,
`bluetooth_adapters` and `usb` components (the test package doesn't include
them). When bumping `pytest-homeassistant-custom-component`, update those pins
from the new HA version's `components/<name>/manifest.json`.

Home Assistant's test tools are made for Linux/macOS; on Windows run them in WSL
(`wsl`, then the commands above) if they won't install natively. GitHub Actions
also runs them on every push (`.github/workflows/release.yml`).

Test notes: the `client` fixture fakes `asyncio.sleep` (also inside `block_till_done`), so state-change events need `await let_loop_run()` to be delivered. `conftest.py` mocks the setup of HA's bluetooth/bluetooth_adapters/usb components (they depend on the machine and broke when GitHub's runner image changed); CI is pinned to `ubuntu-24.04`. Tests fake the Bluetooth client (`fake_client`) and check the exact
bytes sent. Patching `asyncio.sleep` in `device` patches it globally — only
freeze long waits. Fake clocks via `loop.time` must not be active while waiting
for HA's own time triggers.

## Backlog

`BACKLOG.md` lists planned features, items waiting for a decision, and ideas. When an item ships, remove it there and describe it in `CHANGELOG.md`. Items under "Waiting for a decision" need the owner's answer first.

## Versions and releases

Semantic versioning: MAJOR.MINOR.PATCH (patch = fixes and small adjustments,
minor = new features, major = breaking changes for existing users, e.g. entity
IDs or option formats). Still 0.x: go to 1.0.0 once the owner says it has
proven itself in daily use.

Changes are tested by the owner as **betas** before a real release:

1. Make the change, add or adjust tests, run `python -m pytest`.
2. Add a section for the new version at the top of `CHANGELOG.md`
   (`## 0.9.2b1`, then short bullet points of the user-visible changes). The
   release workflow puts that section into the release notes, which Home
   Assistant shows in the update dialog, plus a full-changelog link. For a
   final release (e.g. `## 0.9.2`), summarise all of its betas in one section.
3. Set `version` in `custom_components/weekaqua/manifest.json` to the next
   version with a beta suffix, e.g. `0.9.1b1` (next beta of the same version:
   `0.9.1b2`). Push to `main`. The workflow runs the tests and publishes a
   **pre-release** `v0.9.1b1`; HACS only shows it with "Show beta versions".
4. The owner installs it (HACS → Week Aqua → Redownload → Show beta versions)
   and tests it.
5. When the owner approves, set the version to `0.9.1` (no suffix) and push:
   that becomes the normal release everyone gets.

Several changes can be collected in one beta. Commits without a version change
are not released. Update `README.md` when users see a difference. Never push
with failing tests. Don't create releases by hand.
