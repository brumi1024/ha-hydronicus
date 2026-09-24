import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../src/index";
import { FakeConnection, makeHass, makeSnapshot, makeZone, OTHER_PLANT_ID, PLANT_ID, settle, type FakeHass } from "./fixtures";

type CardElement = HTMLElement & {
  hass?: unknown;
  setConfig(config: Record<string, unknown>): void;
  getCardSize(): number;
  getGridOptions(): Record<string, unknown>;
  updateComplete: Promise<boolean>;
};

type CardClass = CustomElementConstructor & {
  getConfigForm(): Promise<{
    schema: Array<Record<string, unknown>>;
    assertConfig?: (config: Record<string, unknown>) => void;
    computeLabel?: (schema: { name: string }) => string | undefined;
  }>;
  getStubConfig(hass: unknown): Promise<Record<string, unknown>>;
};

const TAG = "hydronicus-plant-card";

async function mount(hass: FakeHass | undefined, config: Record<string, unknown> = {}): Promise<CardElement> {
  const card = document.createElement(TAG) as CardElement;
  card.setConfig({ type: `custom:${TAG}`, plant: PLANT_ID, ...config });
  if (hass) card.hass = hass;
  document.body.append(card);
  await settle(card);
  return card;
}

function root(card: CardElement): ShadowRoot {
  if (!card.shadowRoot) throw new Error("The card has no shadow root.");
  return card.shadowRoot;
}

function text(card: CardElement): string {
  return (root(card).textContent ?? "").replace(/\s+/g, " ");
}

async function deliver(card: CardElement, connection: FakeConnection, snapshot = makeSnapshot()): Promise<void> {
  connection.last.emit({ snapshot });
  await settle(card);
}

beforeEach(() => {
  document.body.replaceChildren();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

describe("B5 reactive properties", () => {
  it("leaves the loading state when the first snapshot arrives", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    expect(hass.connection.subscriptions).toHaveLength(1);

    await deliver(card, hass.connection);

    expect(text(card)).toContain("Test plant");
    expect(root(card).querySelector("[aria-busy='true']")).toBeNull();
  });
});

describe("C3 select values", () => {
  it("shows the real requested mode and preset in each dropdown", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot({ zones: [makeZone({ thermostat: { ...makeZone().thermostat, preset: "eco" } })] });
    snapshot.plant.requested_mode = "cooling";

    await deliver(card, hass.connection, snapshot);

    const selects = [...root(card).querySelectorAll("select")];
    expect(selects).toHaveLength(2);
    expect(selects[0].value).toBe("cooling");
    expect(selects[1].value).toBe("eco");
  });
});

describe("C4 plant changes", () => {
  it("resubscribes to the new Plant and drops the old stream", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const first = hass.connection.last;

    card.setConfig({ type: `custom:${TAG}`, plant: OTHER_PLANT_ID });
    await settle(card);

    expect(first.unsubscribed).toBe(true);
    expect(hass.connection.subscriptions).toHaveLength(2);
    expect(hass.connection.last.message).toEqual({ type: "hydronicus/subscribe_plant", plant_id: OTHER_PLANT_ID });
    expect(text(card)).not.toContain("Test plant");
  });
});

describe("C5 subscription lifecycle", () => {
  it("subscribes once per connection and Plant while hass keeps changing", async () => {
    const hass = makeHass();
    hass.connection.autoResolve = false;
    const card = await mount(hass);

    for (let index = 0; index < 5; index += 1) {
      card.hass = { ...hass };
      await settle(card);
    }
    hass.connection.last.resolve();
    for (let index = 0; index < 5; index += 1) {
      card.hass = { ...hass };
      await settle(card);
    }

    expect(hass.connection.subscriptions).toHaveLength(1);
  });

  it("retries a transient failure with backoff instead of on every hass update", async () => {
    vi.useFakeTimers();
    const hass = makeHass();
    hass.connection.autoResolve = false;
    const card = await mount(hass);

    hass.connection.last.reject({ code: "unknown_error", message: "Boom" });
    await settle(card);
    for (let index = 0; index < 20; index += 1) {
      card.hass = { ...hass };
      await settle(card);
    }
    expect(hass.connection.subscriptions).toHaveLength(1);
    expect(text(card)).toContain("Boom");

    await vi.advanceTimersByTimeAsync(1_000);
    expect(hass.connection.subscriptions).toHaveLength(2);
    hass.connection.last.reject({ code: "unknown_error", message: "Boom" });
    await settle(card);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(hass.connection.subscriptions).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(hass.connection.subscriptions).toHaveLength(3);

    hass.connection.last.resolve();
    await deliver(card, hass.connection);
    expect(text(card)).toContain("Test plant");
  });

  it.each([
    ["plant_not_found", "Plant was not found"],
    ["unauthorized", "do not have access"],
  ])("shows a terminal state for %s without retrying", async (code, message) => {
    vi.useFakeTimers();
    const hass = makeHass();
    hass.connection.autoResolve = false;
    const card = await mount(hass);

    hass.connection.last.reject({ code, message: "Rejected." });
    await settle(card);
    await vi.advanceTimersByTimeAsync(300_000);

    expect(hass.connection.subscriptions).toHaveLength(1);
    expect(text(card)).toContain(message);
  });

  it("shows an unavailable Plant and recovers on the next snapshot", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    hass.connection.last.emit({ status: "unavailable", plant_id: PLANT_ID });
    await settle(card);
    expect(text(card)).toContain("unavailable");
    expect(root(card).querySelector("select")).toBeNull();

    await deliver(card, hass.connection);
    expect(text(card)).toContain("Test plant");
    expect(hass.connection.subscriptions).toHaveLength(1);
  });

  it("stops the stream when the backend revokes access", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    hass.connection.last.emit({ status: "unauthorized", plant_id: PLANT_ID });
    await settle(card);

    expect(hass.connection.last.unsubscribed).toBe(true);
    expect(text(card)).toContain("do not have access");
    expect(text(card)).not.toContain("Test plant");
  });

  it("resubscribes exactly once after the connection reconnects", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    expect(hass.connection.last.options).toMatchObject({ resubscribe: false });

    hass.connection.fire("disconnected");
    await settle(card);
    expect(text(card)).toContain("Reconnecting");
    hass.connection.fire("ready");
    await settle(card);

    expect(hass.connection.subscriptions).toHaveLength(2);
    // The old unsubscribe belongs to the closed socket and must not be sent.
    expect(hass.connection.subscriptions[0].unsubscribed).toBe(false);
    await deliver(card, hass.connection);
    expect(text(card)).toContain("Test plant");
  });

  it("unsubscribes when the card leaves the DOM", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    card.remove();
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(true);
  });
});

describe("C6 hold to shut down", () => {
  async function shutdownButton(): Promise<{ card: CardElement; hass: FakeHass; button: HTMLButtonElement }> {
    vi.useFakeTimers();
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const button = root(card).querySelector<HTMLButtonElement>("button.shutdown");
    if (!button) throw new Error("No shutdown button.");
    return { card, hass, button };
  }

  it("presses the shutdown button after a complete hold", async () => {
    const { hass, button } = await shutdownButton();
    button.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(1_300);
    expect(hass.calls).toEqual([{ domain: "button", service: "press", data: { entity_id: "button.hydronic_shutdown" }, notifyOnError: false }]);
  });

  it.each(["pointerleave", "pointercancel", "lostpointercapture", "pointerup"])(
    "cancels the hold on %s",
    async (type) => {
      const { hass, button } = await shutdownButton();
      button.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
      await vi.advanceTimersByTimeAsync(400);
      button.dispatchEvent(new PointerEvent(type, { bubbles: true }));
      await vi.advanceTimersByTimeAsync(2_000);
      expect(hass.calls).toEqual([]);
    },
  );
});

describe("C7 failed actions", () => {
  it("keeps the snapshot and shows an inline error", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    hass.failNextCall = "Entity is unavailable.";

    const select = root(card).querySelector("select");
    if (!select) throw new Error("No mode select.");
    select.value = "idle";
    select.dispatchEvent(new Event("change"));
    await settle(card);

    expect(text(card)).toContain("Test plant");
    const error = root(card).querySelector("[role='alert']");
    expect(error?.textContent).toContain("Entity is unavailable.");
    // The dropdown returns to the Plant's real mode.
    expect(root(card).querySelector("select")?.value).toBe("heating");

    root(card).querySelector<HTMLButtonElement>(".action-error button")?.click();
    await settle(card);
    expect(root(card).querySelector(".action-error")).toBeNull();
  });

  it("shows the error only inline, without Home Assistant's own toast", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    hass.failNextCall = "Entity is unavailable.";

    root(card).querySelector<HTMLButtonElement>(".zone-actions button")?.click();
    await settle(card);

    expect(hass.calls).toHaveLength(1);
    expect(hass.calls[0].notifyOnError).toBe(false);
    expect(root(card).querySelector(".action-error")?.textContent).toContain("Entity is unavailable.");
  });
});

describe("Zone presets", () => {
  it.each([[[]], [["none"]]])("hides the preset control when a Zone has no presets (%j)", async (presetModes) => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, preset: "none", preset_modes: presetModes } }] }));

    expect(root(card).querySelector("select.preset")).toBeNull();
    expect(text(card)).not.toContain("Preset:");
    expect(root(card).querySelectorAll(".zone-actions button")).toHaveLength(2);
  });

  it("offers each configured preset once", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, preset_modes: ["none", "comfort", "eco"] } }] }));

    const options = [...root(card).querySelectorAll("select.preset option")].map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(["none", "comfort", "eco"]);
  });
});

describe("Translated states", () => {
  const TRANSLATIONS: Record<string, string> = {
    "component.hydronicus.entity.sensor.controller_status.state.heating": "Heizen (Status)",
    "component.hydronicus.entity.select.requested_mode.state.heating": "Heizen (angefordert)",
    "component.hydronicus.entity.select.requested_mode.state.auto": "Automatisch",
    "component.hydronicus.entity.select.requested_mode.state.idle": "Leerlauf",
    "component.hydronicus.entity.select.requested_mode.state.cooling": "Kühlen",
    "component.hydronicus.entity.sensor.operating_mode.state.idle": "Leerlauf (aktiv)",
  };
  const localize = (key: string) => TRANSLATIONS[key] ?? "";

  it("labels entity-backed values with Home Assistant's translated states", async () => {
    const hass = makeHass({ localize });
    const card = await mount(hass);
    const snapshot = makeSnapshot();
    await deliver(card, hass.connection, makeSnapshot({ plant: { ...snapshot.plant, active_mode: "idle", controller: { evaluated: true, mode_explanation: "heating demand" } } }));

    expect(root(card).querySelector(".status-primary")?.textContent).toContain("Heizen (Status)");
    const detail = root(card).querySelector(".mode-detail")?.textContent ?? "";
    expect(detail).toContain("Heizen (angefordert)");
    expect(detail).toContain("Leerlauf (aktiv)");
    const options = [...root(card).querySelectorAll(".mode-control option")].map((option) => option.textContent?.trim());
    expect(options).toEqual(["Automatisch", "Leerlauf", "Heizen (angefordert)", "Kühlen"]);
    // Free-text explanations stay as they are.
    expect(text(card)).toContain("heating demand");
  });

  it("falls back to readable raw values without translations", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot();
    await deliver(card, hass.connection, makeSnapshot({ plant: { ...snapshot.plant, status: "safe_shutdown" } }));

    expect(root(card).querySelector(".status-primary")?.textContent).toContain("safe shutdown");
  });
});

describe("Right-to-left prose", () => {
  it("lets English prose pick its own direction", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot({
      explanations: [{ order: 1, scope: "zone", code: "demand", message: "No demand in this Zone." }],
      actuators: [
        { id: "a", name: "Pump", kind: "pump", state: "idle", requested: null, observed: "off", ready: true, blocked: false, mismatch: false, reason: "Waiting.", active_consumers: [] },
      ],
      alerts: [{ code: "stale", severity: "warning", priority: 1, scope: "plant", message: "Sensor is stale." }],
    });
    await deliver(card, hass.connection, snapshot);

    for (const selector of [".boundary-copy", ".zone-note", ".operation-copy", ".alert", ".actuator .meta", ".header-copy > p.meta:last-of-type", ".diagnostic-chip", ".section-head > .meta"]) {
      const nodes = [...root(card).querySelectorAll(selector)];
      expect(nodes.length, selector).toBeGreaterThan(0);
      for (const node of nodes) expect(node.getAttribute("dir"), selector).toBe("auto");
    }
    // A signed step such as "−0.5" has no strong direction of its own.
    for (const button of root(card).querySelectorAll(".zone-actions button")) expect(button.getAttribute("dir")).toBe("ltr");
  });
});

describe("C11 theme and badge", () => {
  it("renders inside ha-card and styles the Dry run badge", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    expect(root(card).querySelector("ha-card")).not.toBeNull();
    expect(root(card).querySelector(".badge.dry-run")).not.toBeNull();
  });
});

describe("C13 right-to-left layouts", () => {
  it("uses only logical properties for the inline direction", () => {
    const styles = (customElements.get(TAG) as unknown as { styles: { cssText: string } }).styles.cssText;
    const physical = styles.match(
      /(?:^|[\s;{])(?:(?:margin|padding|border)-(?:left|right)(?:-[a-z]+)?|left|right)\s*:|text-align:\s*(?:left|right)|float:\s*(?:left|right)/g,
    );
    expect(physical).toBeNull();
    expect(styles).toContain(":host(:dir(rtl))");
  });
});

describe("C8 Home Assistant frontend contexts", () => {
  it("uses the frontend context groups without a hass object", async () => {
    const { ContextProvider, createContext } = await import("@lit/context");
    const { LitElement } = await import("lit");
    const hass = makeHass();
    class Provider extends LitElement {
      constructor() {
        super();
        new ContextProvider(this, { context: createContext("hassConnection"), initialValue: { connection: hass.connection, connected: true } });
        new ContextProvider(this, { context: createContext("hassApi"), initialValue: { callService: hass.callService } });
        new ContextProvider(this, { context: createContext("hassConfig"), initialValue: { config: { unit_system: { temperature: "°F" } } } });
        new ContextProvider(this, { context: createContext("hassInternationalization"), initialValue: { language: "de", locale: { language: "de", number_format: "language" } } });
      }
      protected createRenderRoot() {
        return this;
      }
    }
    customElements.define("test-hass-provider", Provider);
    const provider = document.createElement("test-hass-provider");
    document.body.append(provider);
    const card = document.createElement(TAG) as CardElement;
    card.setConfig({ type: `custom:${TAG}`, plant: PLANT_ID });
    provider.append(card);
    await settle(card);

    expect(hass.connection.subscriptions).toHaveLength(1);
    await deliver(card, hass.connection);
    const values = [...root(card).querySelectorAll(".metric-value")].map((node) => node.textContent);
    expect(values).toEqual(["68,0", "69,8"]);

    // A later hass object must not override values that contexts provide.
    card.hass = makeHass();
    await settle(card);
    expect(hass.connection.subscriptions).toHaveLength(1);
    root(card).querySelector<HTMLButtonElement>(".zone-actions button")?.click();
    await settle(card);
    expect(hass.calls).toHaveLength(1);
  });
});

describe("C12 units and locale", () => {
  it("converts Celsius snapshot temperatures to the user's unit system", async () => {
    const hass = makeHass({ config: { unit_system: { temperature: "°F" } } });
    const snapshot = makeSnapshot({
      zones: [makeZone({ cooling: { ...makeZone().cooling, dew_point: 10, condensation_margin: 5 } })],
    });
    const card = await mount(hass);
    await deliver(card, hass.connection, snapshot);

    const values = [...root(card).querySelectorAll(".metric-value")].map((node) => node.textContent);
    expect(values).toEqual(["68.0", "69.8"]);
    expect(text(card)).toContain("°F");
    expect(text(card)).not.toContain("°C");
    expect(text(card)).toContain("Dew point 50.0 °F");
    expect(text(card)).toContain("Margin 9.0 °F");
  });

  it("sends target changes in the user's unit system", async () => {
    const hass = makeHass({ config: { unit_system: { temperature: "°F" } } });
    const card = await mount(hass);
    await deliver(card, hass.connection);

    const increase = root(card).querySelector<HTMLButtonElement>(".zone-actions button:nth-of-type(2)");
    increase?.click();
    await settle(card);

    expect(hass.calls).toEqual([
      { domain: "climate", service: "set_temperature", data: { entity_id: "climate.hydronic_living_room", temperature: 70 }, notifyOnError: false },
    ]);
  });

  it("formats numbers with the user's locale", async () => {
    const hass = makeHass({ language: "de", locale: { language: "de", number_format: "language" } });
    const card = await mount(hass);
    const snapshot = makeSnapshot({ zones: [makeZone({ thermostat: { ...makeZone().thermostat, current_temperature: 20.5 } })] });
    await deliver(card, hass.connection, snapshot);

    const values = [...root(card).querySelectorAll(".metric-value")].map((node) => node.textContent);
    expect(values).toEqual(["20,5", "21,0"]);
  });
});

describe("C14 more-info", () => {
  it("opens more-info for Hydronicus-owned entities", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const opened: string[] = [];
    card.addEventListener("hass-more-info", (event) => opened.push((event as CustomEvent<{ entityId: string }>).detail.entityId));

    root(card).querySelector<HTMLButtonElement>(".zone-title button")?.click();
    root(card).querySelector<HTMLButtonElement>(".plant-title button")?.click();

    expect(opened).toEqual(["climate.hydronic_living_room", "select.hydronic_mode"]);
  });
});

describe("C15 accessibility", () => {
  it("uses no page-level heading and no aria-label on generic elements", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot({
      delivery_paths: [{ id: "p", zone_id: "zone-1", circuit_id: "c", status: "active", problem: null, coupled: false, nodes: [{ kind: "zone", id: "zone-1", name: "Living room", state: "active" }] }],
    });
    await deliver(card, hass.connection, snapshot);

    expect(root(card).querySelector("h1")).toBeNull();
    const generic = [...root(card).querySelectorAll("div[aria-label], span[aria-label], p[aria-label]")].filter(
      (node) => !node.hasAttribute("role"),
    );
    expect(generic.map((node) => node.outerHTML)).toEqual([]);
    expect(root(card).querySelector("button.shutdown")?.hasAttribute("aria-pressed")).toBe(false);
  });
});

describe("C2 and C16 sizing", () => {
  it("lets the sections grid size the height and reports a realistic masonry size", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const options = card.getGridOptions();
    expect(options).not.toHaveProperty("rows");
    expect(options).not.toHaveProperty("min_rows");
    expect(options.columns).toBe(12);

    const loadingSize = card.getCardSize();
    const zones = Array.from({ length: 6 }, (_, index) => makeZone({ id: `zone-${index}`, name: `Zone ${index}` }));
    await deliver(card, hass.connection, makeSnapshot({ zones }));
    expect(loadingSize).toBeGreaterThanOrEqual(3);
    expect(card.getCardSize()).toBeGreaterThan(loadingSize);
    expect(card.getCardSize()).toBeGreaterThanOrEqual(15);
  });
});

describe("C9 configuration", () => {
  it("offers a built-in form and a prefilled stub config", async () => {
    const cardClass = customElements.get(TAG) as CardClass;
    const hass = makeHass();
    hass.connection.plants = [{ id: PLANT_ID, name: "Test plant" }, { id: OTHER_PLANT_ID, name: "Other" }];

    expect(await cardClass.getStubConfig(hass)).toEqual({ plant: PLANT_ID, density: "comfortable" });
    const form = await cardClass.getConfigForm();
    const plant = form.schema.find((field) => field.name === "plant");
    expect(plant).toMatchObject({
      required: true,
      selector: { select: { mode: "dropdown", options: [{ value: PLANT_ID, label: "Test plant" }, { value: OTHER_PLANT_ID, label: "Other" }] } },
    });
    expect(() => form.assertConfig?.({ type: `custom:${TAG}`, plant: PLANT_ID })).not.toThrow();
    expect(() => form.assertConfig?.({ type: `custom:${TAG}`, plant: { nested: true } })).toThrow();
    expect("getConfigElement" in cardClass).toBe(false);
  });

  it("shows the Plant name instead of its UUID in the editor", async () => {
    // With `custom_value`, Home Assistant renders a combo box that shows the
    // raw value. A plain dropdown shows the label of the matching option,
    // and a UUID that is not listed, for example from YAML, as itself.
    const cardClass = customElements.get(TAG) as CardClass;
    const hass = makeHass();
    hass.connection.plants = [{ id: PLANT_ID, name: "Hydronic plant" }];
    await cardClass.getStubConfig(hass);
    const form = await cardClass.getConfigForm();
    const plant = form.schema.find((field) => field.name === "plant") as { selector: { select: Record<string, unknown> } };
    expect(plant.selector.select.custom_value).toBeFalsy();
    expect(plant.selector.select.options).toEqual([{ value: PLANT_ID, label: "Hydronic plant" }]);
  });

  it("falls back to free text input when no Plant can be listed", async () => {
    const cardClass = customElements.get(TAG) as CardClass;
    const hass = makeHass();
    hass.connection.plants = [];
    await cardClass.getStubConfig(hass);
    const form = await cardClass.getConfigForm();
    expect(form.schema.find((field) => field.name === "plant")).toMatchObject({ required: true, selector: { text: {} } });
  });

  it("keeps existing plant UUID YAML working and rejects invalid config", async () => {
    const hass = makeHass();
    const card = await mount(hass, { plant: PLANT_ID, density: "compact" });
    expect(hass.connection.last.message).toEqual({ type: "hydronicus/subscribe_plant", plant_id: PLANT_ID });
    expect(() => card.setConfig({ type: `custom:${TAG}` })).toThrow();
    expect(() => card.setConfig({ type: `custom:${TAG}`, plant: PLANT_ID, density: "huge" })).toThrow();
  });

  it("shows a setup prompt for an empty stub instead of an error", async () => {
    const hass = makeHass();
    const card = await mount(hass, { plant: "" });
    expect(hass.connection.subscriptions).toHaveLength(0);
    expect(text(card)).toContain("Select a Hydronicus Plant");
  });
});

describe("C10 double loading", () => {
  it("does not throw when the bundle is evaluated twice", async () => {
    vi.resetModules();
    await expect(import("../src/index")).resolves.toBeDefined();
    const entries = (window.customCards ?? []).filter((card) => card.type === TAG);
    expect(entries).toHaveLength(1);
  });
});
