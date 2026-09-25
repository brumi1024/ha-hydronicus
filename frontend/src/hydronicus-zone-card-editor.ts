import { LitElement, html, type PropertyValues, type TemplateResult } from "lit";
import { computeHelper, computeLabel, plantDirectory, validateZoneConfig, zoneConfigSchema } from "./config";
import { plantStore, type Release } from "./store";
import type { HomeAssistantConnection, HomeAssistantLike, PlantSummary, ZoneCardConfig, ZoneSnapshot } from "./types";

type ZoneChoice = Pick<ZoneSnapshot, "id" | "name">;

/**
 * The Zone card's visual editor. The built-in form editor takes one fixed
 * schema, but the Zone choices depend on the chosen Plant, so this element
 * renders Home Assistant's `ha-form` with a schema that follows the Plant.
 * It lists the Zones of the chosen Plant's snapshot from the shared Plant
 * store, so the card preview and the editor share one subscription.
 */
export class HydronicusZoneCardEditor extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _plants: { state: true },
    _zones: { state: true },
  };

  declare hass: HomeAssistantLike | undefined;
  declare _config: ZoneCardConfig | undefined;
  declare _plants: PlantSummary[];
  declare _zones: ZoneChoice[];

  private _release: Release | undefined;
  private _followed: { connection: HomeAssistantConnection; plantId: string } | undefined;
  private _directoryConnection: HomeAssistantConnection | undefined;

  constructor() {
    super();
    this.hass = undefined;
    this._config = undefined;
    this._plants = plantDirectory.known;
    this._zones = [];
  }

  /**
   * Keep the config as Home Assistant passed it, with keys such as
   * `grid_options` that the card itself does not read, so an edit keeps them.
   * An invalid config throws, which makes Home Assistant offer YAML instead.
   */
  setConfig(config: ZoneCardConfig): void {
    validateZoneConfig(config);
    this._config = config;
  }

  connectedCallback(): void {
    super.connectedCallback();
    // Reattaching needs the Plant again; updated() follows it.
    this.requestUpdate();
  }

  disconnectedCallback(): void {
    this._unfollow();
    this._directoryConnection = undefined;
    super.disconnectedCallback();
  }

  protected updated(changed: PropertyValues): void {
    super.updated(changed);
    // Forgetting the Zones on disconnect renders once more; stay released.
    if (!this.isConnected) return;
    const connection = this.hass?.connection;
    if (connection && connection !== this._directoryConnection) {
      this._directoryConnection = connection;
      void plantDirectory.load(connection).then((plants) => {
        this._plants = plants;
      });
    }
    this._follow(connection, this._config?.plant || undefined);
  }

  private _follow(connection: HomeAssistantConnection | undefined, plantId: string | undefined): void {
    const followed = this._followed;
    if (followed?.connection === connection && followed?.plantId === plantId) return;
    this._unfollow();
    if (!connection || !plantId) return;
    this._followed = { connection, plantId };
    this._release = plantStore.subscribe(connection, plantId, (state) => {
      // Keep the last known Zones while the Plant reconnects or reloads.
      if (state.snapshot) this._zones = state.snapshot.zones.map((zone) => ({ id: zone.id, name: zone.name }));
    });
  }

  private _unfollow(): void {
    this._release?.();
    this._release = undefined;
    this._followed = undefined;
    this._zones = [];
  }

  render(): TemplateResult {
    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config ?? {}}
      .schema=${zoneConfigSchema(this._plants, this._zones)}
      .computeLabel=${computeLabel}
      .computeHelper=${computeHelper}
      @value-changed=${this._valueChanged}
    ></ha-form>`;
  }

  private _valueChanged(event: CustomEvent<{ value: Record<string, unknown> }>): void {
    event.stopPropagation();
    // `ha-form` reports the whole data object it was given, with the edit.
    const value = { ...event.detail.value } as unknown as ZoneCardConfig;
    // A Zone id belongs to one Plant, so choosing another Plant clears it.
    if (value.plant !== this._config?.plant) value.zone = "";
    this._config = value;
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: value } }));
  }
}
