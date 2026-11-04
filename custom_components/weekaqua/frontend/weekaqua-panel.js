/*
 * Week Aqua panel: lighting, the day's schedule, acclimation and spectrum controls.
 * Served and registered by the Week Aqua integration (type: custom:weekaqua-panel).
 *
 * Finds its entities itself (platform "weekaqua" + translation key), so it works
 * whatever the entity IDs are. With several lights, set `device_id`.
 */

const I18N = {
  en: {
    brand: "AQUARIUM LIGHTING", connected: "Connected", disconnected: "Connection unavailable",
    unavailable: "Unavailable", fading: "Fading", light_on: "Light on", lights_off: "Lights off",
    output: "{v}% output", turn_on: "Turn light on", turn_off: "Turn light off",
    offline_warning: "The light is not connected. Controls are unavailable; schedule details may be out of date.",
    up_next: "Up next", schedule_paused: "Schedule paused", no_step: "No scheduled step available",
    step_channels: "Step channels", scheduled_spectrum: "Scheduled spectrum", brightness: "Brightness",
    output_short: "Output", step_unavailable: "Step channel data is unavailable.",
    schedule: "Schedule", photo: "Photo", maintenance: "Maintenance", active: "Active", off: "Off",
    stops_co2: "Off also stops CO₂", resume_schedule: "Resume schedule",
    acclimation_day: "Acclimation · day {day} · stage {stage} of {stages}", next_change: "Next change {date}",
    fph_title: "Full-power hours · acclimation", planned_now: "h / day planned now",
    day_stage: "Day {day} · {stage} · Finish {finish}", paused: "Paused", running: "Running", stage: "Stage {n}",
    current: "CURRENT", stage_tip: "Stage {n}: {h} full-power hours/day · {what}", current_plan: "current plan",
    estimate: "estimate", today_accumulated: "Today accumulated",
    fph_note: "Teal = the integration's plan for today. Other stages (≈) are estimates from each stage's brightness and light period, anchored to today's curve.<br>1 full-power hour = 1 hour at 100% output, or 2 hours at 50%. This is relative output, not PAR/DLI. The CO₂ fallback is left out.",
    todays_light: "Today's light", accumulated: "{a} h accumulated · {p} h planned so far",
    comparison_unavailable: "Comparison unavailable", plan_unavailable: "Light plan unavailable", now: "Now",
    full_day_plan: "Full-day plan {h} h · {from}–{until}",
    plan_note: "Relative full-power hours, not measured PAR/DLI. Forecast supplied by the integration; the CO₂ fallback is left out.",
    current_label: "Current", next_label: "Next", in_time: "{h} h {m} min",
    adjust: "Adjust acclimation", finish: "Finish {date}", pause_acc: "Pause acclimation", resume_acc: "Resume acclimation",
    days_to_move: "Days to move", advance: "Advance {n} days", go_back: "Go back {n} days",
    finish_or_today: "Finish {date}, or today if that completes it", finish_stops: "Finish {date} · stops at day 1",
    move_note: "Moves your current day and finish date together. Brightness follows the configured stages. Pause holds the current level and stops counting days.",
    moved_forward: "Acclimation moved forward by {n} day(s).", moved_back: "Acclimation moved back by {n} day(s).",
    choose_days: "Choose 1–60 whole days.", back_to_schedule: "Back to schedule",
    troubleshooting: "Connection & troubleshooting", last_delivered: "Last delivered write: {t}",
    latest_attempt: "Latest attempt: {r} · Failures {f} · Retries {x}",
    delivered_note: "Delivered means the Bluetooth write succeeded; the light can't confirm it applied it.",
    resend: "Re-send state", sync: "Sync clock",
    co2_ready: "CO₂ ready", co2_off: "CO₂ off", co2_warming: "CO₂ warming up", co2_unavailable: "CO₂ plug unavailable",
    co2_schedule: "CO₂ {s}", spectrum_controls: "Spectrum & manual controls", choose_preset: "Choose a preset…",
    fan: "Fan", manual_note: "Manual changes override the schedule until its next step. Use Back to schedule to return to it now.",
    not_found: "No Week Aqua light found. Is the integration set up?",
    timeline_label: "Daily schedule", siesta: "siesta",
  },
  ru: {
    brand: "ОСВЕЩЕНИЕ АКВАРИУМА", connected: "Подключено", disconnected: "Нет связи",
    unavailable: "Недоступно", fading: "Плавный переход", light_on: "Свет включён", lights_off: "Свет выключен",
    output: "мощность {v}%", turn_on: "Включить свет", turn_off: "Выключить свет",
    offline_warning: "Светильник не подключён. Управление недоступно; данные расписания могут быть устаревшими.",
    up_next: "Далее", schedule_paused: "Расписание на паузе", no_step: "Нет запланированных шагов",
    step_channels: "Каналы шага", scheduled_spectrum: "Спектр по расписанию", brightness: "Яркость",
    output_short: "Мощность", step_unavailable: "Данные о каналах шага недоступны.",
    schedule: "Расписание", photo: "Фото", maintenance: "Обслуживание", active: "Вкл", off: "Выкл",
    stops_co2: "Выключение останавливает и CO₂", resume_schedule: "Возобновить расписание",
    acclimation_day: "Акклиматизация · день {day} · этап {stage} из {stages}", next_change: "Следующее изменение {date}",
    fph_title: "Часы полной мощности · акклиматизация", planned_now: "ч / день по плану сейчас",
    day_stage: "День {day} · {stage} · Окончание {finish}", paused: "На паузе", running: "Идёт", stage: "Этап {n}",
    current: "СЕЙЧАС", stage_tip: "Этап {n}: {h} ч полной мощности в день · {what}", current_plan: "текущий план",
    estimate: "оценка", today_accumulated: "Накоплено сегодня",
    fph_note: "Бирюзовый — план интеграции на сегодня. Остальные этапы (≈) — оценка по яркости и длине светового дня каждого этапа, от сегодняшней кривой.<br>1 час полной мощности = 1 час на 100% или 2 часа на 50%. Это относительная величина, не PAR/DLI. Запасная яркость при неготовом CO₂ не учитывается.",
    todays_light: "Свет сегодня", accumulated: "Накоплено {a} ч · по плану к этому времени {p} ч",
    comparison_unavailable: "Сравнение недоступно", plan_unavailable: "План освещения недоступен", now: "Сейчас",
    full_day_plan: "План на день {h} ч · {from}–{until}",
    plan_note: "Относительные часы полной мощности, а не измеренные PAR/DLI. Прогноз интеграции; запасная яркость при неготовом CO₂ не учитывается.",
    current_label: "Сейчас", next_label: "Далее", in_time: "{h} ч {m} мин",
    adjust: "Настройка акклиматизации", finish: "Окончание {date}", pause_acc: "Приостановить акклиматизацию", resume_acc: "Возобновить акклиматизацию",
    days_to_move: "Сдвинуть на дней", advance: "Вперёд на {n} дн.", go_back: "Назад на {n} дн.",
    finish_or_today: "Окончание {date}, или сегодня, если это её завершает", finish_stops: "Окончание {date} · не раньше первого дня",
    move_note: "Сдвигает текущий день и дату окончания вместе. Яркость следует настроенным этапам. Пауза сохраняет текущий уровень и не считает дни.",
    moved_forward: "Акклиматизация сдвинута вперёд на {n} дн.", moved_back: "Акклиматизация сдвинута назад на {n} дн.",
    choose_days: "Выберите от 1 до 60 целых дней.", back_to_schedule: "Вернуть расписание",
    troubleshooting: "Связь и устранение неполадок", last_delivered: "Последняя доставленная команда: {t}",
    latest_attempt: "Последняя попытка: {r} · Ошибок {f} · Повторов {x}",
    delivered_note: "«Доставлено» значит, что запись по Bluetooth прошла; светильник не может подтвердить, что применил её.",
    resend: "Отправить заново", sync: "Синхронизировать часы",
    co2_ready: "CO₂ готов", co2_off: "CO₂ выключен", co2_warming: "CO₂ набирается", co2_unavailable: "Розетка CO₂ недоступна",
    co2_schedule: "CO₂ {s}", spectrum_controls: "Спектр и ручное управление", choose_preset: "Выберите пресет…",
    fan: "Вентилятор", manual_note: "Ручные изменения действуют до следующего шага расписания. «Вернуть расписание» возвращает к нему сразу.",
    not_found: "Светильник Week Aqua не найден. Интеграция настроена?",
    timeline_label: "Расписание на день", siesta: "сиеста",
  },
};

// [domain, translation key] of everything the card uses
const KEYS = {
  light: ["light", null], connection: ["binary_sensor", "connection"], co2_ready: ["binary_sensor", "co2_ready"],
  schedule: ["switch", "schedule"], acclimation_switch: ["switch", "acclimation"],
  maintenance_mode: ["switch", "maintenance_mode"], photo_mode: ["switch", "photo_mode"],
  next_step: ["sensor", "next_step"], current_step: ["sensor", "current_step"], schedule_steps: ["sensor", "schedule_steps"],
  power: ["sensor", "power"], acclimation: ["sensor", "acclimation"], last_command: ["sensor", "last_command"],
  co2_schedule: ["sensor", "co2_schedule"], step_channels: ["sensor", "step_channels"], light_plan: ["sensor", "light_plan"],
  light_today: ["sensor", "light_today"], fade: ["sensor", "fade"],
  red: ["number", "channel_red"], green: ["number", "channel_green"], blue: ["number", "channel_blue"], uv: ["number", "channel_uv"],
  fan: ["number", "fan"], preset: ["select", "preset"],
  back_to_schedule: ["button", "back_to_schedule"], resend: ["button", "resend"], sync_clock: ["button", "sync_clock"],
};

const STYLE = ':host{display:block}*{box-sizing:border-box}ha-card{overflow:hidden;border-radius:20px;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color);box-shadow:var(--ha-card-box-shadow);border:1px solid var(--divider-color)}button,input,select{font:inherit}button{cursor:pointer;color:inherit}button:disabled,input:disabled,select:disabled{cursor:default;opacity:.45}button:focus-visible,summary:focus-visible,select:focus-visible{outline:2px solid #55c6b2;outline-offset:3px}ha-icon{--mdc-icon-size:21px;display:inline-flex}.hero{padding:23px 23px 20px;background:linear-gradient(125deg,rgba(38,166,154,.15),rgba(57,116,157,.04));border-bottom:1px solid var(--divider-color)}.top,.line,.channel-label{display:flex;align-items:center;justify-content:space-between;gap:12px}.brand{font-size:11px;letter-spacing:2px;font-weight:700;color:var(--secondary-text-color)}h2{margin:8px 0 7px;font-size:25px;letter-spacing:-.7px;font-weight:650}.subtitle,.muted{font-size:12px;color:var(--secondary-text-color);line-height:1.55}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#62bba2;margin-right:5px}.dot.offline{background:#ed9b63}.power{width:48px;height:48px;border-radius:50%;border:1px solid var(--divider-color);background:var(--card-background-color)}.power.active{background:#237d70;color:white;border-color:transparent}.hero-state{display:flex;align-items:center;gap:8px}.pill{font-size:11px;font-weight:600;padding:5px 9px;border-radius:7px;background:rgba(38,166,154,.12);color:var(--primary-text-color)}.body{padding:20px 23px}.section-label{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;font-weight:700;color:var(--secondary-text-color)}.next{margin:7px 0 17px;font-size:14px;font-weight:600;line-height:1.5}.next time{color:#319f8b;font-variant-numeric:tabular-nums;margin-right:8px}.timeline{display:grid;gap:5px;margin:0 0 20px}.event{min-width:0;border-top:3px solid #67bcb0;padding-top:10px}.event.co2{border-color:#849cc8}.event.end{border-color:#869096}.event.siesta{border-color:#b9a36a}.event b{display:block;font-size:13px;font-variant-numeric:tabular-nums}.event span{display:block;font-size:11px;line-height:1.5;color:var(--secondary-text-color);margin-top:4px}.step-spectrum{margin:0 0 20px;padding:14px;border:1px solid var(--divider-color);border-radius:12px}.step-name{font-size:13px;font-weight:600;margin:8px 0 14px}.step-bars{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px 18px}.step-track{height:5px;border-radius:4px;background:var(--divider-color);margin-top:8px;overflow:hidden}.step-track div{height:100%;border-radius:4px;background:var(--channel)}.step-meta{font-size:11px;color:var(--secondary-text-color);line-height:1.6;margin-top:13px}.step-note{font-size:10px;color:var(--secondary-text-color);line-height:1.5;margin-top:5px}.controls{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.control{border:1px solid var(--divider-color);border-radius:12px;background:transparent;display:flex;flex-direction:column;align-items:flex-start;gap:10px;padding:12px;font-size:12px;text-align:left}.control.active{background:rgba(38,166,154,.10);border-color:rgba(38,166,154,.38)}.control small{font-size:10px;color:var(--secondary-text-color);display:block;margin-top:3px}.notice{margin-top:15px;border-radius:11px;padding:11px 12px;background:rgba(111,167,99,.09);font-size:12px;line-height:1.6}.notice strong{font-weight:600}.stats{display:flex;flex-wrap:wrap;gap:7px 16px;margin-top:15px;font-size:11px;color:var(--secondary-text-color)}.stats span{display:flex;gap:5px;align-items:center}.stats ha-icon{--mdc-icon-size:15px}.expand{display:flex;align-items:center;justify-content:space-between;width:100%;border:0;border-top:1px solid var(--divider-color);background:transparent;padding:15px 23px;font-size:12px;text-align:left}.spectrum{padding:3px 23px 22px}.channel{margin-top:16px}.channel-label{font-size:12px}.channel-label span{border-left:3px solid var(--channel);padding-left:8px}.channel-label b{font-size:11px;font-weight:600;color:var(--secondary-text-color)}input[type=range]{width:100%;accent-color:var(--channel,#48ae9c);height:26px;margin:5px 0 0;cursor:pointer}select{width:100%;padding:11px;border:1px solid var(--divider-color);border-radius:9px;background:var(--card-background-color);color:var(--primary-text-color);margin-top:14px}.resume{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:15px;width:100%;padding:11px;background:#237d70;color:white;border:0;border-radius:10px;font-size:12px}.error{margin-top:12px;color:var(--error-color);font-size:12px}.warning{font-size:12px;line-height:1.6;padding:11px;border-radius:9px;background:rgba(224,153,65,.12);margin-bottom:15px}.brightness{margin:15px 0 0}.footer-note{font-size:11px;line-height:1.55;color:var(--secondary-text-color);margin-top:14px}.days{width:75px;margin:10px;padding:8px;background:var(--card-background-color);color:inherit;border:1px solid var(--divider-color);border-radius:7px}@media(max-width:360px){.hero,.body{padding:18px}.spectrum{padding:3px 18px 18px}.control{padding:10px}.event b{font-size:12px}.event span{font-size:10px}}';

const COLORS = { red: "#ed6f7d", green: "#66cfa0", blue: "#78aaff", uv: "#b995ef", power: "#d5ac64" };

class WeekAquaPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._open = false;
    this._busy = false;
    this._error = "";
    this._notice = "";
    this._days = 1;
    this._ids = {};
    this._seen = {};
    this.shadowRoot.addEventListener("click", (e) => this._click(e));
    this.shadowRoot.addEventListener("change", (e) => this._change(e));
    this.shadowRoot.addEventListener("toggle", (e) => { if (e.target.tagName === "DETAILS") this._diag = e.target.open; }, true);
  }

  static getStubConfig() { return {}; }

  setConfig(config) {
    this._config = { ...config };
    this._entitiesRef = null;
    this._seen = {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (hass.entities !== this._entitiesRef) this._resolve();
    // Only redraw when one of our entities (or the CO₂ plug, or the language) changed
    const ids = [...Object.values(this._ids), this._co2Plug()].filter(Boolean);
    const lang = hass.locale?.language || hass.language;
    const changed = lang !== this._lang || ids.some((id) => hass.states[id] !== this._seen[id]);
    if (!changed) return;
    this._lang = lang;
    for (const id of ids) this._seen[id] = hass.states[id];
    if (!this.shadowRoot.activeElement?.matches("input,select")) this._render();
  }

  connectedCallback() {
    this._timer = setInterval(() => { if (!this.shadowRoot.activeElement?.matches("input,select")) this._render(); }, 60000);
  }

  disconnectedCallback() { clearInterval(this._timer); clearTimeout(this._noticeTimer); }

  getCardSize() { return this._open ? 12 : 8; }

  getGridOptions() { return { columns: 12, rows: "auto", min_columns: 6 }; }

  // ---- finding our entities ------------------------------------------------

  _resolve() {
    this._entitiesRef = this._hass.entities;
    const ours = Object.values(this._hass.entities || {}).filter((e) => e.platform === "weekaqua");
    const device = this._config.device_id || ours.find((e) => e.entity_id.startsWith("light."))?.device_id;
    this._device = device;
    const mine = ours.filter((e) => e.device_id === device);
    this._ids = {};
    for (const [key, [domain, tkey]] of Object.entries(KEYS)) {
      const found = mine.find((e) => e.entity_id.startsWith(domain + ".") && (tkey === null || e.translation_key === tkey));
      if (found) this._ids[key] = found.entity_id;
    }
    this._seen = {};
  }

  _co2Plug() { return this._attr("co2_ready").co2_entity; }
  _entity(key) { const id = this._ids[key]; return id ? this._hass.states[id] : undefined; }
  _state(key) { return this._entity(key)?.state ?? "unavailable"; }
  _attr(key) { return this._entity(key)?.attributes ?? {}; }
  _valid(key) { return !["unavailable", "unknown"].includes(this._state(key)); }

  // ---- helpers ----------------------------------------------------------------

  _t(key, vars = {}) {
    const lang = (this._lang || "en").toLowerCase().startsWith("ru") ? "ru" : "en";
    const text = I18N[lang][key] ?? I18N.en[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
  }

  _esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  _num(v) { return Number.isFinite(Number(v)) ? Math.max(0, Math.min(100, Number(v))) : null; }
  _icon(name) { return '<ha-icon icon="mdi:' + name + '"></ha-icon>'; }

  _clock(value) {
    const d = new Date(value);
    if (isNaN(d)) return "—";
    return new Intl.DateTimeFormat(this._lang || "en", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: this._hass?.config?.time_zone }).format(d);
  }

  _date(iso, delta = 0) {
    const d = new Date(String(iso) + "T12:00:00Z");
    if (isNaN(d)) return "—";
    d.setUTCDate(d.getUTCDate() + delta);
    return d.toISOString().slice(0, 10);
  }

  _setNotice(text) {
    this._notice = text;
    clearTimeout(this._noticeTimer);
    this._noticeTimer = setTimeout(() => { this._notice = ""; this._render(); }, 8000);
  }

  // ---- actions --------------------------------------------------------------------

  async _call(domain, service, data = {}) {
    if (this._busy) return false;
    this._busy = true;
    this._error = "";
    this._render();
    try {
      await this._hass.callService(domain, service, data);
      return true;
    } catch (e) {
      this._error = e.message || String(e);
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _callEntity(domain, service, key, data = {}) {
    const id = this._ids[key];
    return id ? this._call(domain, service, { entity_id: id, ...data }) : false;
  }

  _acclimation(service, data = {}) {
    return this._call("weekaqua", service, { ...(this._device ? { device_id: this._device } : {}), ...data });
  }

  async _shift(direction) {
    const days = Number(this._days || 1);
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      this._error = this._t("choose_days");
      this._render();
      return;
    }
    if (await this._acclimation("acclimation_shift", { days: days * direction })) {
      this._setNotice(this._t(direction > 0 ? "moved_forward" : "moved_back", { n: days }));
      this._render();
    }
  }

  _click(e) {
    const b = e.target.closest("[data-action]");
    if (!b || b.disabled) return;
    const a = b.dataset.action;
    if (a === "acclimation-pause") return this._acclimation("acclimation_pause");
    if (a === "acclimation-resume") return this._acclimation("acclimation_resume");
    if (a === "shift-forward") return this._shift(1);
    if (a === "shift-back") return this._shift(-1);
    if (a === "back-schedule") return this._callEntity("button", "press", "back_to_schedule");
    if (a === "resend") return this._callEntity("button", "press", "resend");
    if (a === "sync") return this._callEntity("button", "press", "sync_clock");
    if (a === "expand") { this._open = !this._open; this._render(); return; }
    if (a === "light") return this._callEntity("light", "toggle", "light");
    if (a === "toggle") return this._callEntity("switch", "toggle", b.dataset.key);
    if (a === "resume") return this._callEntity("switch", "turn_on", "schedule");
  }

  _change(e) {
    const el = e.target;
    if (el.hasAttribute("data-days")) { this._days = el.value; this._render(); return; }
    if (el.dataset.number) this._callEntity("number", "set_value", el.dataset.number, { value: Number(el.value) });
    if (el.dataset.brightness) this._callEntity("light", "turn_on", "light", { brightness_pct: Number(el.value) });
    if (el.dataset.preset && el.value) this._callEntity("select", "select_option", "preset", { option: el.value });
  }

  // ---- sections ---------------------------------------------------------------------

  _timelineHtml() {
    const E = (v) => this._esc(v);
    const events = Array.isArray(this._attr("schedule_steps").timeline) ? this._attr("schedule_steps").timeline : [];
    if (!events.length) return "";
    const cls = { co2_on: "co2", co2_off: "co2", off: "end", siesta: "siesta", on: "" };
    return '<div class="timeline" style="grid-template-columns:repeat(' + events.length + ',minmax(0,1fr))" aria-label="' + E(this._t("timeline_label")) + '">' +
      events.map((ev) => {
        const desc = String(ev.text || "").split(" · ").slice(1).join(" · ") + (ev.kind === "siesta" ? " (" + this._t("siesta") + ")" : "");
        return '<div class="event ' + (cls[ev.kind] ?? "") + '"><b>' + E(ev.time) + "</b><span>" + E(desc) + "</span></div>";
      }).join("") + "</div>";
  }

  _stepHtml() {
    const E = (v) => this._esc(v);
    const data = this._attr("step_channels");
    const state = this._state("step_channels");
    const head = '<div class="step-spectrum"><div class="line"><div class="section-label">' + E(this._t("step_channels")) + '</div><span class="subtitle">' + E(data.applies ?? "") + "</span></div>";
    if (!this._valid("step_channels")) return head + '<div class="step-meta">' + E(this._t("step_unavailable")) + "</div></div>";
    // Raw levels (0-235) are language-independent; fall back to the text for older versions
    const raw = data.levels || {};
    const fromText = Object.fromEntries([...state.matchAll(/\b(R|G|B|UV)\s+([\d.]+)%/g)].map((m) => [m[1], Number(m[2])]));
    const labels = [["R", "red"], ["G", "green"], ["B", "blue"], ["UV", "uv"]];
    const bars = labels.map(([label, key]) => {
      const v = Number.isFinite(Number(raw[label])) ? Math.round(Number(raw[label]) / 235 * 100) : this._num(fromText[label]);
      return '<div class="step-value" style="--channel:' + COLORS[key] + '"><div class="channel-label"><span>' + label + "</span><b>" + (v == null ? "—" : E(v) + "%") + '</b></div><div class="step-track"><div style="width:' + (v ?? 0) + '%"></div></div></div>';
    }).join("");
    const meta = (data.brightness ? E(this._t("brightness")) + " " + E(data.brightness) : "") + (data.power ? " · " + E(this._t("output_short")) + " " + E(data.power) : "");
    return head + '<div class="step-name">' + E(data.step ?? this._t("scheduled_spectrum")) + '</div><div class="step-bars">' + bars + '</div><div class="step-meta">' + meta + "</div>" +
      (data.co2_note ? '<div class="step-note">' + E(data.co2_note) + "</div>" : "") + "</div>";
  }

  _acclimationChartHtml() {
    const E = (v) => this._esc(v);
    const ac = this._attr("acclimation");
    const stages = Array.isArray(ac.stages) ? ac.stages : [];
    const plan = Number(this._state("light_plan"));
    if (!(Number(ac.day) > 0) || !stages.length || !Number.isFinite(plan)) return "";
    const p = this._attr("light_plan");
    const index = Math.max(0, Math.min(stages.length - 1, Number(ac.stage_index) || 0));
    const now = stages[index];
    // Hours of light at full brightness today, from today's curve
    const curve = Array.isArray(p.curve) ? p.curve : [];
    const minutes = (t) => { const a = String(t).split(":").map(Number); return a[0] * 60 + a[1]; };
    let lit = 0;
    for (let i = 1; i < curve.length; i++) lit += (minutes(curve[i].t) - minutes(curve[i - 1].t)) * (Number(curve[i].power) + Number(curve[i - 1].power)) / 200;
    const peak = Number(p.peak_power) / 100;
    const effective = peak > 0 ? (lit || plan) / peak : 0;
    const rows = stages.map((s, i) => {
      const hours = i === index ? plan
        : plan * (Number(s.brightness) / Math.max(1, Number(now.brightness))) * Math.max(0, effective + (Number(now.shorter_minutes) - Number(s.shorter_minutes)) / 60) / Math.max(0.01, effective);
      return { i, brightness: Number(s.brightness), hours, date: String(s.from).slice(5, 10) };
    });
    const max = Math.max(1, ...rows.map((r) => r.hours)) * 1.18;
    const bars = rows.map((r) => {
      const x = 45 + r.i * 84, y = 170 - r.hours / max * 132, h = 170 - y, cur = r.i === index;
      const tip = this._t("stage_tip", { n: r.i + 1, h: r.hours.toFixed(2), what: this._t(cur ? "current_plan" : "estimate") });
      return "<g><title>" + E(tip) + '</title><rect x="' + x + '" y="' + y + '" width="52" height="' + h + '" rx="6" fill="' + (cur ? "#44bfa9" : "#8dabc2") + '" opacity="' + (cur ? 1 : 0.5) + '"/>' +
        '<text x="' + (x + 26) + '" y="' + (y - 9) + '" text-anchor="middle" fill="currentColor" font-size="13" font-weight="600">' + (cur ? "" : "≈") + r.hours.toFixed(2) + "</text>" +
        '<text x="' + (x + 26) + '" y="190" text-anchor="middle" fill="currentColor" font-size="11">' + r.brightness + "%</text>" +
        '<text x="' + (x + 26) + '" y="207" text-anchor="middle" fill="currentColor" opacity=".65" font-size="10">' + E(r.date) + "</text>" +
        (cur ? '<text x="' + (x + 26) + '" y="225" text-anchor="middle" fill="#44bfa9" font-size="10">' + E(this._t("current")) + "</text>" : "") + "</g>";
    }).join("");
    const width = Math.max(460, rows.length * 84 + 30);
    const grid = [0, 0.5, 1].map((f) => '<line x1="35" x2="' + (rows.length * 84 + 20) + '" y1="' + (170 - f * 132) + '" y2="' + (170 - f * 132) + '" stroke="currentColor" opacity=".12"/><text x="2" y="' + (174 - f * 132) + '" fill="currentColor" opacity=".65" font-size="10">' + (max * f).toFixed(1) + "</text>").join("");
    const actual = Number(this._state("light_today"));
    const valid = this._valid("light_today") && Number.isFinite(actual);
    const pct = valid && plan > 0 ? Math.min(100, actual / plan * 100) : 0;
    const status = ac.paused ? this._t("paused") : this._t("stage", { n: index + 1 });
    return '<div class="step-spectrum" style="margin-top:18px"><div class="section-label">' + E(this._t("fph_title")) + '</div>' +
      '<div style="display:flex;align-items:baseline;gap:8px;margin:12px 0 4px"><strong style="font-size:30px;font-variant-numeric:tabular-nums">' + plan.toFixed(2) + '</strong><span class="muted">' + E(this._t("planned_now")) + "</span></div>" +
      '<div class="muted">' + E(this._t("day_stage", { day: ac.day, stage: status, finish: ac.back_to_normal ?? "—" })) + "</div>" +
      '<svg viewBox="0 0 ' + width + ' 234" role="img" style="display:block;width:100%;height:auto;margin-top:12px">' + grid + bars + "</svg>" +
      '<div class="line muted"><span>' + E(this._t("today_accumulated")) + "</span><strong>" + E(valid ? actual.toFixed(2) : "—") + " / " + plan.toFixed(2) + " h</strong></div>" +
      '<div style="height:6px;border-radius:6px;background:var(--divider-color);overflow:hidden;margin-top:8px"><div style="width:' + pct + '%;height:100%;background:#44bfa9"></div></div>' +
      '<div class="footer-note">' + this._t("fph_note") + "</div></div>";
  }

  _todayHtml() {
    const E = (v) => this._esc(v);
    const plan = this._attr("light_plan"), today = this._attr("light_today");
    const actual = Number(this._state("light_today")), expected = Number(today.planned_until_now);
    const valid = this._valid("light_today") && Number.isFinite(actual) && Number.isFinite(expected);
    const curve = (plan.curve || []).filter((p) => /^\d{2}:\d{2}$/.test(p.t));
    const x = (t) => { const [h, m] = t.split(":").map(Number); return 28 + (h * 60 + m) / 1440 * 444; };
    const y = (v) => 118 - Math.max(0, Math.min(100, Number(v) || 0)) * 0.95;
    const lines = [["r", COLORS.red, "R"], ["g", COLORS.green, "G"], ["b", COLORS.blue, "B"], ["uv", COLORS.uv, "UV"], ["power", COLORS.power, this._t("output_short")]];
    const local = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: this._hass.config.time_zone }).format(new Date());
    const plot = curve.length
      ? '<svg viewBox="0 0 500 150" role="img" style="width:100%;height:auto">' +
        [0, 50, 100].map((v) => '<line x1="28" x2="472" y1="' + y(v) + '" y2="' + y(v) + '" stroke="currentColor" opacity=".12"/><text x="1" y="' + (y(v) + 3) + '" fill="currentColor" font-size="9">' + v + "</text>").join("") +
        lines.map(([k, c]) => '<polyline fill="none" stroke="' + c + '" stroke-width="' + (k === "power" ? 2.5 : 1.4) + '" points="' + curve.map((p) => x(p.t) + "," + y(p[k])).join(" ") + '"/>').join("") +
        [0, 6, 12, 18, 24].map((h) => '<text x="' + (28 + h / 24 * 444) + '" y="139" text-anchor="middle" fill="currentColor" font-size="10">' + String(h).padStart(2, "0") + ":00</text>").join("") +
        '<line x1="' + x(local) + '" x2="' + x(local) + '" y1="15" y2="120" stroke="currentColor" stroke-dasharray="3 3"/><text x="' + Math.min(450, x(local) + 4) + '" y="12" fill="currentColor" font-size="10">' + E(this._t("now")) + "</text></svg>"
      : '<div class="muted">' + E(this._t("plan_unavailable")) + "</div>";
    return '<div class="step-spectrum" style="margin-top:18px"><div class="section-label">' + E(this._t("todays_light")) + '</div><div class="next">' +
      E(valid ? this._t("accumulated", { a: actual.toFixed(2), p: expected.toFixed(2) }) : this._t("comparison_unavailable")) + "</div>" + plot +
      '<div class="stats">' + lines.map(([, c, n]) => '<span style="color:' + c + '">' + E(n) + "</span>").join("") + "</div>" +
      '<div class="footer-note">' + E(this._t("full_day_plan", { h: this._state("light_plan"), from: plan.light_from || "—", until: plan.light_until || "—" })) + "<br>" + E(this._t("plan_note")) + "</div></div>";
  }

  _adjustHtml(busy) {
    const E = (v) => this._esc(v);
    const ac = this._attr("acclimation");
    if (!(Number(ac.day) > 0)) return "";
    const paused = ac.paused === true || this._state("acclimation_switch") === "off";
    const n = Number(this._days || 1), day = Number(ac.day) || 1, back = Math.min(n, Math.max(0, day - 1));
    return '<div class="notice"><div class="line"><strong>' + E(this._t("adjust")) + "</strong><span>" + E(this._t(paused ? "paused" : "running")) + "</span></div>" +
      "<div>" + E(this._t("finish", { date: ac.back_to_normal || "—" })) + "</div>" +
      '<button class="resume" data-action="' + (paused ? "acclimation-resume" : "acclimation-pause") + '" ' + busy + ">" + this._icon(paused ? "play-outline" : "pause") + E(this._t(paused ? "resume_acc" : "pause_acc")) + "</button>" +
      '<label for="wa-days">' + E(this._t("days_to_move")) + '</label><input id="wa-days" class="days" data-days type="number" min="1" max="60" step="1" value="' + E(n) + '" ' + busy + ">" +
      '<div class="controls" style="grid-template-columns:1fr 1fr"><button class="control" data-action="shift-forward" ' + busy + ">" + E(this._t("advance", { n })) + "<small>" + E(this._t("finish_or_today", { date: this._date(ac.back_to_normal, -n) })) + "</small></button>" +
      '<button class="control" data-action="shift-back" ' + (busy || (back === 0 ? "disabled" : "")) + ">" + E(this._t("go_back", { n: back })) + "<small>" + E(this._t("finish_stops", { date: this._date(ac.back_to_normal, back) })) + "</small></button></div>" +
      '<div class="footer-note">' + E(this._t("move_note")) + "</div></div>";
  }

  _diagnosticsHtml(busy) {
    const E = (v) => this._esc(v);
    const d = this._attr("last_command");
    return '<details style="margin-top:18px" ' + (this._diag ? "open" : "") + "><summary>" + E(this._t("troubleshooting")) + '</summary><div class="footer-note">' +
      E(this._t("last_delivered", { t: this._clock(this._state("last_command")) })) + "<br>" +
      E(this._t("latest_attempt", { r: d.last_attempt_result || "—", f: d.failed_since_start ?? "—", x: d.retries_since_start ?? "—" })) + "<br>" + E(this._t("delivered_note")) +
      '</div><div class="controls" style="grid-template-columns:1fr 1fr;margin-top:12px"><button class="control" data-action="resend" ' + busy + ">" + E(this._t("resend")) + '</button><button class="control" data-action="sync" ' + busy + ">" + E(this._t("sync")) + "</button></div></details>";
  }

  _co2Html() {
    if (!this._entity("co2_ready") || !this._valid("co2_ready")) return "";
    const E = (v) => this._esc(v);
    const plug = this._hass.states[this._co2Plug()];
    let text;
    if (this._state("co2_ready") === "on") text = this._t("co2_ready");
    else if (!plug || ["unavailable", "unknown"].includes(plug.state)) text = this._t("co2_unavailable");
    else if (plug.state === "off") text = this._t("co2_off");
    else text = this._t("co2_warming");
    return "<span>" + this._icon("molecule-co2") + E(text) + "</span>" +
      (this._valid("co2_schedule") ? "<span>" + this._icon("clock-outline") + E(this._t("co2_schedule", { s: this._state("co2_schedule") })) + "</span>" : "");
  }

  _spectrumHtml(disabled) {
    const E = (v) => this._esc(v);
    const light = this._attr("light"), on = this._state("light") === "on";
    const brightness = on ? Math.round((light.brightness ?? 0) / 255 * 100) : 0;
    const slider = (key, label, color) => {
      const n = this._num(this._state(key)), a = this._attr(key);
      if (!this._entity(key)) return "";
      return '<div class="channel" style="--channel:' + color + '"><div class="channel-label"><span>' + E(label) + "</span><b>" + (n === null ? "—" : n + "%") + '</b></div><input aria-label="' + E(label) + '" type="range" min="' + E(a.min ?? 0) + '" max="' + E(a.max ?? 100) + '" step="' + E(a.step ?? 1) + '" value="' + (n ?? 0) + '" data-number="' + key + '" ' + (disabled || (n === null && key !== "fan" ? "disabled" : "")) + "></div>";
    };
    const presets = this._attr("preset").options ?? [];
    return '<div class="spectrum"><div class="brightness"><div class="channel-label"><span>' + E(this._t("brightness")) + "</span><b>" + brightness + '%</b></div><input aria-label="' + E(this._t("brightness")) + '" type="range" min="1" max="100" value="' + Math.max(1, brightness) + '" data-brightness="1" ' + disabled + "></div>" +
      '<select data-preset="1" aria-label="' + E(this._t("choose_preset")) + '" ' + disabled + '><option value="">' + E(this._t("choose_preset")) + "</option>" + presets.map((v) => '<option value="' + E(v) + '">' + E(v) + "</option>").join("") + "</select>" +
      slider("red", "R", COLORS.red) + slider("green", "G", COLORS.green) + slider("blue", "B", COLORS.blue) + slider("uv", "UV", COLORS.uv) + slider("fan", this._t("fan"), "#8a9aa3") +
      '<div class="footer-note">' + E(this._t("manual_note")) + "</div></div>";
  }

  // ---- the card ------------------------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) return;
    const E = (v) => this._esc(v);
    if (!this._ids.light) {
      this.shadowRoot.innerHTML = "<style>" + STYLE + '</style><ha-card><div class="body"><div class="warning">' + E(this._t("not_found")) + "</div></div></ha-card>";
      return;
    }
    const on = this._state("light") === "on";
    const online = this._state("connection") === "on";
    const schedule = this._state("schedule") === "on";
    const light = this._attr("light");
    const ac = this._attr("acclimation");
    const name = this._config.name || this._hass.devices?.[this._device]?.name_by_user || this._hass.devices?.[this._device]?.name || "Week Aqua";
    const next = this._attr("next_step");
    const when = this._clock(this._state("next_step"));
    const disabled = !online || this._busy ? "disabled" : "";
    const busy = this._busy ? "disabled" : "";
    const co2Control = this._valid("co2_schedule");
    const stopsCo2 = co2Control ? '<small>' + E(this._t("stops_co2")) + "</small>" : "";
    const tiles = [["schedule", "calendar-clock", "schedule"], ["photo_mode", "camera-outline", "photo"], ["maintenance_mode", "tools", "maintenance"]]
      .filter(([key]) => this._entity(key))
      .map(([key, icon, label]) => {
        const active = this._state(key) === "on";
        return '<button class="control ' + (active ? "active" : "") + '" data-action="toggle" data-key="' + key + '" aria-pressed="' + active + '" ' + disabled + ">" + this._icon(icon) +
          "<span>" + E(this._t(label)) + "<small>" + E(this._t(active ? "active" : "off")) + "</small>" + (key === "schedule" && active ? stopsCo2 : "") + "</span></button>";
      }).join("");
    const t = Date.parse(this._state("next_step"));
    const mins = Math.max(0, Math.floor((t - Date.now()) / 60000));
    const stages = Array.isArray(ac.stages) ? ac.stages.length : 0;
    const pill = !online ? this._t("unavailable") : on ? this._t(light.fading ? "fading" : "light_on") : this._t("lights_off");

    this.shadowRoot.innerHTML = "<style>" + STYLE + "</style><ha-card>" +
      '<div class="hero"><div class="top"><div><div class="brand">' + E(this._t("brand")) + "</div><h2>" + E(name) + "</h2></div>" +
      '<button class="power ' + (on ? "active" : "") + '" data-action="light" aria-label="' + E(this._t(on ? "turn_off" : "turn_on")) + '" ' + disabled + ">" + this._icon("power") + "</button></div>" +
      '<div class="line"><div class="subtitle"><span class="dot ' + (online ? "" : "offline") + '"></span>' + E(this._t(online ? "connected" : "disconnected")) + "</div>" +
      '<div class="hero-state"><span class="pill">' + E(pill) + '</span><span class="subtitle">' + E(this._t("output", { v: this._state("power") })) + "</span></div></div></div>" +
      '<div class="body">' +
      (online ? "" : '<div class="warning">' + E(this._t("offline_warning")) + "</div>") +
      '<div class="section-label">' + E(this._t(schedule ? "up_next" : "schedule_paused")) + '</div><div class="next"><time>' + E(when) + "</time>" + E(next.step ? next.step.replace(/^\d\d:\d\d\s*·\s*/, "") : this._t("no_step")) + "</div>" +
      this._timelineHtml() + this._stepHtml() +
      '<div class="controls">' + tiles + "</div>" +
      (schedule ? "" : '<button class="resume" data-action="resume" ' + disabled + ">" + this._icon("play-outline") + E(this._t("resume_schedule")) + "</button>") +
      (Number(ac.day) > 0 ? '<div class="notice"><strong>' + this._icon("sprout") + " " + E(this._t("acclimation_day", { day: ac.day, stage: (Number(ac.stage_index) || 0) + 1, stages })) + "</strong><br>" +
        E(this._state("acclimation")) + (ac.next_change ? " · " + E(this._t("next_change", { date: ac.next_change })) : "") + "</div>" : "") +
      this._acclimationChartHtml() + this._todayHtml() +
      '<div class="muted"><b>' + E(this._t("current_label")) + ":</b> " + E(this._state("current_step")) + "<br><b>" + E(this._t("next_label")) + ":</b> " +
      (Number.isFinite(t) ? E(this._t("in_time", { h: Math.floor(mins / 60), m: mins % 60 })) : "—") + (this._valid("fade") ? " · " + E(this._state("fade")) : "") + "</div>" +
      this._adjustHtml(busy) +
      '<button class="resume" data-action="back-schedule" ' + busy + ">" + E(this._t("back_to_schedule")) + "</button>" +
      this._diagnosticsHtml(busy) +
      (this._notice ? '<div class="muted" role="status">' + E(this._notice) + "</div>" : "") +
      '<div class="stats">' + this._co2Html() + "</div>" +
      (this._error ? '<div class="error" role="alert">' + E(this._error) + "</div>" : "") +
      '</div><button class="expand" data-action="expand" aria-expanded="' + this._open + '"><span>' + E(this._t("spectrum_controls")) + "</span>" + this._icon(this._open ? "chevron-up" : "chevron-down") + "</button>" +
      (this._open ? this._spectrumHtml(disabled) : "") + "</ha-card>";
  }
}

const TAG = "weekaqua-panel";

// The integration loads this file early, before the frontend has started. In some
// browsers (Firefox) the frontend then installs a new element registry, which drops
// elements defined before it: so check for a while and define the card again if so.
// A new subclass each time, as a constructor can't be defined twice in one registry.
function defineCard() {
  try {
    if (!customElements.get(TAG)) customElements.define(TAG, class extends WeekAquaPanel {});
  } catch (err) {
    console.warn("Week Aqua panel:", err);
  }
}
defineCard();
let defineChecks = 0;
const defineTimer = setInterval(() => {
  defineCard();
  if (++defineChecks >= 120) clearInterval(defineTimer); // 60 s
}, 500);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "weekaqua-panel")) {
  window.customCards.push({
    type: "weekaqua-panel",
    name: "Week Aqua panel",
    description: "Lighting, the day's schedule, acclimation and spectrum controls for a Week Aqua light.",
    preview: false,
  });
}
