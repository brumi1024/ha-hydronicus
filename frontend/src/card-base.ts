import { ContextConsumer, createContext } from "@lit/context";
import { LitElement, type PropertyDeclarations, type PropertyValues } from "lit";
import { plantDirectory } from "./config";
import { CELSIUS, temperatureUnit, type TemperatureUnit } from "./format";
import type { ActionCall } from "./logic";
import type { RenderContext } from "./render/context";
import { IDLE_PLANT_STATE, plantStore, type PlantState, type Release } from "./store";
import { errorMessage } from "./stream";
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
} from "./types";

/*
 * Home Assistant frontend context groups (documented since 2026.5). The keys
 * are the context names the frontend providers answer to.
 */
const connectionContext = createContext<HassConnectionContextValue>("hassConnection");
const apiContext = createContext<HassApiContextValue>("hassApi");
const configContext = createContext<HassConfigContextValue>("hassConfig");
const internationalizationContext = createContext<HassInternationalizationContextValue>("hassInternationalization");

type ContextSource = "connection" | "api" | "config" | "i18n";

/**
 * What every Hydronicus card shares: the Home Assistant frontend data it
 * reads, its subscription to the shared Plant store, and how it calls
 * actions and reports their failures. A subclass names its Plant and
 * renders.
 */
export abstract class HydronicusCardElement extends LitElement {
  static properties: PropertyDeclarations = {
    preview: { type: Boolean },
    _connection: { state: true },
    _unit: { state: true },
    _locale: { state: true },
    _localize: { state: true },
    _plant: { state: true },
    _actionError: { state: true },
  };

  static styles = cardStyles;

  declare preview: boolean;
  declare _connection: HomeAssistantConnection | undefined;
  declare _unit: TemperatureUnit;
  declare _locale: FrontendLocale | undefined;
  declare _localize: Localize | undefined;
  declare _plant: PlantState;
  declare _actionError: string | null;

  private _hass: HomeAssistantLike | undefined;
  private _callService: CallService | undefined;
  private readonly _fromContext = new Set<ContextSource>();
  private _release: Release | undefined;
  private _followed: { connection: HomeAssistantConnection; plantId: string } | undefined;

  constructor() {
    super();
    this.preview = false;
    this._connection = undefined;
    this._unit = CELSIUS;
    this._locale = undefined;
    this._localize = undefined;
    this._plant = IDLE_PLANT_STATE;
    this._actionError = null;
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

  /** The Plant UUID this card follows, or undefined while none is chosen. */
  protected abstract get plantId(): string | undefined;

  /** Called whenever the followed Plant's state changes. */
  protected plantStateChanged?(state: PlantState): void;

  /** Forget the previous Plant's state; call when the configured Plant changes. */
  protected resetPlant(): void {
    this._plant = IDLE_PLANT_STATE;
    this._actionError = null;
  }

  connectedCallback(): void {
    super.connectedCallback();
    // Follow the Plant again right away, so a card that Lovelace moves
    // within the page keeps sharing the existing subscription.
    this._follow();
  }

  disconnectedCallback(): void {
    this._unfollow();
    super.disconnectedCallback();
  }

  protected updated(changed: PropertyValues): void {
    super.updated(changed);
    this._syncSelectValues();
    if (!this.isConnected) return;
    this._follow();
    if (this._connection && (changed.has("_connection") || this.preview)) void plantDirectory.load(this._connection);
  }

  private _follow(): void {
    const connection = this._connection;
    const plantId = this.plantId || undefined;
    const followed = this._followed;
    if (followed && followed.connection === connection && followed.plantId === plantId) return;
    this._unfollow();
    if (!connection || !plantId) return;
    this._followed = { connection, plantId };
    this._release = plantStore.subscribe(connection, plantId, (state) => {
      this._plant = state;
      this.plantStateChanged?.(state);
    });
  }

  private _unfollow(): void {
    this._release?.();
    this._release = undefined;
    this._followed = undefined;
    this._plant = IDLE_PLANT_STATE;
    this.plantStateChanged?.(IDLE_PLANT_STATE);
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

  /** What the shared templates render with. */
  protected get renderContext(): RenderContext {
    return {
      unit: this._unit,
      locale: this._locale,
      localize: this._localize,
      moreInfo: (entityId) => this.moreInfo(entityId),
      call: (action) => this.call(action),
    };
  }

  protected moreInfo(entityId: string): void {
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }

  protected call(action: ActionCall | null): void {
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

  protected dismissActionError = (): void => {
    this._actionError = null;
  };
}
