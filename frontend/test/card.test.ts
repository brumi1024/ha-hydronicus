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

describe("Room HVAC mode", () => {
  function modeButtons(card: CardElement): HTMLButtonElement[] {
    return [...root(card).querySelectorAll<HTMLButtonElement>(".hvac-modes button")];
  }

  it("shows an Off Room as Off and turns heating on with one tap", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone({ demand: false, phase: "idle" });
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, hvac_mode: "off" } }] }));

    const group = root(card).querySelector(".hvac-modes");
    expect(group?.getAttribute("role")).toBe("group");
    expect(group?.getAttribute("aria-label")).toBe("Living room HVAC mode");
    const buttons = modeButtons(card);
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(["Off", "Heat"]);
    expect(buttons.map((button) => button.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
    expect(root(card).querySelector(".zone .phase")?.textContent?.trim()).toBe("Off");
    expect(root(card).querySelector(".zone-note")?.textContent).toContain("Thermostat off");

    buttons[0].click();
    buttons[1].click();
    await settle(card);

    // Choosing the current mode sends nothing.
    expect(hass.calls).toEqual([
      { domain: "climate", service: "set_hvac_mode", data: { entity_id: "climate.hydronic_living_room", hvac_mode: "heat" }, notifyOnError: false },
    ]);
  });

  it("offers cooling modes only when the Room's climate entity supports them", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, hvac_mode: "cool", hvac_modes: ["off", "heat", "cool", "heat_cool"] } }] }));

    expect(modeButtons(card).map((button) => button.dataset.mode)).toEqual(["off", "heat", "cool", "heat_cool"]);
    expect(root(card).querySelector(".hvac-mode[aria-pressed='true']")?.textContent?.trim()).toBe("Cool");
  });

  it("keeps an external thermostat read-only and shows its mode", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, kind: "external_climate", control_entity_id: null, hvac_mode: "heat", hvac_modes: [] } }] }));

    expect(root(card).querySelector(".hvac-modes")).toBeNull();
    expect(root(card).querySelector(".zone-owner")?.textContent).toContain("External thermostat · read-only · Heat");
  });

  it("disables the mode control when the climate entity is hidden", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, control_entity_id: null } }] }));

    expect(modeButtons(card).every((button) => button.disabled)).toBe(true);
  });
});

describe("Header", () => {
  it("hides the source line when the Plant has no sources", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    expect(root(card).querySelector(".source-line")).toBeNull();
    expect(text(card)).not.toContain("recommended");
  });

  it("shows the source line when the Plant has sources", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot({ sources: [{ id: "boiler" }] });
    snapshot.plant.source = { active_id: "boiler", active_name: "Boiler", recommended_id: "heat-pump", recommended_name: "Heat pump" };
    await deliver(card, hass.connection, snapshot);

    expect(root(card).querySelector(".source-line")?.textContent?.replace(/\s+/g, " ").trim()).toBe("Source Boiler · recommended Heat pump");
  });

  it("reads the requested mode naturally", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot();
    await deliver(card, hass.connection, makeSnapshot({ plant: { ...snapshot.plant, status: "idle", requested_mode: "auto", active_mode: "idle" } }));

    expect(root(card).querySelector(".mode-detail")?.textContent?.trim()).toBe("Mode Auto");
  });

  it("labels the boundary in sentence case and keeps safe shutdown available but quiet in Dry run", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    expect(root(card).querySelector(".badge")?.textContent).toContain("Dry run");
    const shutdown = root(card).querySelector<HTMLButtonElement>("button.shutdown");
    expect(shutdown?.classList.contains("quiet")).toBe(true);
    expect(shutdown?.disabled).toBe(false);
    expect(shutdown?.getAttribute("aria-describedby")).toBe("shutdown-hint");
  });

  it("marks outputs as live when nothing is forced to shadow", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot();
    const message = "Control enabled - heating and cooling outputs may execute.";
    await deliver(card, hass.connection, makeSnapshot({ plant: { ...snapshot.plant, execution_boundary: { mode: "mixed", dry_run: false, forced_shadow: [], message } } }));

    expect(root(card).querySelector(".badge.live")?.textContent).toContain("Live");
    expect(root(card).querySelector(".boundary-copy")?.textContent).toContain(message);
    expect(root(card).querySelector("button.shutdown")?.classList.contains("quiet")).toBe(false);
  });
});

describe("Room and Loop wording", () => {
  it("uses Room and Loop instead of Zone and Circuit", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const snapshot = makeSnapshot({
      zones: [makeZone({ coupling_group_ids: ["group-1"] })],
      delivery_paths: [{ id: "p", zone_id: "zone-1", circuit_id: "c", status: "active", problem: null, coupled: true, nodes: [{ kind: "zone", id: "zone-1", name: "Living room", state: "active" }, { kind: "circuit", id: "c", name: "Floor loop", state: "active" }] }],
      actuators: [
        { id: "a", name: "Pump", kind: "pump", state: "idle", requested: null, observed: "off", ready: true, blocked: false, mismatch: false, reason: "Waiting.", active_consumers: [] },
        { id: "b", name: "Valve", kind: "valve", state: "open", requested: null, observed: "on", ready: true, blocked: false, mismatch: false, reason: null, active_consumers: [{ id: "c", name: "Floor loop" }] },
      ],
    });
    await deliver(card, hass.connection, snapshot);

    const content = text(card);
    for (const phrase of ["Rooms", "Room → Loop → Valve → Pump → Source", "Equipment", "No loop is using this right now.", "this Room shares hydraulic equipment"]) {
      expect(content).toContain(phrase);
    }
    expect([...root(card).querySelectorAll(".node-kind")].map((node) => node.textContent)).toEqual(["Room", "Loop"]);
    expect(root(card).querySelector(".consumer-list")?.getAttribute("aria-label")).toBe("Loops using this equipment");
    expect(root(card).querySelector(".diagnostic-list")?.getAttribute("aria-label")).toBe("Room diagnostics");
    expect(content).not.toMatch(/\bZones?\b|\bCircuits?\b|circuit consumers|Actuator Ownership/);
  });

  it("uses Room wording for an empty Plant", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection, makeSnapshot({ zones: [] }));

    expect(text(card)).toContain("No Rooms are visible for this Plant.");
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

    expect(root(card).querySelector(".status-primary")?.textContent).toContain("Safe shutdown");
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

describe("Shared Plant subscription", () => {
  it("shares one subscription between cards for the same Plant", async () => {
    const hass = makeHass();
    const first = await mount(hass);
    const second = await mount(hass, { sections: ["rooms"] });
    expect(hass.connection.subscriptions).toHaveLength(1);

    await deliver(first, hass.connection);
    await settle(second);
    expect(text(first)).toContain("Test plant");
    expect(root(second).querySelector(".zone")).not.toBeNull();

    first.remove();
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(false);
    second.remove();
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(true);
  });

  it("keeps the subscription when a card moves within the page", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const other = document.createElement("div");
    document.body.append(other);

    other.append(card);
    await settle(card);

    expect(hass.connection.subscriptions).toHaveLength(1);
    expect(hass.connection.last.unsubscribed).toBe(false);
    expect(text(card)).toContain("Test plant");
  });

  it("keeps an action error on the card whose control failed", async () => {
    const hass = makeHass();
    const first = await mount(hass);
    const second = await mount(hass);
    await deliver(first, hass.connection);
    await settle(second);
    hass.failNextCall = "Entity is unavailable.";

    root(first).querySelector<HTMLButtonElement>(".zone-actions button")?.click();
    await settle(first);
    await settle(second);

    expect(root(first).querySelector(".action-error")).not.toBeNull();
    expect(root(second).querySelector(".action-error")).toBeNull();
  });
});

describe("Plant card sections", () => {
  function richSnapshot() {
    return makeSnapshot({
      alerts: [{ code: "stale", severity: "warning", priority: 1, scope: "plant", message: "Sensor is stale." }],
      delivery_paths: [{ id: "p", zone_id: "zone-1", circuit_id: "c", status: "active", problem: null, coupled: false, nodes: [{ kind: "zone", id: "zone-1", name: "Living room", state: "active" }] }],
      actuators: [{ id: "a", name: "Pump", kind: "pump", state: "idle", requested: null, observed: "off", ready: true, blocked: false, mismatch: false, reason: null, active_consumers: [] }],
      explanations: [{ order: 1, scope: "plant", code: "x", message: "Why." }],
      execution: { boundary: {}, operations: { proposed: [{ action: "open", actuator_name: "Valve", result: "proposed" }], executed: [], suppressed: [], failed: [], timed_out: [] } },
    });
  }

  /** The shown sections in document order, by their distinctive element. */
  function shown(card: CardElement): string[] {
    const markers: Array<[string, string]> = [
      ["header", "header.header"],
      ["alerts", "[aria-labelledby='hydronicus-alerts']"],
      ["rooms", "[aria-labelledby='hydronicus-zones']"],
      ["paths", "[aria-labelledby='hydronicus-paths']"],
      ["equipment", "[aria-labelledby='hydronicus-actuators']"],
      ["explanations", "details:not([open])"],
      ["operations", "details[open]"],
    ];
    const found = markers
      .map(([name, selector]) => [name, root(card).querySelector(selector)] as const)
      .filter((entry): entry is readonly [string, Element] => entry[1] !== null);
    return found
      .sort(([, left], [, right]) => (left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
      .map(([name]) => name);
  }

  it("shows every section in the default order without `sections`", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection, richSnapshot());

    expect(shown(card)).toEqual(["header", "alerts", "rooms", "paths", "equipment", "explanations", "operations"]);
    expect(root(card).querySelector(".boundary")).not.toBeNull();
  });

  it("shows only the configured sections, in the configured order", async () => {
    const hass = makeHass();
    const card = await mount(hass, { sections: ["rooms", "alerts"] });
    await deliver(card, hass.connection, richSnapshot());

    expect(shown(card)).toEqual(["rooms", "alerts"]);
    // The execution boundary belongs to the header section.
    expect(root(card).querySelector(".boundary")).toBeNull();
    expect(root(card).querySelector("button.shutdown")).toBeNull();
  });

  it("keeps stream notices and action errors visible without the header", async () => {
    const hass = makeHass();
    const card = await mount(hass, { sections: ["rooms"] });
    await deliver(card, hass.connection);
    hass.failNextCall = "Entity is unavailable.";

    root(card).querySelector<HTMLButtonElement>(".zone-actions button")?.click();
    await settle(card);
    hass.connection.fire("disconnected");
    await settle(card);

    const first = root(card).querySelector("ha-card")?.firstElementChild;
    expect(first?.classList.contains("notice")).toBe(true);
    expect(root(card).querySelector(".action-error")?.textContent).toContain("Entity is unavailable.");
  });

  it("validates `sections`", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    for (const sections of [["rooms", "rooms"], ["zones"], "rooms", [1]]) {
      expect(() => card.setConfig({ type: `custom:${TAG}`, plant: PLANT_ID, sections }), JSON.stringify(sections)).toThrow();
    }
    // The visual editor clears every choice to an empty list: every section.
    card.setConfig({ type: `custom:${TAG}`, plant: PLANT_ID, sections: [] });
    await deliver(card, hass.connection, richSnapshot());
    expect(shown(card)).toHaveLength(7);
  });

  it("offers the sections as an ordered choice in the editor", async () => {
    const form = await (customElements.get(TAG) as CardClass).getConfigForm();
    const field = form.schema.find((entry) => entry.name === "sections") as { selector: { select: Record<string, unknown> } };
    expect(field.selector.select).toMatchObject({ multiple: true, reorder: true });
    expect((field.selector.select.options as Array<{ value: string }>).map((option) => option.value)).toEqual([
      "header", "alerts", "rooms", "paths", "equipment", "explanations", "operations",
    ]);
    expect(() => form.assertConfig?.({ type: `custom:${TAG}`, plant: PLANT_ID, sections: ["header"] })).not.toThrow();
    expect(() => form.assertConfig?.({ type: `custom:${TAG}`, plant: PLANT_ID, sections: ["nope"] })).toThrow();
    expect(form.computeLabel?.({ name: "sections" })).toBe("Sections");
  });

  it("sizes the card for the shown sections", async () => {
    const hass = makeHass();
    const full = await mount(hass);
    const header = await mount(hass, { sections: ["header"] });
    const rooms = await mount(hass, { sections: ["rooms"] });
    await deliver(full, hass.connection, richSnapshot());
    await settle(header);
    await settle(rooms);

    expect(header.getCardSize()).toBe(4);
    expect(rooms.getCardSize()).toBe(6);
    expect(full.getCardSize()).toBeGreaterThan(header.getCardSize() + rooms.getCardSize());
    expect(full.getGridOptions()).toEqual({ columns: 12, min_columns: 6 });
    expect(rooms.getGridOptions()).toEqual({ columns: 12, min_columns: 6 });
    expect(header.getGridOptions()).toEqual({ columns: 6, min_columns: 4 });
  });
});
