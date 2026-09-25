import { html, nothing, type TemplateResult } from "lit";
import { formatNumber } from "../format";
import { actionForMode, alertTitle, boundaryClass, boundaryLabel, isFlowingState, nodeKindLabel, operationLabel, prioritizedAlerts, sentenceLabel, sourceSummary, stateLabel, zoneDemandKind } from "../logic";
import type { PlantSnapshot } from "../types";
import type { RenderContext } from "./context";
import { renderRoom } from "./room";

const MODES = ["auto", "idle", "heating", "cooling"];

type Rendered = TemplateResult | typeof nothing;

/**
 * The requested Plant mode, plus the active mode when it differs from an
 * explicit request, for example while a changeover is still pending.
 */
function modeDetail(context: RenderContext, snapshot: PlantSnapshot): string {
  const plant = snapshot.plant;
  const requested = `Mode ${stateLabel(context.localize, "select.requested_mode", plant.requested_mode)}`;
  if (plant.requested_mode === "auto" || plant.requested_mode === plant.active_mode) return requested;
  return `${requested} · now ${stateLabel(context.localize, "sensor.operating_mode", plant.active_mode)}`;
}

/**
 * The Plant name, status, mode control, and execution boundary. The safe
 * shutdown control holds per-card interaction state, so the card renders
 * it and passes it in.
 */
export function renderHeader(context: RenderContext, snapshot: PlantSnapshot, shutdown: TemplateResult): TemplateResult {
  const plant = snapshot.plant;
  const boundary = plant.execution_boundary;
  const modeEntity = snapshot.controls.requested_mode;
  const modes = MODES.includes(plant.requested_mode) ? MODES : [...MODES, plant.requested_mode];
  const source = sourceSummary(snapshot);
  const modeChanged = (event: Event) => context.call(actionForMode(snapshot, (event.target as HTMLSelectElement).value));
  return html`<header class="header" part="header">
      <div class="plant-heading">
        <span class="plant-mark" part="mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow" part="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title" part="title">${modeEntity ? html`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${() => context.moreInfo(modeEntity)}>${plant.name}</button>` : plant.name}</h2>
          <div class="status-line" part="status">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${stateLabel(context.localize, "sensor.controller_status", plant.status)}</span>
            <span class="meta mode-detail">${modeDetail(context, snapshot)}</span>
          </div>
          ${source === null ? nothing : html`<p class="meta source-line" dir="auto"><strong>Source</strong> ${source}</p>`}
          <p class="meta" dir="auto">${plant.controller.mode_explanation || "The controller is starting."}</p>
        </div>
      </div>
      <div class="controls" part="controls">
        <span class="badge ${boundaryClass(boundary)}" part="badge"><span class="visually-hidden">Execution boundary: </span>${boundaryLabel(boundary)}</span>
        <label class="mode-control" part="control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${plant.requested_mode} ?disabled=${!modeEntity} @change=${modeChanged}>
          ${modes.map((mode) => html`<option value=${mode}>${stateLabel(context.localize, "select.requested_mode", mode)}</option>`)}
        </select></label>
        ${shutdown}
      </div>
    </header>`;
}

export function renderBoundary(snapshot: PlantSnapshot): TemplateResult {
  return html`<div class="boundary" part="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${snapshot.plant.execution_boundary.message || `${boundaryLabel(snapshot.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`;
}

export function renderAlerts(context: RenderContext, snapshot: PlantSnapshot): Rendered {
  const alerts = prioritizedAlerts(snapshot);
  if (!alerts.length) return nothing;
  return html`<section part="section" aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${formatNumber(alerts.length, context.locale, 0)}</span></div>${alerts.slice(0, 3).map((alert) => {
    const urgent = alert.severity === "error" || alert.severity === "critical";
    return html`<p class="alert ${urgent ? "error" : ""}" part="notice" data-severity=${alert.severity} dir="auto"><strong>${alertTitle(alert)}</strong><span> · ${alert.message}</span></p>`;
  })}</section>`;
}

export function renderRooms(context: RenderContext, snapshot: PlantSnapshot): TemplateResult {
  return html`<section part="section" aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${formatNumber(snapshot.zones.length, context.locale, 0)} visible</span></div><div class="zone-grid">${snapshot.zones.length ? snapshot.zones.map((zone) => renderRoom(context, zone, { headingLevel: 4 })) : html`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`;
}

export function renderPaths(snapshot: PlantSnapshot): Rendered {
  if (!snapshot.delivery_paths.length) return nothing;
  return html`<section part="section" aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${snapshot.delivery_paths.map((path) => {
    const zone = snapshot.zones.find((candidate) => candidate.id === path.zone_id);
    // A path takes the colour of its own Room's demand, not the Plant's.
    return html`<article class="path" part="path" data-status=${path.status} data-flowing=${String(isFlowingState(path.status))} data-demand-kind=${zoneDemandKind(zone)}>
    <div class="path-head"><div class="path-heading"><strong>${zone?.name ?? path.zone_id}</strong></div><div class="status-line"><span class="state ${path.status}" part="badge">${sentenceLabel(path.status)}</span>${path.coupled ? html`<span class="meta">shares equipment</span>` : nothing}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${path.nodes.map((node, index) => html`<li class="path-step">${index ? html`<span class="flow-link" aria-hidden="true"></span>` : nothing}<span class="node" part="node" data-kind=${node.kind} data-state=${node.state} data-flowing=${String(isFlowingState(node.state))}><span class="node-kind">${nodeKindLabel(node.kind)}</span><span class="node-name">${node.name}</span><span class="node-state">${sentenceLabel(node.state)}</span></span></li>`)}</ol>
    ${path.problem ? html`<p class="meta path-problem" dir="auto">${path.problem}</p>` : nothing}
  </article>`;
  })}</div></section>`;
}

export function renderEquipment(snapshot: PlantSnapshot): Rendered {
  if (!snapshot.actuators.length) return nothing;
  return html`<section part="section" aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${snapshot.actuators.map((actuator) => html`<article class="actuator" part="equipment" data-state=${actuator.state}><div class="row"><strong>${actuator.name}</strong><span class="state actuator-state ${actuator.state}" part="badge">${sentenceLabel(actuator.state)}</span></div><p class="meta" dir="auto">${sentenceLabel(actuator.kind)} · ${actuator.reason ?? "No additional explanation."}</p>${actuator.active_consumers.length ? html`<ul class="consumer-list" aria-label="Loops using this equipment">${actuator.active_consumers.map((consumer) => html`<li class="consumer-chip" part="chip" title=${consumer.id}><strong>${consumer.name}</strong></li>`)}</ul>` : html`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`;
}

export function renderExplanations(snapshot: PlantSnapshot): TemplateResult {
  return html`<section part="section"><details part="disclosure"><summary>Controller explanations</summary>${snapshot.explanations.map((step) => html`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${step.name ?? nodeKindLabel(step.scope)}</strong> · ${step.message}</p></div>`)}</details></section>`;
}

export function renderOperations(context: RenderContext, snapshot: PlantSnapshot): Rendered {
  const operations = Object.values(snapshot.execution.operations).flat();
  if (!operations.length) return nothing;
  return html`<section part="section"><details part="disclosure" open><summary>Latest operation outcomes (${formatNumber(operations.length, context.locale, 0)})</summary>${operations.map((operation) => {
    const result = String(operation.result ?? "unknown");
    return html`<div class="operation" data-result=${result}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${operationLabel(operation)}</strong><br><span class="meta">${String(operation.reason ?? operation.explanation ?? "")}</span></p></div>`;
  })}</details></section>`;
}
