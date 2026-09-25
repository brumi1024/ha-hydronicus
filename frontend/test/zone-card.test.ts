import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../src/index";
import { plantDirectory } from "../src/config";
import { FakeConnection, makeHass, makeSnapshot, makeZone, OTHER_PLANT_ID, PLANT_ID, settle, type FakeHass } from "./fixtures";

type CardElement = HTMLElement & {
  hass?: unknown;
  setConfig(config: Record<string, unknown>): void;
  getCardSize(): number;
  getGridOptions(): Record<string, unknown>;
  updateComplete: Promise<boolean>;
};

type ZoneCardClass = CustomElementConstructor & {
  getConfigElement(): HTMLElement;
  getStubConfig(hass: unknown): Promise<Record<string, unknown>>;
};

type EditorElement = HTMLElement & {
  hass?: unknown;
  setConfig(config: Record<string, unknown>): void;
  updateComplete: Promise<boolean>;
};

type FormElement = HTMLElement & { schema: Array<Record<string, unknown>>; data: Record<string, unknown> };

const TAG = "hydronicus-zone-card";
const PLANT_TAG = "hydronicus-plant-card";
const TYPE = `custom:${TAG}`;

async function mount(hass: FakeHass | undefined, config: Record<string, unknown> = {}): Promise<CardElement> {
  const card = document.createElement(TAG) as CardElement;
  card.setConfig({ type: TYPE, plant: PLANT_ID, zone: "zone-1", ...config });
  if (hass) card.hass = hass;
  document.body.append(card);
  await settle(card);
  return card;
}

function root(element: HTMLElement): ShadowRoot {
  if (!element.shadowRoot) throw new Error("The element has no shadow root.");
  return element.shadowRoot;
}

function text(card: CardElement): string {
  return (root(card).textContent ?? "").replace(/\s+/g, " ");
}

async function deliver(card: CardElement, connection: FakeConnection, snapshot = makeSnapshot()): Promise<void> {
  connection.last.emit({ snapshot });
  await settle(card);
}

/** Element markup without Lit's comment markers and whitespace-only text. */
function markup(element: Element): string {
  return element.outerHTML.replace(/<!--[^]*?-->/g, "").replace(/>\s+</g, "><");
}

beforeEach(() => {
  document.body.replaceChildren();
  plantDirectory.reset();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

describe("Zone card rendering", () => {
  it("renders the same Zone tile as the Plant card, as a card of its own", async () => {
    const hass = makeHass();
    const zones = [makeZone(), makeZone({ id: "zone-2", name: "Bath", coupling_group_ids: ["g"], cooling: { ...makeZone().cooling, dew_point: 12, condensation_margin: 3 } })];
    const plant = document.createElement(PLANT_TAG) as CardElement;
    plant.setConfig({ type: `custom:${PLANT_TAG}`, plant: PLANT_ID });
    plant.hass = hass;
    document.body.append(plant);
    const card = await mount(hass, { zone: "zone-2" });
    await deliver(card, hass.connection, makeSnapshot({ zones }));
    await settle(plant);

    expect(hass.connection.subscriptions).toHaveLength(1);
    const tile = root(card).querySelector("ha-card.zone-card > article.zone");
    const inPlant = [...root(plant).querySelectorAll(".zone-grid > article.zone")][1];
    if (!tile || !inPlant) throw new Error("A Zone tile is missing.");
    // Only the heading level differs: the Zone card's heading is its first.
    expect(markup(tile)).toBe(markup(inPlant).replaceAll("<h4 ", "<h2 ").replaceAll("</h4>", "</h2>"));
    expect(tile.querySelector("h2.zone-title")?.textContent).toBe("Bath");
    expect(root(card).querySelector("h1, h3, h4")).toBeNull();
  });

  it("uses the Zone's own demand for the card state", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection, makeSnapshot({ zones: [makeZone({ demand: false, cooling: { ...makeZone().cooling, demand: true } })] }));
    expect(root(card).querySelector("ha-card")?.getAttribute("data-visual")).toBe("cooling");

    await deliver(card, hass.connection, makeSnapshot({ zones: [makeZone({ blocked: true })] }));
    expect(root(card).querySelector("ha-card")?.getAttribute("data-visual")).toBe("attention");
  });

  it("applies the density", async () => {
    const hass = makeHass();
    const card = await mount(hass, { density: "compact" });
    await deliver(card, hass.connection);
    expect(root(card).querySelector("ha-card")?.classList.contains("compact")).toBe(true);
  });
});

describe("Zone card controls", () => {
  it("sets the HVAC mode, target, and preset of the Zone's climate entity", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    root(card).querySelector<HTMLButtonElement>(".hvac-mode[data-mode='off']")?.click();
    root(card).querySelector<HTMLButtonElement>(".zone-actions button:nth-of-type(2)")?.click();
    const preset = root(card).querySelector<HTMLSelectElement>("select.preset");
    if (!preset) throw new Error("No preset control.");
    expect(preset.value).toBe("comfort");
    preset.value = "eco";
    preset.dispatchEvent(new Event("change"));
    await settle(card);

    const entity_id = "climate.hydronic_living_room";
    expect(hass.calls).toEqual([
      { domain: "climate", service: "set_hvac_mode", data: { entity_id, hvac_mode: "off" }, notifyOnError: false },
      { domain: "climate", service: "set_temperature", data: { entity_id, temperature: 21.5 }, notifyOnError: false },
      { domain: "climate", service: "set_preset_mode", data: { entity_id, preset_mode: "eco" }, notifyOnError: false },
    ]);
  });

  it("opens more-info for the Zone's climate entity", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const opened: string[] = [];
    card.addEventListener("hass-more-info", (event) => opened.push((event as CustomEvent<{ entityId: string }>).detail.entityId));

    root(card).querySelector<HTMLButtonElement>(".zone-title button")?.click();

    expect(opened).toEqual(["climate.hydronic_living_room"]);
  });

  it("shows a failed action inline and reverts the preset", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    hass.failNextCall = "Entity is unavailable.";

    const preset = root(card).querySelector<HTMLSelectElement>("select.preset");
    if (!preset) throw new Error("No preset control.");
    preset.value = "eco";
    preset.dispatchEvent(new Event("change"));
    await settle(card);

    expect(root(card).querySelector(".action-error")?.textContent).toContain("Entity is unavailable.");
    expect(root(card).querySelector<HTMLSelectElement>("select.preset")?.value).toBe("comfort");
    root(card).querySelector<HTMLButtonElement>(".action-error button")?.click();
    await settle(card);
    expect(root(card).querySelector(".action-error")).toBeNull();
  });

  it("keeps an external thermostat read-only", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const zone = makeZone();
    await deliver(card, hass.connection, makeSnapshot({ zones: [{ ...zone, thermostat: { ...zone.thermostat, kind: "external_climate", control_entity_id: null, hvac_modes: [] } }] }));

    expect(root(card).querySelector(".hvac-modes, .zone-actions")).toBeNull();
    expect(text(card)).toContain("Adjust this thermostat in its owning Home Assistant integration.");
  });
});

describe("Zone card states", () => {
  it.each([
    [{ plant: "" }, "Select a Hydronicus Plant and a Zone"],
    [{ zone: "" }, "Select a Zone in the card editor"],
  ])("prompts for setup with %j without subscribing", async (config, message) => {
    const hass = makeHass();
    const card = await mount(hass, config);
    expect(text(card)).toContain(message);
    expect(hass.connection.subscriptions).toHaveLength(0);
  });

  it("shows loading until the first snapshot", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    expect(root(card).querySelector("[aria-busy='true']")).not.toBeNull();
    await deliver(card, hass.connection);
    expect(root(card).querySelector("[aria-busy='true']")).toBeNull();
  });

  it("shows Zone not found when the snapshot has no such Zone", async () => {
    const hass = makeHass();
    const card = await mount(hass, { zone: "zone-9" });
    await deliver(card, hass.connection);

    expect(root(card).querySelector("h2")?.textContent).toBe("Zone not found");
    expect(root(card).querySelector("[role='alert']")?.textContent).toContain("do not have access to it");
    expect(root(card).querySelector("button")).toBeNull();
  });

  it.each([
    ["plant_not_found", "Plant not found"],
    ["unauthorized", "No access"],
  ])("shows a terminal state for %s", async (status, title) => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    hass.connection.last.emit({ status, plant_id: PLANT_ID });
    await settle(card);

    expect(root(card).querySelector("h2")?.textContent).toBe(title);
    expect(root(card).querySelector(".eyebrow")?.textContent).toBe("Hydronicus Zone");
    expect(root(card).querySelector(".zone")).toBeNull();
  });

  it("hides the controls while the Plant is unavailable", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    hass.connection.last.emit({ status: "unavailable", plant_id: PLANT_ID });
    await settle(card);
    expect(root(card).querySelector("h2")?.textContent).toBe("Plant unavailable");
    expect(root(card).querySelector("button")).toBeNull();

    await deliver(card, hass.connection);
    expect(root(card).querySelector(".zone")).not.toBeNull();
  });

  it("keeps the Zone with a notice while reconnecting", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);

    hass.connection.fire("disconnected");
    await settle(card);

    expect(root(card).querySelector(".notice")?.textContent).toContain("Reconnecting");
    expect(root(card).querySelector(".zone")).not.toBeNull();
  });

  it("asks for a reload on an unsupported snapshot", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection, { ...makeSnapshot(), schema_version: 99 });
    expect(text(card)).toContain("Card update needed");
  });

  it("follows another Plant and Zone from a new config", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    await deliver(card, hass.connection);
    const first = hass.connection.last;

    card.setConfig({ type: TYPE, plant: OTHER_PLANT_ID, zone: "zone-1" });
    await settle(card);

    expect(first.unsubscribed).toBe(true);
    expect(hass.connection.last.message).toEqual({ type: "hydronicus/subscribe_plant", plant_id: OTHER_PLANT_ID });
    expect(root(card).querySelector(".zone")).toBeNull();
  });
});

describe("Zone card configuration", () => {
  it("validates its config", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    expect(() => card.setConfig({ type: TYPE })).toThrow();
    expect(() => card.setConfig({ type: TYPE, plant: PLANT_ID, zone: 3 })).toThrow();
    expect(() => card.setConfig({ type: TYPE, plant: PLANT_ID, zone: "zone-1", density: "huge" })).toThrow();
    expect(() => card.setConfig({ type: `custom:${PLANT_TAG}`, plant: PLANT_ID, zone: "zone-1" })).toThrow();
    expect(() => card.setConfig({ type: TYPE, plant: PLANT_ID })).not.toThrow();
  });

  it("sizes like a thermostat card in a Sections view", async () => {
    const card = await mount(makeHass());
    expect(card.getGridOptions()).toEqual({ columns: 6, min_columns: 4 });
    expect(card.getGridOptions()).not.toHaveProperty("rows");
    expect(card.getCardSize()).toBe(5);
  });

  it("prefills the first readable Plant and its first Zone", async () => {
    const cardClass = customElements.get(TAG) as ZoneCardClass;
    const hass = makeHass();
    hass.connection.plants = [{ id: PLANT_ID, name: "Test plant" }];
    const pending = cardClass.getStubConfig(hass);
    await vi.waitFor(() => expect(hass.connection.subscriptions).toHaveLength(1));
    hass.connection.last.emit({ snapshot: makeSnapshot({ zones: [makeZone({ id: "zone-7" })] }) });

    expect(await pending).toEqual({ plant: PLANT_ID, zone: "zone-7", density: "comfortable" });
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(true);
  });

  it("prefills an empty stub without a readable Plant", async () => {
    const cardClass = customElements.get(TAG) as ZoneCardClass;
    const hass = makeHass();
    expect(await cardClass.getStubConfig(hass)).toEqual({ plant: "", zone: "", density: "comfortable" });
    expect(hass.connection.subscriptions).toHaveLength(0);
  });
});

describe("Zone card editor", () => {
  async function openEditor(hass: FakeHass, config: Record<string, unknown>): Promise<{ editor: EditorElement; form: () => FormElement }> {
    const editor = (customElements.get(TAG) as ZoneCardClass).getConfigElement() as EditorElement;
    editor.setConfig({ type: TYPE, ...config });
    editor.hass = hass;
    document.body.append(editor);
    await settle(editor);
    const form = () => {
      const element = root(editor).querySelector("ha-form");
      if (!element) throw new Error("No ha-form.");
      return element as FormElement;
    };
    return { editor, form };
  }

  function field(form: FormElement, name: string): Record<string, unknown> {
    const entry = form.schema.find((candidate) => candidate.name === name);
    if (!entry) throw new Error(`No ${name} field.`);
    return entry;
  }

  it("is a registered custom element", () => {
    const editor = (customElements.get(TAG) as ZoneCardClass).getConfigElement();
    expect(editor.tagName.toLowerCase()).toBe("hydronicus-zone-card-editor");
    expect(customElements.get("hydronicus-zone-card-editor")).toBeDefined();
  });

  it("lists the Plants by name and the chosen Plant's Zones by name", async () => {
    const hass = makeHass();
    hass.connection.plants = [{ id: PLANT_ID, name: "Test plant" }, { id: OTHER_PLANT_ID, name: "Other" }];
    const { editor, form } = await openEditor(hass, { plant: PLANT_ID, zone: "zone-2", grid_options: { columns: 3 } });
    // Without a snapshot yet, the Zone is free text.
    expect(field(form(), "zone")).toMatchObject({ required: true, selector: { text: {} } });

    hass.connection.last.emit({ snapshot: makeSnapshot({ zones: [makeZone(), makeZone({ id: "zone-2", name: "Bath" })] }) });
    await settle(editor);

    expect(field(form(), "plant")).toMatchObject({
      required: true,
      selector: { select: { mode: "dropdown", options: [{ value: PLANT_ID, label: "Test plant" }, { value: OTHER_PLANT_ID, label: "Other" }] } },
    });
    expect(field(form(), "zone")).toMatchObject({
      required: true,
      selector: { select: { mode: "dropdown", options: [{ value: "zone-1", label: "Living room" }, { value: "zone-2", label: "Bath" }] } },
    });
    expect(form().data).toMatchObject({ plant: PLANT_ID, zone: "zone-2", grid_options: { columns: 3 } });
  });

  it("reports Zone changes and keeps keys the card does not read", async () => {
    const hass = makeHass();
    const { editor, form } = await openEditor(hass, { plant: PLANT_ID, zone: "zone-1", grid_options: { columns: 3 } });
    const changes: Array<Record<string, unknown>> = [];
    editor.addEventListener("config-changed", (event) => changes.push((event as CustomEvent<{ config: Record<string, unknown> }>).detail.config));

    form().dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form().data, zone: "zone-2" } } }));

    expect(changes).toEqual([{ type: TYPE, plant: PLANT_ID, zone: "zone-2", grid_options: { columns: 3 } }]);
  });

  it("clears the Zone and lists the new Plant's Zones when the Plant changes", async () => {
    const hass = makeHass();
    const { editor, form } = await openEditor(hass, { plant: PLANT_ID, zone: "zone-1" });
    hass.connection.last.emit({ snapshot: makeSnapshot() });
    await settle(editor);
    const first = hass.connection.last;
    const changes: Array<Record<string, unknown>> = [];
    editor.addEventListener("config-changed", (event) => changes.push((event as CustomEvent<{ config: Record<string, unknown> }>).detail.config));

    form().dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form().data, plant: OTHER_PLANT_ID } } }));
    await settle(editor);

    expect(changes).toEqual([{ type: TYPE, plant: OTHER_PLANT_ID, zone: "" }]);
    expect(first.unsubscribed).toBe(true);
    expect(hass.connection.last.message).toEqual({ type: "hydronicus/subscribe_plant", plant_id: OTHER_PLANT_ID });
    expect(field(form(), "zone")).toMatchObject({ selector: { text: {} } });
  });

  it("shares the Plant subscription with the card preview and releases it on close", async () => {
    const hass = makeHass();
    const card = await mount(hass);
    const { editor } = await openEditor(hass, { plant: PLANT_ID, zone: "zone-1" });
    expect(hass.connection.subscriptions).toHaveLength(1);

    card.remove();
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(false);
    editor.remove();
    await settle();
    expect(hass.connection.last.unsubscribed).toBe(true);
  });

  it("rejects an invalid config so Home Assistant offers YAML", async () => {
    const editor = (customElements.get(TAG) as ZoneCardClass).getConfigElement() as EditorElement;
    expect(() => editor.setConfig({ type: TYPE, plant: PLANT_ID, density: "huge" })).toThrow();
  });
});
