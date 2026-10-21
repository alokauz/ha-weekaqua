# Backlog

Ideas and planned features, not yet built. Move an item to `CHANGELOG.md` when it ships.

## Planned

### Daily light amount

A sensor showing the day's light as **full-power hours**: the integral of total power over the day, e.g. "4.3 h of full power today", plus the planned amount for the whole day from the schedule.

- For comparing schedules and acclimation weeks.
- Honest about what it is: relative light from the channel levels and the power weights, **not** PAR/PPFD or DLI (that needs a PAR meter; channel photon output, optics, water depth and mounting height all differ).
- Later, optional: a PAR calibration profile (measured PPFD at the substrate/canopy for a few channel combinations) to estimate DLI, clearly labelled as estimated.

### Daily light chart

A view of the whole day: R, G, B and UV over 24 h with sunrise and sunset ramps, the Off times, the current time, and the effect of acclimation and the CO₂ fallback.

- Done in part: the dashboard card has a 24-hour graph of the **Power** sensor (what actually happened).
- Next step: a sensor with the day's planned curve (time → channel levels) in its attributes, plus a ready-made dashboard card config for a chart card (e.g. ApexCharts card from HACS).
- Possible later: a custom card with drag-to-edit schedule points (a separate frontend project, much larger).

## Ideas

- **Other Week Aqua models**: model codes 5745 and 5747–5752 use other protocols (already in the decompiled app); needs owners of those lights to test.
- **Sunrise/sunset-based schedule steps** (e.g. "30 min before sunset") in the built-in schedule.
- **Translations**, e.g. Russian.
- **Fewer reloads** when settings change (apply fade/power/schedule settings without reloading the integration).
- **Release checks**: make the release workflow refuse a version without a `CHANGELOG.md` entry.
- **1.0.0** once the schedule has run for a week or two in daily use without problems.
- **HACS default store** listing (pull request to `hacs/default`) around 1.0.0.
- **README screenshots** and a **bug report template** before announcing it (forum, Reddit, aquarium groups).
