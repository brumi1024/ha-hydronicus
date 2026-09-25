import { html, nothing, type TemplateResult } from "lit";
import { HydronicusCardElement } from "./card-base";
import { configForm, shownSections, stubConfig, validateConfig, type ConfigForm } from "./config";
import { actionForSafeShutdown, plantVisualState } from "./logic";
import type { RenderContext } from "./render/context";
import { renderAlerts, renderBoundary, renderEquipment, renderExplanations, renderHeader, renderOperations, renderPaths, renderRooms } from "./render/plant";
import { renderActionError, renderState, renderStreamNotice, renderUnservedPlant, showableSnapshot } from "./render/state";
import type { PlantState } from "./store";
import type { HomeAssistantLike, PlantCardConfig, PlantSection, PlantSnapshot } from "./types";

const HOLD_MS = 1_200;
const EYEBROW = "Hydronicus Plant";
/** Sections whose items fill a grid or a wide track, so the card spans the section. */
const WIDE_SECTIONS: readonly PlantSection[] = ["rooms", "paths", "equipment"];

/** Masonry height in 50 px units of each section, estimated from its items. */
function sectionSize(section: PlantSection, snapshot: PlantSnapshot): number {
  switch (section) {
    case "header":
      return 4;
    case "alerts": {
      const alerts = Math.min(snapshot.alerts.length, 3);
      return alerts ? 1 + alerts : 0;
    }
    case "rooms":
      return 1 + Math.max(1, snapshot.zones.length) * 5;
    case "paths":
      return snapshot.delivery_paths.length ? 1 + snapshot.delivery_paths.length * 3 : 0;
    case "equipment":
      return snapshot.actuators.length ? 1 + snapshot.actuators.length * 2 : 0;
    case "explanations":
      return 1;
    case "operations": {
      const operations = Object.values(snapshot.execution.operations).flat().length;
      return operations ? 1 + operations : 0;
    }
  }
}

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

  /** Masonry height in 50 px units, estimated from the shown sections. */
  getCardSize(): number {
    const snapshot = this._plant.snapshot;
    const sections = shownSections(this._config);
    if (!snapshot) return sections.includes("header") ? 4 : 2;
    return Math.max(1, sections.reduce((size, section) => size + sectionSize(section, snapshot), 0));
  }

  getGridOptions() {
    // No rows: the Sections grid then sizes the card to its content height.
    // Without a Room grid, path track, or equipment list the card fits half
    // a section, like other summary cards.
    const wide = shownSections(this._config).some((section) => WIDE_SECTIONS.includes(section));
    return wide ? { columns: 12, min_columns: 6 } : { columns: 6, min_columns: 4 };
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
    const sections = shownSections(config);
    // Notices about the stream and a failed action follow the header, or
    // lead the card when the header is not shown.
    const notices = html`${renderStreamNotice(state.status)}${renderActionError(this._actionError, this.dismissActionError)}`;
    return html`<ha-card part="card" class=${config.density ?? "comfortable"} data-visual=${plantVisualState(snapshot)}>
      ${sections.includes("header") ? nothing : notices}
      ${sections.map((section) => this._renderSection(section, context, snapshot, notices))}
    </ha-card>`;
  }

  private _renderSection(section: PlantSection, context: RenderContext, snapshot: PlantSnapshot, notices: TemplateResult) {
    switch (section) {
      case "header":
        return html`${renderHeader(context, snapshot, this._renderShutdown(snapshot))}
          ${notices}
          ${renderBoundary(snapshot)}`;
      case "alerts":
        return renderAlerts(context, snapshot);
      case "rooms":
        return renderRooms(context, snapshot);
      case "paths":
        return renderPaths(snapshot);
      case "equipment":
        return renderEquipment(snapshot);
      case "explanations":
        return renderExplanations(snapshot);
      case "operations":
        return renderOperations(context, snapshot);
    }
  }

  private _renderShutdown(snapshot: PlantSnapshot): TemplateResult {
    const disabled = !snapshot.controls.safe_shutdown;
    // In Dry run nothing executes, so the action stays available but quiet.
    const quiet = snapshot.plant.execution_boundary.dry_run;
    return html`<button type="button" part="control" class=${`shutdown${quiet ? " quiet" : ""}${this._holdingShutdown ? " is-holding" : ""}`} ?disabled=${disabled} aria-describedby="shutdown-hint"
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
