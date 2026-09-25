import { html, type TemplateResult } from "lit";
import { HydronicusCardElement } from "./card-base";
import { ROOM_EDITOR_TAG, roomStubConfig, validateRoomConfig } from "./config";
import { roomVisualState } from "./logic";
import { renderRoom } from "./render/room";
import { renderActionError, renderState, renderStreamNotice, renderUnservedPlant, showableSnapshot } from "./render/state";
import type { HomeAssistantLike, RoomCardConfig } from "./types";

const EYEBROW = "Hydronicus Room";

/**
 * One Room of a Plant as a card of its own, with the same tile and
 * controls as the Room inside the Plant card. Cards for Rooms of the same
 * Plant share one Plant subscription.
 */
export class HydronicusRoomCard extends HydronicusCardElement {
  static properties = {
    _config: { state: true },
  };

  declare _config: RoomCardConfig | undefined;

  constructor() {
    super();
    this._config = undefined;
  }

  static getConfigElement(): HTMLElement {
    return document.createElement(ROOM_EDITOR_TAG);
  }

  static async getStubConfig(hass?: HomeAssistantLike): Promise<Omit<RoomCardConfig, "type">> {
    return roomStubConfig(hass);
  }

  setConfig(config: RoomCardConfig): void {
    const next = validateRoomConfig(config);
    if (next.plant !== this._config?.plant) this.resetPlant();
    else if (next.room !== this._config?.room) this._actionError = null;
    this._config = next;
  }

  /** The Plant to follow; none until a Room is chosen, since only a Room is shown. */
  protected get plantId(): string | undefined {
    return this._config?.room ? this._config.plant : undefined;
  }

  /** Masonry height in 50 px units, like one Room in the Plant card. */
  getCardSize(): number {
    return 5;
  }

  getGridOptions() {
    // Half a section, like a thermostat card; no rows, so the height
    // follows the tile's content.
    return { columns: 6, min_columns: 4 };
  }

  render(): TemplateResult {
    const config = this._config;
    if (!config || !config.plant) {
      return renderState(EYEBROW, EYEBROW, "Select a Hydronicus Plant and a Room in the card editor.", "status");
    }
    if (!config.room) {
      return renderState(EYEBROW, EYEBROW, "Select a Room in the card editor.", "status");
    }
    const state = this._plant;
    const snapshot = showableSnapshot(state);
    if (!snapshot) return renderUnservedPlant(EYEBROW, state);
    const zone = snapshot.zones.find((candidate) => candidate.id === config.room);
    if (!zone) {
      // The snapshot omits Rooms the user may not read, so a hidden Room
      // looks the same as one that was removed.
      return renderState(EYEBROW, "Room not found", "This Room is not in the Plant, or you do not have access to it. Choose another Room in the card editor.", "alert");
    }
    return html`<ha-card class="room-card ${config.density ?? "comfortable"}" data-visual=${roomVisualState(zone)}>
      ${renderStreamNotice(state.status)}
      ${renderActionError(this._actionError, this.dismissActionError)}
      ${renderRoom(this.renderContext, zone, { headingLevel: 2 })}
    </ha-card>`;
  }
}
