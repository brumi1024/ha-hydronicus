import { ContextConsumer, createContext } from "@lit/context";
import { LitElement, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { configForm, plantDirectory, stubConfig, validateConfig, type ConfigForm } from "./config";
import { CELSIUS, formatNumber, formatTemperature, formatTemperatureDelta, targetStep, temperatureUnit, type TemperatureUnit } from "./format";
import { actionForHvacMode, actionForMode, actionForPreset, actionForSafeShutdown, actionForTarget, adjustTarget, boundaryClass, boundaryLabel, hvacModeLabel, isFlowingState, nodeKindLabel, operationLabel, parseSnapshot, plantVisualState, prioritizedAlerts, sentenceLabel, sourceSummary, stateLabel, zoneHvacModes, zonePresets, type ActionCall } from "./logic";
import { errorMessage, PlantStream, type StreamStatus } from "./stream";
import { cardStyles } from "./styles";
import type {
  CallService,
  FrontendLocale,
  HassApiContextValue,
  HassConfigContextValue,
  HassConnectionContextValue,
  HassInternationalizationContextValue,
  HomeAssistantConnection,
  HomeAssistantLike,
  Localize,
  PlantCardConfig,
  PlantSnapshot,
  ZoneSnapshot,
} from "./types";

const MODES = ["auto", "idle", "heating", "cooling"];
const HOLD_MS = 1_200;

/*
 * Home Assistant frontend context groups (documented since 2026.5). The keys
 * are the context names the frontend providers answer to.
 */
const connectionContext = createContext<HassConnectionContextValue>("hassConnection");
const apiContext = createContext<HassApiContextValue>("hassApi");
const configContext = createContext<HassConfigContextValue>("hassConfig");
const internationalizationContext = createContext<HassInternationalizationContextValue>("hassInternationalization");

type ContextSource = "connection" | "api" | "config" | "i18n";

function retryText(delayMs: number): string {
  return `Retrying in ${Math.round(delayMs / 1000)} s.`;
}

export class HydronicusPlantCard extends LitElement {
  static properties = {
    preview: { type: Boolean },
    _config: { state: true },
    _connection: { state: true },
    _unit: { state: true },
    _locale: { state: true },
    _localize: { state: true },
    _snapshot: { state: true },
    _snapshotError: { state: true },
    _stream: { state: true },
    _actionError: { state: true },
    _holdingShutdown: { state: true },
  };

  static styles = cardStyles;

  declare preview: boolean;
  declare _config: PlantCardConfig | undefined;
  declare _connection: HomeAssistantConnection | undefined;
  declare _unit: TemperatureUnit;
  declare _locale: FrontendLocale | undefined;
  declare _localize: Localize | undefined;
  declare _snapshot: PlantSnapshot | null;
  declare _snapshotError: string | null;
  declare _stream: StreamStatus;
  declare _actionError: string | null;
  declare _holdingShutdown: boolean;

  private _hass: HomeAssistantLike | undefined;
  private _callService: CallService | undefined;
  private readonly _fromContext = new Set<ContextSource>();
  private readonly _plantStream: PlantStream;
  private _holdTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    super();
    this.preview = false;
    this._config = undefined;
    this._connection = undefined;
    this._unit = CELSIUS;
    this._locale = undefined;
    this._localize = undefined;
    this._snapshot = null;
    this._snapshotError = null;
    this._stream = { kind: "idle" };
    this._actionError = null;
    this._holdingShutdown = false;
    this._plantStream = new PlantStream({
      onStatus: (status) => this._streamStatusChanged(status),
      onSnapshot: (snapshot) => this._snapshotReceived(snapshot),
    });
    new ContextConsumer(this, {
      context: connectionContext,
      subscribe: true,
      callback: (value) => {
        this._fromContext.add("connection");
        this._connection = value?.connection;
      },
    });
    new ContextConsumer(this, {
      context: apiContext,
      subscribe: true,
      callback: (value) => {
        this._fromContext.add("api");
        this._callService = value?.callService;
      },
    });
    new ContextConsumer(this, {
      context: configContext,
      subscribe: true,
      callback: (value) => {
        this._fromContext.add("config");
        this._unit = temperatureUnit(value?.config?.unit_system);
      },
    });
    new ContextConsumer(this, {
      context: internationalizationContext,
      subscribe: true,
      callback: (value) => {
        this._fromContext.add("i18n");
        this._locale = value?.locale ?? (value?.language ? { language: value.language } : undefined);
        this._localize = value?.localize;
      },
    });
  }

  /**
   * Home Assistant still sets `hass` on every card. The card prefers the
   * frontend contexts and uses `hass` only for values no context provided.
   * Only the parts the card reads are stored as reactive state, so a state
   * change elsewhere in Home Assistant does not re-render the card.
   */
  set hass(hass: HomeAssistantLike | undefined) {
    this._hass = hass;
    if (!this._fromContext.has("connection")) this._connection = hass?.connection;
    if (!this._fromContext.has("api")) this._callService = hass ? (...args) => hass.callService(...args) : undefined;
    if (!this._fromContext.has("config")) this._unit = temperatureUnit(hass?.config?.unit_system);
    if (!this._fromContext.has("i18n")) {
      this._locale = hass?.locale ?? (hass?.language ? { language: hass.language } : undefined);
      this._localize = hass?.localize;
    }
  }

  get hass(): HomeAssistantLike | undefined {
    return this._hass;
  }

  static async getConfigForm(): Promise<ConfigForm> {
    return configForm();
  }

  static async getStubConfig(hass?: HomeAssistantLike): Promise<Omit<PlantCardConfig, "type">> {
    return stubConfig(hass);
  }

  setConfig(config: PlantCardConfig): void {
    const next = validateConfig(config);
    if (next.plant !== this._config?.plant) {
      this._snapshot = null;
      this._snapshotError = null;
      this._actionError = null;
    }
    this._config = next;
  }

  /** Masonry height in 50 px units, estimated from the rendered sections. */
  getCardSize(): number {
    const snapshot = this._snapshot;
    if (!snapshot) return 4;
    let size = 4;
    const alerts = Math.min(snapshot.alerts.length, 3);
    if (alerts) size += 1 + alerts;
    size += 1 + Math.max(1, snapshot.zones.length) * 5;
    if (snapshot.delivery_paths.length) size += 1 + snapshot.delivery_paths.length * 3;
    if (snapshot.actuators.length) size += 1 + snapshot.actuators.length * 2;
    size += 1;
    const operations = Object.values(snapshot.execution.operations).flat().length;
    if (operations) size += 1 + operations;
    return size;
  }

  getGridOptions() {
    // No rows: the Sections grid then sizes the card to its content height.
    return { columns: 12, min_columns: 6 };
  }

  connectedCallback(): void {
    super.connectedCallback();
    // Reattaching needs a new stream; updated() connects it.
    this.requestUpdate();
  }

  disconnectedCallback(): void {
    this._plantStream.disconnect();
    this._clearHold();
    super.disconnectedCallback();
  }

  protected updated(changed: PropertyValues): void {
    super.updated(changed);
    this._syncSelectValues();
    if (!this.isConnected) return;
    const plant = this._config?.plant || undefined;
    this._plantStream.connect(this._connection, plant);
    if (this._connection && (changed.has("_connection") || this.preview)) void plantDirectory.load(this._connection);
  }

  /**
   * Show each dropdown's real value. A `.value` binding on the select is
   * committed before its options exist, and a failed action must also revert
   * the user's pick, so the value is applied after every render instead.
   */
  private _syncSelectValues(): void {
    for (const select of this.renderRoot.querySelectorAll<HTMLSelectElement>("select[data-value]")) {
      const value = select.dataset.value ?? "";
      if (select.value !== value) select.value = value;
    }
  }

  private _streamStatusChanged(status: StreamStatus): void {
    this._stream = status;
    if (["idle", "unavailable", "not_found", "unauthorized"].includes(status.kind)) {
      // Controls must never act on a Plant the backend no longer serves.
      this._snapshot = null;
      this._clearHold();
    }
  }

  private _snapshotReceived(candidate: unknown): void {
    try {
      this._snapshot = parseSnapshot(candidate);
      this._snapshotError = null;
    } catch (error) {
      this._snapshot = null;
      this._snapshotError = errorMessage(error, "Unsupported Hydronicus snapshot.");
    }
  }

  render(): TemplateResult {
    const config = this._config;
    if (!config || !config.plant) {
      return this._renderState("Hydronicus Plant", "Select a Hydronicus Plant in the card editor.", "status");
    }
    if (this._snapshotError) {
      return this._renderState("Card update needed", this._snapshotError, "alert", "Reload the browser after upgrading Hydronicus so the card and the integration match.");
    }
    const snapshot = this._snapshot;
    const stream = this._stream;
    if (!snapshot) {
      switch (stream.kind) {
        case "not_found":
          return this._renderState("Plant not found", "This Hydronicus Plant was not found. Choose another Plant in the card editor.", "alert");
        case "unauthorized":
          return this._renderState("No access", "You do not have access to this Hydronicus Plant.", "alert");
        case "unavailable":
          return this._renderState("Plant unavailable", "The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.", "status");
        case "retrying":
          return this._renderState("Connection needs attention", stream.message, "alert", retryText(stream.delayMs));
        default:
          return this._renderLoading(stream.kind === "reconnecting");
      }
    }
    return html`<ha-card class=${config.density ?? "comfortable"} data-visual=${plantVisualState(snapshot)}>
      ${this._renderHeader(snapshot)}
      ${this._renderStreamNotice(stream)}
      ${this._actionError ? html`<div class="action-error" role="alert"><span dir="auto">${this._actionError}</span><button type="button" @click=${this._dismissActionError}>Dismiss</button></div>` : nothing}
      <div class="boundary" role="status">
        <span class="boundary-orb" aria-hidden="true"></span>
        <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${snapshot.plant.execution_boundary.message || `${boundaryLabel(snapshot.plant.execution_boundary)} execution boundary is active.`}</strong></p>
      </div>
      ${this._renderAlerts(snapshot)}
      ${this._renderZones(snapshot)}
      ${this._renderPaths(snapshot)}
      ${this._renderActuators(snapshot)}
      ${this._renderExplanations(snapshot)}
      ${this._renderOperations(snapshot)}
    </ha-card>`;
  }

  private _renderState(title: string, message: string, role: "status" | "alert", detail?: string): TemplateResult {
    return html`<ha-card class="state-card" data-visual=${role === "alert" ? "attention" : "idle"}>
      <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">Hydronicus Plant</p><h2>${title}</h2></div></div>
      <p class=${role === "alert" ? "notice error" : "notice"} role=${role} dir="auto">${message}</p>
      ${detail ? html`<p class="meta" dir="auto">${detail}</p>` : nothing}
    </ha-card>`;
  }

  private _renderLoading(reconnecting: boolean): TemplateResult {
    return html`<ha-card class="loading-card" role="status" aria-busy="true">
      <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
      <div class="loading-panel"></div>
      <p class="muted">${reconnecting ? "Reconnecting to Home Assistant…" : "Loading Plant snapshot…"}</p>
    </ha-card>`;
  }

  private _renderStreamNotice(stream: StreamStatus) {
    if (stream.kind === "reconnecting") {
      return html`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`;
    }
    if (stream.kind === "retrying") {
      return html`<p class="notice" role="status" dir="auto">${stream.message} ${retryText(stream.delayMs)} The values below may be out of date.</p>`;
    }
    return nothing;
  }

  private _renderHeader(snapshot: PlantSnapshot) {
    const plant = snapshot.plant;
    const boundary = plant.execution_boundary;
    const modeEntity = snapshot.controls.requested_mode;
    const modes = MODES.includes(plant.requested_mode) ? MODES : [...MODES, plant.requested_mode];
    const source = sourceSummary(snapshot);
    return html`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${modeEntity ? html`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${() => this._moreInfo(modeEntity)}>${plant.name}</button>` : plant.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${stateLabel(this._localize, "sensor.controller_status", plant.status)}</span>
            <span class="meta mode-detail">${this._modeDetail(snapshot)}</span>
          </div>
          ${source === null ? nothing : html`<p class="meta source-line" dir="auto"><strong>Source</strong> ${source}</p>`}
          <p class="meta" dir="auto">${plant.controller.mode_explanation || "The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${boundaryClass(boundary)}"><span class="visually-hidden">Execution boundary: </span>${boundaryLabel(boundary)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${plant.requested_mode} ?disabled=${!modeEntity} @change=${this._modeChanged}>
          ${modes.map((mode) => html`<option value=${mode}>${stateLabel(this._localize, "select.requested_mode", mode)}</option>`)}
        </select></label>
        ${this._renderShutdown(snapshot)}
      </div>
    </header>`;
  }

  /**
   * The requested Plant mode, plus the active mode when it differs from an
   * explicit request, for example while a changeover is still pending.
   */
  private _modeDetail(snapshot: PlantSnapshot): string {
    const plant = snapshot.plant;
    const requested = `Mode ${stateLabel(this._localize, "select.requested_mode", plant.requested_mode)}`;
    if (plant.requested_mode === "auto" || plant.requested_mode === plant.active_mode) return requested;
    return `${requested} · now ${stateLabel(this._localize, "sensor.operating_mode", plant.active_mode)}`;
  }

  private _renderShutdown(snapshot: PlantSnapshot) {
    const disabled = !snapshot.controls.safe_shutdown;
    // In Dry run nothing executes, so the action stays available but quiet.
    const quiet = snapshot.plant.execution_boundary.dry_run;
    return html`<button type="button" class=${`shutdown${quiet ? " quiet" : ""}${this._holdingShutdown ? " is-holding" : ""}`} ?disabled=${disabled} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown ? html`<span class="hold-progress" role="status">Keep holding…</span>` : nothing}`;
  }

  private _renderAlerts(snapshot: PlantSnapshot) {
    const alerts = prioritizedAlerts(snapshot);
    if (!alerts.length) return nothing;
    return html`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${formatNumber(alerts.length, this._locale, 0)}</span></div>${alerts.slice(0, 3).map((alert) => {
      const urgent = alert.severity === "error" || alert.severity === "critical";
      return html`<p class="alert ${urgent ? "error" : ""}" data-severity=${alert.severity} dir="auto"><strong>${sentenceLabel(alert.code)}</strong><span> · ${alert.message}</span></p>`;
    })}</section>`;
  }

  private _renderZones(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${formatNumber(snapshot.zones.length, this._locale, 0)} visible</span></div><div class="zone-grid">${snapshot.zones.length ? snapshot.zones.map((zone) => this._renderZone(zone)) : html`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`;
  }

  private _temperature(celsius: number | null, label: string, className: string) {
    const unit = this._unit;
    if (celsius === null) {
      return html`<div class=${className}><span class="metric-value">--</span><span class="metric-label">${label}<span class="visually-hidden"> unavailable</span></span></div>`;
    }
    return html`<div class=${className}><span class="metric-value">${formatTemperature(celsius, unit, this._locale)}</span><span class="metric-unit">${unit}</span><span class="metric-label">${label}</span></div>`;
  }

  private _renderZone(zone: ZoneSnapshot) {
    const thermostat = zone.thermostat;
    const internal = thermostat.kind === "hydronicus";
    const demandKind = zone.cooling.demand ? "cooling" : zone.demand ? "heating" : "none";
    const hasDemand = demandKind !== "none";
    const off = thermostat.hvac_mode === "off";
    const unit = this._unit;
    const step = formatNumber(targetStep(unit), this._locale, unit === CELSIUS ? 1 : 0);
    const controlEntity = thermostat.control_entity_id;
    const canAdjust = Boolean(controlEntity) && thermostat.target_temperature !== null;
    // A thermostat without preset support offers only "none"; choosing
    // anything would fail, so the control is hidden.
    const presets = zonePresets(zone);
    const hvacModes = zoneHvacModes(zone);
    const modeLabel = thermostat.hvac_mode ? hvacModeLabel(this._localize, thermostat.hvac_mode) : null;
    // An Off thermostat reads as Off rather than as an idle Room.
    const phase = off && !zone.blocked ? (modeLabel ?? "Off") : sentenceLabel(zone.phase);
    const demandNote = hasDemand ? `${demandKind === "cooling" ? "Cooling" : "Heating"} demand active` : off ? "Thermostat off" : "No demand";
    return html`<article class="zone" data-phase=${zone.phase} data-hvac-mode=${thermostat.hvac_mode ?? "unknown"} data-demand=${String(hasDemand)} data-demand-kind=${demandKind} data-blocked=${String(zone.blocked)} aria-labelledby=${`zone-${zone.id}`}>
      <div class="row"><div><h4 class="zone-title" id=${`zone-${zone.id}`}>${controlEntity ? html`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${() => this._moreInfo(controlEntity)}>${zone.name}</button>` : zone.name}</h4><p class="meta zone-owner">${internal ? "Hydronicus thermostat" : `External thermostat · read-only${modeLabel ? ` · ${modeLabel}` : ""}`}</p></div><span class=${`phase${zone.blocked ? " state blocked" : ""}${off ? " off" : ""}`}>${phase}</span></div>
      <div class="temperature-panel">
        ${this._temperature(thermostat.current_temperature, "Current", "metric")}
        ${this._temperature(thermostat.target_temperature, "Target", "metric target")}
      </div>
      <p class="meta zone-note" dir="auto">${internal ? demandNote : `${demandNote} · ${thermostat.explanation}`}</p>
      <ul class="diagnostic-list" aria-label="Room diagnostics">
        <li class="diagnostic-chip" dir="auto">${formatNumber(zone.sensor_status.usable, this._locale, 0)} sensor${zone.sensor_status.usable === 1 ? "" : "s"} ready</li>
        ${zone.sensor_status.optional_excluded ? html`<li class="diagnostic-chip warning" dir="auto">${formatNumber(zone.sensor_status.optional_excluded, this._locale, 0)} optional excluded</li>` : nothing}
        ${zone.sensor_status.required_blocking ? html`<li class="diagnostic-chip danger" dir="auto">${formatNumber(zone.sensor_status.required_blocking, this._locale, 0)} required blocked</li>` : nothing}
        ${zone.cooling.dew_point === null ? nothing : html`<li class="diagnostic-chip" dir="auto">Dew point ${formatTemperature(zone.cooling.dew_point, unit, this._locale)} ${unit}</li>`}
        ${zone.cooling.condensation_margin === null ? nothing : html`<li class="diagnostic-chip ${zone.cooling.blocked ? "danger" : ""}" dir="auto">Margin ${formatTemperatureDelta(zone.cooling.condensation_margin, unit, this._locale)} ${unit}</li>`}
      </ul>
      ${thermostat.preset && thermostat.preset !== "none" ? html`<p class="meta zone-note" dir="auto">Preset: ${sentenceLabel(thermostat.preset)}</p>` : nothing}
      ${zone.blocked_reason ? html`<p class="meta zone-note" dir="auto">${zone.blocked_reason}</p>` : nothing}
      ${zone.coupling_group_ids.length ? html`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>` : nothing}
      ${internal
        ? html`${hvacModes.length
              ? html`<div class="hvac-modes" role="group" aria-label=${`${zone.name} HVAC mode`}>${hvacModes.map((mode) => html`<button type="button" class="hvac-mode" data-mode=${mode} aria-pressed=${String(mode === thermostat.hvac_mode)} ?disabled=${!controlEntity} @click=${() => this._hvacModeChosen(zone, mode)}>${hvacModeLabel(this._localize, mode)}</button>`)}</div>`
              : nothing}
            <div class="zone-actions">
              <button type="button" dir="ltr" ?disabled=${!canAdjust} aria-label=${`Decrease ${zone.name} target by ${step} ${unit}`} @click=${() => this._adjustZone(zone, -1)}>−${step}</button>
              <button type="button" dir="ltr" ?disabled=${!canAdjust} aria-label=${`Increase ${zone.name} target by ${step} ${unit}`} @click=${() => this._adjustZone(zone, 1)}>+${step}</button>
              ${presets.length
                ? html`<select class="preset" data-value=${thermostat.preset ?? "none"} aria-label=${`${zone.name} preset`} ?disabled=${!controlEntity} @change=${(event: Event) => this._presetChanged(zone, event)}>${["none", ...presets].map((preset) => html`<option value=${preset}>${sentenceLabel(preset)}</option>`)}</select>`
                : nothing}
            </div>`
        : html`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
    </article>`;
  }

  private _renderPaths(snapshot: PlantSnapshot) {
    if (!snapshot.delivery_paths.length) return nothing;
    return html`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${snapshot.delivery_paths.map((path) => html`<article class="path" data-status=${path.status} data-flowing=${String(isFlowingState(path.status))}>
      <div class="path-head"><div class="path-heading"><strong>${snapshot.zones.find((zone) => zone.id === path.zone_id)?.name ?? path.zone_id}</strong></div><div class="status-line"><span class="state ${path.status}">${sentenceLabel(path.status)}</span>${path.coupled ? html`<span class="meta">shares equipment</span>` : nothing}</div></div>
      <ol class="path-track" aria-label="Ordered hydraulic delivery path">${path.nodes.map((node, index) => html`<li class="path-step">${index ? html`<span class="flow-link" aria-hidden="true"></span>` : nothing}<span class="node" data-kind=${node.kind} data-state=${node.state} data-flowing=${String(isFlowingState(node.state))}><span class="node-kind">${nodeKindLabel(node.kind)}</span><span class="node-name">${node.name}</span><span class="node-state">${sentenceLabel(node.state)}</span></span></li>`)}</ol>
      ${path.problem ? html`<p class="meta path-problem" dir="auto">${path.problem}</p>` : nothing}
    </article>`)}</div></section>`;
  }

  private _renderActuators(snapshot: PlantSnapshot) {
    if (!snapshot.actuators.length) return nothing;
    return html`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${snapshot.actuators.map((actuator) => html`<article class="actuator" data-state=${actuator.state}><div class="row"><strong>${actuator.name}</strong><span class="state actuator-state ${actuator.state}">${sentenceLabel(actuator.state)}</span></div><p class="meta" dir="auto">${sentenceLabel(actuator.kind)} · ${actuator.reason ?? "No additional explanation."}</p>${actuator.active_consumers.length ? html`<ul class="consumer-list" aria-label="Loops using this equipment">${actuator.active_consumers.map((consumer) => html`<li class="consumer-chip" title=${consumer.id}><strong>${consumer.name}</strong></li>`)}</ul>` : html`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`;
  }

  private _renderExplanations(snapshot: PlantSnapshot) {
    return html`<section><details><summary>Controller explanations</summary>${snapshot.explanations.map((step) => html`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${nodeKindLabel(step.scope)}</strong> · ${step.message}</p></div>`)}</details></section>`;
  }

  private _renderOperations(snapshot: PlantSnapshot) {
    const operations = Object.values(snapshot.execution.operations).flat();
    if (!operations.length) return nothing;
    return html`<section><details open><summary>Latest operation outcomes (${formatNumber(operations.length, this._locale, 0)})</summary>${operations.map((operation) => {
      const result = String(operation.result ?? "unknown");
      return html`<div class="operation" data-result=${result}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${operationLabel(operation)}</strong><br><span class="meta">${String(operation.reason ?? operation.explanation ?? "")}</span></p></div>`;
    })}</details></section>`;
  }

  private _moreInfo(entityId: string): void {
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }

  private _call(action: ActionCall | null): void {
    const callService = this._callService;
    if (!action || !callService) return;
    // The card shows a failure inline, so Home Assistant must not also toast it.
    callService(action.domain, action.service, action.data, undefined, false).then(
      () => {
        this._actionError = null;
      },
      (error: unknown) => {
        // Keep the snapshot: the Plant is still valid, only this action failed.
        this._actionError = errorMessage(error, "The Home Assistant action failed.");
        // Re-render so the dropdowns return to the Plant's real values.
        this.requestUpdate();
      },
    );
  }

  private _dismissActionError = (): void => {
    this._actionError = null;
  };

  private _modeChanged = (event: Event): void => {
    if (!this._snapshot) return;
    this._call(actionForMode(this._snapshot, (event.target as HTMLSelectElement).value));
  };

  private _adjustZone(zone: ZoneSnapshot, direction: 1 | -1): void {
    const target = adjustTarget(zone, direction, this._unit);
    if (target !== null) this._call(actionForTarget(zone, target));
  }

  private _hvacModeChosen(zone: ZoneSnapshot, mode: string): void {
    if (mode === zone.thermostat.hvac_mode) return;
    this._call(actionForHvacMode(zone, mode));
  }

  private _presetChanged(zone: ZoneSnapshot, event: Event): void {
    this._call(actionForPreset(zone, (event.target as HTMLSelectElement).value));
  }

  private _startHold(): void {
    if (!this._snapshot || this._holdTimer !== null) return;
    this._holdingShutdown = true;
    this._holdTimer = setTimeout(() => {
      this._holdTimer = null;
      this._holdingShutdown = false;
      if (this._snapshot) this._call(actionForSafeShutdown(this._snapshot));
    }, HOLD_MS);
  }

  private _clearHold = (): void => {
    if (this._holdTimer !== null) clearTimeout(this._holdTimer);
    this._holdTimer = null;
    this._holdingShutdown = false;
  };

  private _pointerHoldStart = (event: PointerEvent): void => {
    if (event.button !== undefined && event.button > 0) return;
    this._startHold();
  };

  private _keyHoldStart = (event: KeyboardEvent): void => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (!event.repeat) this._startHold();
  };

  private _keyHoldEnd = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") this._clearHold();
  };

  private _preventContextMenu = (event: Event): void => {
    event.preventDefault();
  };
}
