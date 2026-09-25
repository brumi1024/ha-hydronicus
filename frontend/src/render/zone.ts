import { html, nothing, type TemplateResult } from "lit";
import { CELSIUS, formatNumber, formatTemperature, formatTemperatureDelta, targetStep } from "../format";
import { actionForHvacMode, actionForPreset, actionForTarget, adjustTarget, alertLabel, hvacModeLabel, sentenceLabel, zoneAreaLines, zoneBadge, zoneDemandKind, zoneHvacModes, zonePresets } from "../logic";
import type { Alert, ZoneArea, ZoneSnapshot } from "../types";
import type { RenderContext } from "./context";

export interface ZoneOptions {
  /**
   * The level of the Zone's heading: 4 inside the Plant card, below its
   * Plant and Zones headings, and 2 when the Zone is a card of its own.
   */
  headingLevel: 2 | 4;
  /** The alerts about this Zone, most urgent first. */
  alerts: readonly Alert[];
}

function temperature(context: RenderContext, celsius: number | null, label: string, className: string): TemplateResult {
  const unit = context.unit;
  if (celsius === null) {
    return html`<div class=${className} part="metric"><span class="metric-value">--</span><span class="metric-label">${label}<span class="visually-hidden"> unavailable</span></span></div>`;
  }
  return html`<div class=${className} part="metric"><span class="metric-value">${formatTemperature(celsius, unit, context.locale)}</span><span class="metric-unit">${unit}</span><span class="metric-label">${label}</span></div>`;
}

/**
 * One reading of an area line. A dash stands for a reading the controller
 * could not use and for a sensor the area does not name, which screen
 * readers hear apart.
 */
function areaReading(value: string | null, unit: string, sensor: string | null, measurement: string): TemplateResult {
  if (value === null) {
    return html`<span class="area-value">--<span class="visually-hidden"> ${sensor ? `${measurement} unavailable` : `no ${measurement} sensor`}</span></span>`;
  }
  return html`<span class="area-value">${value}<span class="metric-unit">${unit}</span></span>`;
}

/**
 * An area that no longer exists: its name and a Missing tag in place of the
 * readings, since it has no sensor to read or open until it is removed.
 */
function renderMissingArea(area: ZoneArea): TemplateResult {
  return html`<li class="area" part="area" data-missing="true">
    <span class="area-name" dir="auto">${area.name}</span>
    <span class="area-missing" title="This area no longer exists in Home Assistant.">Missing<span class="visually-hidden"> - removed from Home Assistant</span></span>
  </li>`;
}

function renderArea(context: RenderContext, area: ZoneArea, humidity: boolean): TemplateResult {
  if (area.missing) return renderMissingArea(area);
  const { unit, locale } = context;
  // The area's temperature sensor opens, or its humidity sensor when the user sees only that.
  const sensor = area.temperature_entity_id ?? area.humidity_entity_id;
  const name = sensor
    ? html`<button type="button" class="link" aria-haspopup="dialog" title=${`Show ${area.name} sensor details`} @click=${() => context.moreInfo(sensor)}>${area.name}</button>`
    : area.name;
  return html`<li class="area" part="area">
    <span class="area-name" dir="auto">${name}</span>
    ${areaReading(area.temperature === null ? null : formatTemperature(area.temperature, unit, locale), unit, area.temperature_entity_id, "temperature")}
    ${humidity ? areaReading(area.humidity === null ? null : formatNumber(area.humidity, locale, 0), "%", area.humidity_entity_id, "humidity") : nothing}
  </li>`;
}

/** One compact line per area, when the Zone covers several. */
function renderAreas(context: RenderContext, zone: ZoneSnapshot): TemplateResult | typeof nothing {
  const areas = zoneAreaLines(zone);
  if (!areas.length) return nothing;
  const humidity = areas.some((area) => area.humidity !== null || area.humidity_entity_id !== null);
  return html`<ul class="area-list" data-humidity=${String(humidity)} aria-label="Areas">${areas.map((area) => renderArea(context, area, humidity))}</ul>`;
}

/** The alerts about a Zone, as the Plant card's alert section shows them. */
function renderZoneAlerts(zone: ZoneSnapshot, alerts: readonly Alert[]): TemplateResult | typeof nothing {
  if (!alerts.length) return nothing;
  return html`<ul class="zone-alerts" aria-label=${`${zone.name} alerts`}>${alerts.map((alert) => {
    const urgent = alert.severity === "error" || alert.severity === "critical";
    return html`<li class="alert ${urgent ? "error" : ""}" part="notice" data-severity=${alert.severity} dir="auto"><strong>${alertLabel(alert.code)}</strong><span> · ${alert.message}</span></li>`;
  })}</ul>`;
}

function adjust(context: RenderContext, zone: ZoneSnapshot, direction: 1 | -1): void {
  const target = adjustTarget(zone, direction, context.unit);
  if (target !== null) context.call(actionForTarget(zone, target));
}

function chooseHvacMode(context: RenderContext, zone: ZoneSnapshot, mode: string): void {
  if (mode === zone.thermostat.hvac_mode) return;
  context.call(actionForHvacMode(zone, mode));
}

function choosePreset(context: RenderContext, zone: ZoneSnapshot, event: Event): void {
  context.call(actionForPreset(zone, (event.target as HTMLSelectElement).value));
}

/** One Zone tile with its thermostat state, diagnostics, and controls. */
export function renderZone(context: RenderContext, zone: ZoneSnapshot, options: ZoneOptions): TemplateResult {
  const thermostat = zone.thermostat;
  const internal = thermostat.kind === "hydronicus";
  const demandKind = zoneDemandKind(zone);
  const hasDemand = demandKind !== "none";
  const off = thermostat.hvac_mode === "off";
  const { unit, locale, localize } = context;
  const step = formatNumber(targetStep(unit), locale, unit === CELSIUS ? 1 : 0);
  const controlEntity = thermostat.control_entity_id;
  const canAdjust = Boolean(controlEntity) && thermostat.target_temperature !== null;
  // A thermostat without preset support offers only "none"; choosing
  // anything would fail, so the control is hidden.
  const presets = zonePresets(zone);
  const hvacModes = zoneHvacModes(zone);
  const modeLabel = thermostat.hvac_mode ? hvacModeLabel(localize, thermostat.hvac_mode) : null;
  const badge = zoneBadge(zone, localize);
  // A blocked reason that an alert already carries is not repeated as a note.
  const blockedNote = zone.blocked_reason && !options.alerts.some((alert) => alert.message === zone.blocked_reason) ? zone.blocked_reason : null;
  const demandNote = hasDemand ? `${demandKind === "cooling" ? "Cooling" : "Heating"} demand active` : off ? "Thermostat off" : "No demand";
  const headingId = `zone-${zone.id}`;
  const name = controlEntity
    ? html`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${() => context.moreInfo(controlEntity)}>${zone.name}</button>`
    : zone.name;
  const heading = options.headingLevel === 2
    ? html`<h2 class="zone-title" part="zone-title" id=${headingId}>${name}</h2>`
    : html`<h4 class="zone-title" part="zone-title" id=${headingId}>${name}</h4>`;
  return html`<article class="zone" part="zone" data-phase=${zone.phase} data-hvac-mode=${thermostat.hvac_mode ?? "unknown"} data-demand=${String(hasDemand)} data-demand-kind=${demandKind} data-blocked=${String(zone.blocked)} aria-labelledby=${headingId}>
    <div class="row"><div>${heading}<p class="meta zone-owner">${internal ? "Hydronicus thermostat" : `External thermostat · read-only${modeLabel ? ` · ${modeLabel}` : ""}`}</p></div><span class=${`phase${badge.kind === "blocked" ? " state blocked" : ""}${badge.kind === "off" ? " off" : ""}`} part="badge">${badge.label}</span></div>
    <div class="temperature-panel">
      ${temperature(context, thermostat.current_temperature, "Current", "metric")}
      ${temperature(context, thermostat.target_temperature, "Target", "metric target")}
    </div>
    ${renderAreas(context, zone)}
    ${renderZoneAlerts(zone, options.alerts)}
    <p class="meta zone-note" dir="auto">${internal ? demandNote : `${demandNote} · ${thermostat.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Zone diagnostics">
      <li part="chip" class="diagnostic-chip" dir="auto">${formatNumber(zone.sensor_status.usable, locale, 0)} sensor${zone.sensor_status.usable === 1 ? "" : "s"} ready</li>
      ${zone.sensor_status.optional_excluded ? html`<li part="chip" class="diagnostic-chip warning" dir="auto">${formatNumber(zone.sensor_status.optional_excluded, locale, 0)} optional excluded</li>` : nothing}
      ${zone.sensor_status.required_blocking ? html`<li part="chip" class="diagnostic-chip danger" dir="auto">${formatNumber(zone.sensor_status.required_blocking, locale, 0)} required blocked</li>` : nothing}
      ${zone.cooling.dew_point === null ? nothing : html`<li part="chip" class="diagnostic-chip" dir="auto">Dew point ${formatTemperature(zone.cooling.dew_point, unit, locale)} ${unit}</li>`}
      ${zone.cooling.condensation_margin === null ? nothing : html`<li part="chip" class="diagnostic-chip ${zone.cooling.blocked ? "danger" : ""}" dir="auto">Margin ${formatTemperatureDelta(zone.cooling.condensation_margin, unit, locale)} ${unit}</li>`}
    </ul>
    ${thermostat.preset && thermostat.preset !== "none" ? html`<p class="meta zone-note" dir="auto">Preset: ${sentenceLabel(thermostat.preset)}</p>` : nothing}
    ${blockedNote ? html`<p class="meta zone-note" dir="auto">${blockedNote}</p>` : nothing}
    ${zone.coupling_group_ids.length ? html`<p class="meta coupling-note" dir="auto">Coupled delivery - this Zone shares hydraulic equipment.</p>` : nothing}
    ${internal
      ? html`${hvacModes.length
            ? html`<div class="hvac-modes" part="control" role="group" aria-label=${`${zone.name} HVAC mode`}>${hvacModes.map((mode) => html`<button type="button" class="hvac-mode" part="segment" data-mode=${mode} aria-pressed=${String(mode === thermostat.hvac_mode)} ?disabled=${!controlEntity} @click=${() => chooseHvacMode(context, zone, mode)}>${hvacModeLabel(localize, mode)}</button>`)}</div>`
            : nothing}
          <div class="zone-actions" part="controls">
            <button type="button" part="control" dir="ltr" ?disabled=${!canAdjust} aria-label=${`Decrease ${zone.name} target by ${step} ${unit}`} @click=${() => adjust(context, zone, -1)}>−${step}</button>
            <button type="button" part="control" dir="ltr" ?disabled=${!canAdjust} aria-label=${`Increase ${zone.name} target by ${step} ${unit}`} @click=${() => adjust(context, zone, 1)}>+${step}</button>
            ${presets.length
              ? html`<select class="preset" part="control" data-value=${thermostat.preset ?? "none"} aria-label=${`${zone.name} preset`} ?disabled=${!controlEntity} @change=${(event: Event) => choosePreset(context, zone, event)}>${["none", ...presets].map((preset) => html`<option value=${preset}>${sentenceLabel(preset)}</option>`)}</select>`
              : nothing}
          </div>`
      : html`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`;
}
