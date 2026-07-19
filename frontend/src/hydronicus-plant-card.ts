import { LitElement, css, html, nothing } from "lit";
import { actionForMode, actionForPreset, actionForSafeShutdown, actionForTarget, adjustTarget, operationLabel, parseSnapshot, phaseLabel, prioritizedAlerts } from "./logic";
import type { HomeAssistantLike, PlantCardConfig, PlantSnapshot, ZoneSnapshot } from "./types";

const MODES = ["auto", "idle", "heating", "cooling"];

class HydronicusPlantCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _snapshot: { state: true },
    _error: { state: true },
    _reconnecting: { state: true },
    _holdingShutdown: { state: true },
  };

  static styles = css`
    :host {
      display: block;
      color: var(--primary-text-color, #1c1c1c);
      --hydronicus-border: var(--divider-color, rgba(127, 127, 127, 0.28));
      --hydronicus-muted: var(--secondary-text-color, #5f6368);
      --hydronicus-surface: var(--ha-card-background, var(--card-background-color, #fff));
      --hydronicus-danger: var(--error-color, #ba1a1a);
      --hydronicus-warning: var(--warning-color, #8a5a00);
      --hydronicus-accent: var(--primary-color, #03a9f4);
    }

    .card {
      box-sizing: border-box;
      container-type: inline-size;
      overflow: hidden;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--hydronicus-surface);
      box-shadow: var(--ha-card-box-shadow, none);
      padding: 1rem;
    }

    .card.compact { padding: 0.7rem; }
    .header, .row, .path-head, .action-row, .section-head { display: flex; align-items: center; gap: 0.65rem; }
    .header { justify-content: space-between; align-items: flex-start; gap: 1rem; }
    .header-copy { min-width: 0; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 1.15rem; overflow-wrap: anywhere; }
    h2 { font-size: 0.96rem; }
    h3 { font-size: 0.88rem; }
    .muted, .meta { color: var(--hydronicus-muted); font-size: 0.82rem; }
    .status { margin-top: 0.3rem; font-size: 0.92rem; }
    .badge, .phase, .state { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.22rem 0.5rem; font-size: 0.72rem; white-space: nowrap; }
    .badge { font-weight: 700; background: color-mix(in srgb, var(--hydronicus-warning) 15%, transparent); }
    .badge.dry-run, .state.proposed { color: var(--hydronicus-warning); }
    .badge.mixed, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
    .badge.active, .state.active, .state.ready { color: var(--success-color, #287d34); }
    .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.45rem; }
    button, select { min-height: 2.25rem; border: 1px solid var(--hydronicus-border); border-radius: 0.55rem; background: var(--ha-card-background, transparent); color: inherit; font: inherit; padding: 0.35rem 0.55rem; }
    button { cursor: pointer; }
    button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
    button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--hydronicus-accent); outline-offset: 2px; }
    .shutdown { color: var(--hydronicus-danger); }
    .hold-progress { font-size: 0.7rem; color: var(--hydronicus-danger); }
    .alert, .error, .boundary { margin-top: 0.8rem; border: 1px solid var(--hydronicus-border); border-left: 4px solid var(--hydronicus-warning); border-radius: 0.45rem; padding: 0.55rem 0.65rem; }
    .alert.error, .error { border-left-color: var(--hydronicus-danger); }
    .boundary { border-left-color: var(--hydronicus-accent); }
    section { margin-top: 1rem; }
    .section-head { justify-content: space-between; margin-bottom: 0.45rem; }
    .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(235px, 1fr)); gap: 0.6rem; }
    .zone, .path, .actuator, details { border: 1px solid var(--hydronicus-border); border-radius: 0.65rem; }
    .zone, .path, .actuator { padding: 0.65rem; }
    .row { justify-content: space-between; align-items: baseline; }
    .zone-title { min-width: 0; overflow-wrap: anywhere; }
    .temperature { font-size: 1.35rem; font-weight: 700; }
    .target { font-variant-numeric: tabular-nums; }
    .zone-actions { display: flex; gap: 0.35rem; margin-top: 0.55rem; }
    .zone-actions button { min-width: 2.65rem; }
    .preset { flex: 1; min-width: 0; }
    .path-list, .actuator-list { display: grid; gap: 0.45rem; }
    .path-nodes { display: flex; flex-wrap: wrap; align-items: center; gap: 0.3rem; margin-top: 0.45rem; }
    .node { border: 1px solid var(--hydronicus-border); border-radius: 0.4rem; padding: 0.28rem 0.4rem; font-size: 0.75rem; max-width: 100%; overflow-wrap: anywhere; }
    .arrow { color: var(--hydronicus-muted); }
    details { padding: 0.55rem 0.65rem; }
    details + details { margin-top: 0.45rem; }
    summary { cursor: pointer; font-weight: 600; }
    .operation { padding: 0.35rem 0; border-top: 1px solid var(--hydronicus-border); font-size: 0.82rem; }
    .operation:first-child { border-top: 0; }
    .consumer { color: var(--hydronicus-muted); font-size: 0.75rem; }
    @container (max-width: 560px) {
      .header { display: block; }
      .controls { justify-content: flex-start; margin-top: 0.7rem; }
      .zone-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .card { padding: 0.75rem; }
      .controls { justify-content: flex-start; }
    }
  `;

  hass?: HomeAssistantLike;
  _config?: PlantCardConfig;
  _snapshot: PlantSnapshot | null = null;
  _error: string | null = null;
  _reconnecting = false;
  _holdingShutdown = false;
  private _unsubscribe: (() => void) | null = null;
  private _holdTimer: number | null = null;
  private _subscriptionGeneration = 0;

  setConfig(config: PlantCardConfig): void {
    if (!config || config.type !== "custom:hydronicus-plant-card" || typeof config.plant !== "string" || !config.plant) {
      throw new Error("Hydronicus Plant card requires one Plant UUID.");
    }
    if (config.density && !["comfortable", "compact"].includes(config.density)) {
      throw new Error("Hydronicus Plant card density must be comfortable or compact.");
    }
    this._config = { ...config, density: config.density ?? "comfortable" };
    this._subscribe();
  }

  getCardSize(): number { return 7; }

  getGridOptions() {
    return { rows: 6, columns: 6, min_rows: 4, min_columns: 3, max_columns: 12 };
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._subscribe();
  }

  disconnectedCallback(): void {
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._subscriptionGeneration += 1;
    this._clearHold();
    super.disconnectedCallback();
  }

  protected updated(): void { this._subscribe(); }

  render() {
    const snapshot = this._snapshot;
    const config = this._config;
    if (!config) return html`<div class="card" role="status">Configure one Hydronicus Plant.</div>`;
    if (this._error) return html`<div class="card" role="alert"><h1>Hydronicus Plant</h1><p class="error">${this._error}</p><p class="meta">Check the Dashboard Resource and wait for the connection to recover.</p></div>`;
    if (!snapshot) return html`<div class="card" role="status" aria-busy="true"><h1>Hydronicus Plant</h1><p class="muted">${this._reconnecting ? "Reconnecting to Hydronicus…" : "Loading Plant snapshot…"}</p></div>`;
    return html`<article class="card ${config.density}" aria-label=${snapshot.plant.name}>
      ${this._renderHeader(snapshot)}
      <div class="boundary" role="status"><strong>${snapshot.plant.execution_boundary.message}</strong></div>
      ${this._renderAlerts(snapshot)}
      ${this._renderZones(snapshot)}
      ${this._renderPaths(snapshot)}
      ${this._renderActuators(snapshot)}
      ${this._renderExplanations(snapshot)}
      ${this._renderOperations(snapshot)}
    </article>`;
  }

  private _renderHeader(snapshot: PlantSnapshot) {
    const boundary = snapshot.plant.execution_boundary;
    return html`<header class="header">
      <div class="header-copy">
        <h1>${snapshot.plant.name}</h1>
        <p class="status">${phaseLabel(snapshot.plant.status)} · requested ${phaseLabel(snapshot.plant.requested_mode)} · active ${phaseLabel(snapshot.plant.active_mode)}</p>
        <p class="meta">${snapshot.plant.controller.mode_explanation ?? "The controller is starting."}</p>
        <p class="meta">Source: ${snapshot.plant.source.active_name ?? "none active"} · recommended ${snapshot.plant.source.recommended_name ?? "none"}</p>
      </div>
      <div class="controls">
        <span class="badge ${boundary.mode}" aria-label="Execution boundary">${phaseLabel(boundary.mode)}</span>
        <label>Mode <select aria-label="Requested Plant mode" .value=${snapshot.plant.requested_mode} @change=${this._modeChanged}>
          ${MODES.map((mode) => html`<option value=${mode}>${phaseLabel(mode)}</option>`)}
        </select></label>
        ${this._renderShutdown(snapshot)}
      </div>
    </header>`;
  }

  private _renderShutdown(snapshot: PlantSnapshot) {
    const disabled = !snapshot.controls.safe_shutdown;
    return html`<button class="shutdown" ?disabled=${disabled} aria-label="Hold to confirm Hydronicus Safe shutdown" @pointerdown=${this._startHold} @pointerup=${this._clearHold} @pointercancel=${this._clearHold} @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd}>Safe shutdown</button>${this._holdingShutdown ? html`<span class="hold-progress" role="status">Keep holding…</span>` : nothing}`;
  }

  private _renderAlerts(snapshot: PlantSnapshot) {
    const alerts = prioritizedAlerts(snapshot);
    if (!alerts.length) return nothing;
    return html`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><h2 id="hydronicus-alerts">Alerts</h2><span class="meta">${alerts.length}</span></div>${alerts.slice(0, 3).map((alert) => html`<div class="alert ${alert.severity === "error" || alert.severity === "critical" ? "error" : ""}" role=${alert.severity === "error" ? "alert" : "status"}><strong>${phaseLabel(alert.code)}</strong><span> · ${alert.message}</span></div>`)}</section>`;
  }

  private _renderZones(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-zones"><div class="section-head"><h2 id="hydronicus-zones">Zones</h2><span class="meta">${snapshot.zones.length}</span></div><div class="zone-grid">${snapshot.zones.length ? snapshot.zones.map((zone) => this._renderZone(snapshot, zone)) : html`<p class="muted">No visible Zones are configured for this Plant.</p>`}</div></section>`;
  }

  private _renderZone(_snapshot: PlantSnapshot, zone: ZoneSnapshot) {
    const current = zone.current_temperature === null ? "n/a" : `${zone.current_temperature.toFixed(1)} °C`;
    return html`<article class="zone" aria-label=${`${zone.name} Zone`}>
      <div class="row"><h3 class="zone-title">${zone.name}</h3><span class="phase ${zone.blocked ? "state blocked" : ""}">${phaseLabel(zone.phase)}</span></div>
      <div class="row"><span class="temperature">${current}</span><span class="target">Target ${zone.target_temperature.toFixed(1)} °C</span></div>
      <p class="meta">Preset: ${phaseLabel(zone.preset)} · ${zone.demand ? "demand active" : "satisfied"}</p>
      ${zone.blocked_reason ? html`<p class="meta" role="status">${zone.blocked_reason}</p>` : nothing}
      ${zone.coupling_group_ids.length ? html`<p class="meta">Coupled delivery - this Zone shares hydraulic equipment.</p>` : nothing}
      <div class="zone-actions"><button ?disabled=${!zone.climate_entity_id} aria-label=${`Decrease ${zone.name} target by half a degree`} @click=${() => this._adjustZone(zone, -0.5)}>−0.5</button><button ?disabled=${!zone.climate_entity_id} aria-label=${`Increase ${zone.name} target by half a degree`} @click=${() => this._adjustZone(zone, 0.5)}>+0.5</button><select class="preset" aria-label=${`${zone.name} preset`} .value=${zone.preset} ?disabled=${!zone.climate_entity_id} @change=${(event: Event) => this._presetChanged(zone, event)}>${["none", ...zone.preset_modes].map((preset) => html`<option value=${preset}>${phaseLabel(preset)}</option>`)}</select></div>
    </article>`;
  }

  private _renderPaths(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-paths"><div class="section-head"><h2 id="hydronicus-paths">Delivery paths</h2><span class="meta">Zone → Circuit → Valve → Pump → Source</span></div><div class="path-list">${snapshot.delivery_paths.map((path) => html`<article class="path"><div class="path-head"><strong>${snapshot.zones.find((zone) => zone.id === path.zone_id)?.name ?? path.zone_id}</strong><span class="state ${path.status}">${phaseLabel(path.status)}</span>${path.coupled ? html`<span class="meta">coupled</span>` : nothing}</div><div class="path-nodes">${path.nodes.map((node, index) => html`${index ? html`<span class="arrow" aria-hidden="true">→</span>` : nothing}<span class="node" title=${node.name}>${node.name}<br><small>${phaseLabel(node.state)}</small></span>`)}</div>${path.problem ? html`<p class="meta" role="alert">${path.problem}</p>` : nothing}</article>`)}</div></section>`;
  }

  private _renderActuators(snapshot: PlantSnapshot) {
    if (!snapshot.actuators.length) return nothing;
    return html`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><h2 id="hydronicus-actuators">Actuator ownership</h2><span class="meta">Shared consumers remain visible</span></div><div class="actuator-list">${snapshot.actuators.map((actuator) => html`<article class="actuator"><div class="row"><strong>${actuator.name}</strong><span class="state ${actuator.state}">${phaseLabel(actuator.state)}</span></div><p class="meta">${phaseLabel(actuator.kind)} · ${actuator.reason ?? "No additional explanation."}</p>${actuator.active_consumers.length ? html`<p class="consumer">Consumers: ${actuator.active_consumers.map((consumer) => `${consumer.name} (${consumer.id})`).join(", ")}</p>` : html`<p class="consumer">No active circuit consumers.</p>`}</article>`)}</div></section>`;
  }

  private _renderExplanations(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-explanations"><details><summary id="hydronicus-explanations">Controller explanations</summary>${snapshot.explanations.map((step) => html`<p class="operation"><strong>${phaseLabel(step.scope)}</strong> · ${step.message}</p>`)}</details></section>`;
  }

  private _renderOperations(snapshot: PlantSnapshot) {
    const operations = Object.values(snapshot.execution.operations).flat();
    if (!operations.length) return nothing;
    return html`<section aria-labelledby="hydronicus-operations"><details open><summary id="hydronicus-operations">Latest operation outcomes (${operations.length})</summary>${operations.map((operation) => html`<p class="operation"><strong>${operationLabel(operation)}</strong><br><span class="meta">${String(operation.reason ?? operation.explanation ?? "")}</span></p>`)}</details></section>`;
  }

  private _subscribe(): void {
    if (!this._config || !this.hass || this._unsubscribe) return;
    const generation = ++this._subscriptionGeneration;
    this._reconnecting = false;
    this._error = null;
    this.hass.connection.subscribeMessage(
      (message) => {
        if (generation !== this._subscriptionGeneration) return;
        const candidate = message.snapshot;
        if (!candidate) return;
        try {
          this._snapshot = parseSnapshot(candidate);
          this._error = null;
          this._reconnecting = false;
        } catch (error) {
          this._snapshot = null;
          this._error = error instanceof Error ? error.message : "Unsupported Hydronicus snapshot.";
        }
      },
      { type: "hydronicus/subscribe_plant", plant_id: this._config.plant },
    ).then((unsubscribe) => {
      if (generation !== this._subscriptionGeneration) {
        unsubscribe();
        return;
      }
      this._unsubscribe = unsubscribe;
    }).catch((error: unknown) => {
      if (generation !== this._subscriptionGeneration) return;
      this._reconnecting = true;
      this._error = error instanceof Error ? error.message : "Hydronicus connection failed.";
    });
  }

  private _call(action: { domain: string; service: string; data: Record<string, unknown> } | null): void {
    if (!action || !this.hass) return;
    void this.hass.callService(action.domain, action.service, action.data).catch((error: unknown) => {
      this._error = error instanceof Error ? error.message : "Home Assistant action failed.";
    });
  }

  private _modeChanged = (event: Event): void => {
    if (!this._snapshot) return;
    this._call(actionForMode(this._snapshot, (event.target as HTMLSelectElement).value));
  };

  private _adjustZone(zone: ZoneSnapshot, delta: number): void {
    this._call(actionForTarget(zone, adjustTarget(zone, delta)));
  }

  private _presetChanged(zone: ZoneSnapshot, event: Event): void {
    this._call(actionForPreset(zone, (event.target as HTMLSelectElement).value));
  }

  private _startHold = (): void => {
    if (!this._snapshot || this._holdTimer !== null) return;
    this._holdingShutdown = true;
    this._holdTimer = window.setTimeout(() => {
      if (!this._snapshot) return;
      this._call(actionForSafeShutdown(this._snapshot));
      this._holdingShutdown = false;
      this._holdTimer = null;
    }, 1200);
  };

  private _clearHold = (): void => {
    if (this._holdTimer !== null) window.clearTimeout(this._holdTimer);
    this._holdTimer = null;
    this._holdingShutdown = false;
  };

  private _keyHoldStart = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      this._startHold();
    }
  };

  private _keyHoldEnd = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") this._clearHold();
  };

  static getConfigElement(): HTMLElement { return document.createElement("hydronicus-plant-card-editor"); }

  static getStubConfig(): Omit<PlantCardConfig, "type"> { return { plant: "", density: "comfortable" }; }
}

class HydronicusPlantCardEditor extends LitElement {
  static properties = { hass: { attribute: false }, _config: { state: true }, _plants: { state: true }, _error: { state: true } };
  static styles = css`
    :host { display: block; padding: 1rem; }
    label { display: grid; gap: 0.35rem; margin-bottom: 0.8rem; }
    select { box-sizing: border-box; min-height: 2.4rem; padding: 0.4rem; font: inherit; color: inherit; background: var(--card-background-color, transparent); border: 1px solid var(--divider-color); border-radius: 0.45rem; }
    select:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }
  `;
  hass?: HomeAssistantLike;
  _config: PlantCardConfig = { type: "custom:hydronicus-plant-card", plant: "", density: "comfortable" };
  _plants: Array<{ id: string; name: string }> = [];
  _error: string | null = null;
  private _loaded = false;

  setConfig(config: PlantCardConfig): void {
    this._config = { ...this._config, ...config };
    this._loadPlants();
  }

  protected updated(): void { this._loadPlants(); }

  render() {
    return html`<label>Hydronicus Plant<select aria-label="Hydronicus Plant" .value=${this._config.plant} @change=${this._plantChanged}><option value="">Select a Plant…</option>${this._plants.map((plant) => html`<option value=${plant.id}>${plant.name}</option>`)}</select></label><label>Density<select aria-label="Card density" .value=${this._config.density ?? "comfortable"} @change=${this._densityChanged}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>${this._error ? html`<p role="alert">${this._error}</p>` : nothing}`;
  }

  private _loadPlants(): void {
    if (!this.hass || this._loaded) return;
    this._loaded = true;
    this.hass.connection.sendMessagePromise<{ plants?: Array<{ id: string; name: string }> }>({ type: "hydronicus/list_plants" }).then((message) => {
      this._plants = message.plants ?? [];
    }).catch((error: unknown) => {
      this._error = error instanceof Error ? error.message : "Could not list Hydronicus Plants.";
    });
  }

  private _configChanged(): void {
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }

  private _plantChanged = (event: Event): void => {
    this._config = { ...this._config, plant: (event.target as HTMLSelectElement).value };
    this._configChanged();
  };

  private _densityChanged = (event: Event): void => {
    this._config = { ...this._config, density: (event.target as HTMLSelectElement).value as "comfortable" | "compact" };
    this._configChanged();
  };
}

customElements.define("hydronicus-plant-card", HydronicusPlantCard);
customElements.define("hydronicus-plant-card-editor", HydronicusPlantCardEditor);

declare global {
  interface Window { customCards?: Array<Record<string, unknown>>; }
}

window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "hydronicus-plant-card",
  name: "Hydronicus Plant",
  version: HYDRONICUS_FRONTEND_VERSION,
  description: "Topology-driven Hydronicus Plant status and controls.",
  preview: false,
  documentationURL: "https://github.com/brumi1024/ha-hydronicus",
});
