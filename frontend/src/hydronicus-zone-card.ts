import { html, type TemplateResult } from "lit";
import { HydronicusCardElement } from "./card-base";
import { validateZoneConfig, ZONE_EDITOR_TAG, zoneStubConfig } from "./config";
import { zoneAlerts, zoneTileSize, zoneVisualState } from "./logic";
import { renderActionError, renderState, renderStreamNotice, renderUnservedPlant, showableSnapshot } from "./render/state";
import { renderZone } from "./render/zone";
import type { HomeAssistantLike, ZoneCardConfig } from "./types";

const EYEBROW = "Hydronicus Zone";

/**
 * One Zone of a Plant as a card of its own, with the same tile and
 * controls as the Zone inside the Plant card. Cards for Zones of the same
 * Plant share one Plant subscription.
 */
export class HydronicusZoneCard extends HydronicusCardElement {
  static properties = {
    _config: { state: true },
  };

  declare _config: ZoneCardConfig | undefined;

  constructor() {
    super();
    this._config = undefined;
  }

  static getConfigElement(): HTMLElement {
    return document.createElement(ZONE_EDITOR_TAG);
  }

  static async getStubConfig(hass?: HomeAssistantLike): Promise<Omit<ZoneCardConfig, "type">> {
    return zoneStubConfig(hass);
  }

  setConfig(config: ZoneCardConfig): void {
    const next = validateZoneConfig(config);
    if (next.plant !== this._config?.plant) this.resetPlant();
    else if (next.zone !== this._config?.zone) this._actionError = null;
    this._config = next;
  }

  /** The Plant to follow; none until a Zone is chosen, since only a Zone is shown. */
  protected get plantId(): string | undefined {
    return this._config?.zone ? this._config.plant : undefined;
  }

  /** Masonry height in 50 px units, like one Zone in the Plant card. */
  getCardSize(): number {
    const zone = this._plant.snapshot?.zones.find((candidate) => candidate.id === this._config?.zone);
    return zone ? zoneTileSize(zone) : 5;
  }

  getGridOptions() {
    // Half a section, like a thermostat card; no rows, so the height
    // follows the tile's content.
    return { columns: 6, min_columns: 4 };
  }

  render(): TemplateResult {
    const config = this._config;
    if (!config || !config.plant) {
      return renderState(EYEBROW, EYEBROW, "Select a Hydronicus Plant and a Zone in the card editor.", "status");
    }
    if (!config.zone) {
      return renderState(EYEBROW, EYEBROW, "Select a Zone in the card editor.", "status");
    }
    const state = this._plant;
    const snapshot = showableSnapshot(state);
    if (!snapshot) return renderUnservedPlant(EYEBROW, state);
    const zone = snapshot.zones.find((candidate) => candidate.id === config.zone);
    if (!zone) {
      // The snapshot omits Zones the user may not read, so a hidden Zone
      // looks the same as one that was removed.
      return renderState(EYEBROW, "Zone not found", "This Zone is not in the Plant, or you do not have access to it. Choose another Zone in the card editor.", "alert");
    }
    const alerts = zoneAlerts(snapshot, zone.id);
    return html`<ha-card part="card" class="zone-card ${config.density ?? "comfortable"}" data-visual=${zoneVisualState(zone, alerts)}>
      ${renderStreamNotice(state.status)}
      ${renderActionError(this._actionError, this.dismissActionError)}
      ${renderZone(this.renderContext, zone, { headingLevel: 2, alerts })}
    </ha-card>`;
  }
}
