import { html, nothing, type TemplateResult } from "lit";
import { CELSIUS, formatNumber, formatTemperature, formatTemperatureDelta, targetStep } from "../format";
import { actionForHvacMode, actionForPreset, actionForTarget, adjustTarget, hvacModeLabel, sentenceLabel, zoneDemandKind, zoneHvacModes, zonePresets } from "../logic";
import type { ZoneSnapshot } from "../types";
import type { RenderContext } from "./context";

export interface ZoneOptions {
  /**
   * The level of the Zone's heading: 4 inside the Plant card, below its
   * Plant and Zones headings, and 2 when the Zone is a card of its own.
   */
  headingLevel: 2 | 4;
}

function temperature(context: RenderContext, celsius: number | null, label: string, className: string): TemplateResult {
  const unit = context.unit;
  if (celsius === null) {
    return html`<div class=${className} part="metric"><span class="metric-value">--</span><span class="metric-label">${label}<span class="visually-hidden"> unavailable</span></span></div>`;
  }
  return html`<div class=${className} part="metric"><span class="metric-value">${formatTemperature(celsius, unit, context.locale)}</span><span class="metric-unit">${unit}</span><span class="metric-label">${label}</span></div>`;
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
  // An Off thermostat reads as Off rather than as an idle Zone.
  const phase = off && !zone.blocked ? (modeLabel ?? "Off") : sentenceLabel(zone.phase);
  const demandNote = hasDemand ? `${demandKind === "cooling" ? "Cooling" : "Heating"} demand active` : off ? "Thermostat off" : "No demand";
  const headingId = `zone-${zone.id}`;
  const name = controlEntity
    ? html`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${() => context.moreInfo(controlEntity)}>${zone.name}</button>`
    : zone.name;
  const heading = options.headingLevel === 2
    ? html`<h2 class="zone-title" part="zone-title" id=${headingId}>${name}</h2>`
    : html`<h4 class="zone-title" part="zone-title" id=${headingId}>${name}</h4>`;
  return html`<article class="zone" part="zone" data-phase=${zone.phase} data-hvac-mode=${thermostat.hvac_mode ?? "unknown"} data-demand=${String(hasDemand)} data-demand-kind=${demandKind} data-blocked=${String(zone.blocked)} aria-labelledby=${headingId}>
    <div class="row"><div>${heading}<p class="meta zone-owner">${internal ? "Hydronicus thermostat" : `External thermostat · read-only${modeLabel ? ` · ${modeLabel}` : ""}`}</p></div><span class=${`phase${zone.blocked ? " state blocked" : ""}${off ? " off" : ""}`} part="badge">${phase}</span></div>
    <div class="temperature-panel">
      ${temperature(context, thermostat.current_temperature, "Current", "metric")}
      ${temperature(context, thermostat.target_temperature, "Target", "metric target")}
    </div>
    <p class="meta zone-note" dir="auto">${internal ? demandNote : `${demandNote} · ${thermostat.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Zone diagnostics">
      <li part="chip" class="diagnostic-chip" dir="auto">${formatNumber(zone.sensor_status.usable, locale, 0)} sensor${zone.sensor_status.usable === 1 ? "" : "s"} ready</li>
      ${zone.sensor_status.optional_excluded ? html`<li part="chip" class="diagnostic-chip warning" dir="auto">${formatNumber(zone.sensor_status.optional_excluded, locale, 0)} optional excluded</li>` : nothing}
      ${zone.sensor_status.required_blocking ? html`<li part="chip" class="diagnostic-chip danger" dir="auto">${formatNumber(zone.sensor_status.required_blocking, locale, 0)} required blocked</li>` : nothing}
      ${zone.cooling.dew_point === null ? nothing : html`<li part="chip" class="diagnostic-chip" dir="auto">Dew point ${formatTemperature(zone.cooling.dew_point, unit, locale)} ${unit}</li>`}
      ${zone.cooling.condensation_margin === null ? nothing : html`<li part="chip" class="diagnostic-chip ${zone.cooling.blocked ? "danger" : ""}" dir="auto">Margin ${formatTemperatureDelta(zone.cooling.condensation_margin, unit, locale)} ${unit}</li>`}
    </ul>
    ${thermostat.preset && thermostat.preset !== "none" ? html`<p class="meta zone-note" dir="auto">Preset: ${sentenceLabel(thermostat.preset)}</p>` : nothing}
    ${zone.blocked_reason ? html`<p class="meta zone-note" dir="auto">${zone.blocked_reason}</p>` : nothing}
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
