import { html, nothing, type TemplateResult } from "lit";
import { HydronicusCardElement } from "./card-base";
import { configForm, stubConfig, validateConfig, type ConfigForm } from "./config";
import { actionForSafeShutdown, plantVisualState } from "./logic";
import { renderAlerts, renderBoundary, renderEquipment, renderExplanations, renderHeader, renderOperations, renderPaths, renderRooms } from "./render/plant";
import { renderActionError, renderState, renderStreamNotice, renderUnservedPlant, showableSnapshot } from "./render/state";
import type { PlantState } from "./store";
import type { HomeAssistantLike, PlantCardConfig, PlantSnapshot } from "./types";

const HOLD_MS = 1_200;
const EYEBROW = "Hydronicus Plant";
export class HydronicusPlantCard extends HydronicusCardElement {
  static properties = {
    _config: { state: true },
    _holdingShutdown: { state: true },
  };

  declare _config: PlantCardConfig | undefined;
  declare _holdingShutdown: boolean;

  private _holdTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    super();
    this._config = undefined;
    this._holdingShutdown = false;
  }

  static async getConfigForm(): Promise<ConfigForm> {
    return configForm();
  }

  static async getStubConfig(hass?: HomeAssistantLike): Promise<Omit<PlantCardConfig, "type">> {
    return stubConfig(hass);
  }

  setConfig(config: PlantCardConfig): void {
    const next = validateConfig(config);
    if (next.plant !== this._config?.plant) this.resetPlant();
    this._config = next;
  }

  protected get plantId(): string | undefined {
    return this._config?.plant;
  }

  /** Masonry height in 50 px units, estimated from the rendered sections. */
  getCardSize(): number {
    const snapshot = this._plant.snapshot;
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

  disconnectedCallback(): void {
    this._clearHold();
    super.disconnectedCallback();
  }

  protected plantStateChanged(state: PlantState): void {
    // Controls must never act on a Plant the backend no longer serves.
    if (!state.snapshot) this._clearHold();
  }

  render(): TemplateResult {
    const config = this._config;
    if (!config || !config.plant) {
      return renderState(EYEBROW, EYEBROW, "Select a Hydronicus Plant in the card editor.", "status");
    }
    const state = this._plant;
    const snapshot = showableSnapshot(state);
    if (!snapshot) return renderUnservedPlant(EYEBROW, state);
    const context = this.renderContext;
    return html`<ha-card class=${config.density ?? "comfortable"} data-visual=${plantVisualState(snapshot)}>
      ${renderHeader(context, snapshot, this._renderShutdown(snapshot))}
      ${renderStreamNotice(state.status)}
      ${renderActionError(this._actionError, this.dismissActionError)}
      ${renderBoundary(snapshot)}
      ${renderAlerts(context, snapshot)}
      ${renderRooms(context, snapshot)}
      ${renderPaths(snapshot)}
      ${renderEquipment(snapshot)}
      ${renderExplanations(snapshot)}
      ${renderOperations(context, snapshot)}
    </ha-card>`;
  }

  private _renderShutdown(snapshot: PlantSnapshot): TemplateResult {
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

  private _startHold(): void {
    if (!this._plant.snapshot || this._holdTimer !== null) return;
    this._holdingShutdown = true;
    this._holdTimer = setTimeout(() => {
      this._holdTimer = null;
      this._holdingShutdown = false;
      const snapshot = this._plant.snapshot;
      if (snapshot) this.call(actionForSafeShutdown(snapshot));
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
