import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import "../src/index";
import { cardStyles } from "../src/styles";
import { makeHass, makeSnapshot, PLANT_ID, settle, type FakeConnection } from "./fixtures";

/** The theme token contract shared with themes that map it. */
const CONTRACT_TOKENS = [
  "--hydronicus-surface",
  "--hydronicus-surface-raised",
  "--hydronicus-text",
  "--hydronicus-text-muted",
  "--hydronicus-line",
  "--hydronicus-accent",
  "--hydronicus-heating-color",
  "--hydronicus-cooling-color",
  "--hydronicus-idle-color",
  "--hydronicus-attention-color",
  "--hydronicus-success-color",
  "--hydronicus-warning-color",
  "--hydronicus-danger-color",
  "--hydronicus-radius",
  "--hydronicus-radius-inner",
  "--hydronicus-radius-control",
  "--hydronicus-card-border",
  "--hydronicus-card-shadow",
  "--hydronicus-tile-border",
  "--hydronicus-tile-shadow",
  "--hydronicus-tile-active-border",
  "--hydronicus-tile-active-shadow",
  "--hydronicus-control-border",
  "--hydronicus-control-shadow",
  "--hydronicus-control-surface",
  "--hydronicus-control-color",
  "--hydronicus-selected-background",
  "--hydronicus-selected-color",
  "--hydronicus-font-body",
  "--hydronicus-font-display",
  "--hydronicus-font-weight-display",
  "--hydronicus-ambient-opacity",
  "--hydronicus-glass-blur",
  "--hydronicus-glass-opacity",
  "--hydronicus-flow-duration",
  "--hydronicus-ambient-duration",
];

const css = cardStyles.cssText;
// Vitest runs from the frontend directory.
const docs = readFileSync(resolve(process.cwd(), "../docs/lovelace.md"), "utf8");

/** The first backticked cell of each row of the table under a docs heading. */
function documentedNames(heading: string): string[] {
  const start = docs.indexOf(`\n${heading}\n`);
  if (start < 0) throw new Error(`docs/lovelace.md has no "${heading}" heading.`);
  const rest = docs.slice(start + heading.length + 2);
  const end = rest.search(/\n#{2,4} /);
  const section = end < 0 ? rest : rest.slice(0, end);
  return [...section.matchAll(/^\| `([^`]+)` \|/gm)].map((match) => match[1]);
}

function sorted(values: Iterable<string>): string[] {
  return [...new Set(values)].sort();
}

/** Every public token the stylesheet reads, with whether that read has a fallback. */
function publicReads(): Array<{ token: string; fallback: boolean }> {
  return [...css.matchAll(/var\(\s*(--hydronicus-[\w-]+)\s*([,)])/g)].map((match) => ({ token: match[1], fallback: match[2] === "," }));
}

describe("theme token contract", () => {
  it("never declares a public token, so an inherited theme value is not shadowed", () => {
    expect(css.match(/(?<![\w-])--hydronicus-[\w-]+\s*:/g)).toBeNull();
  });

  it("reads every public token with a fallback", () => {
    const reads = publicReads();
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.filter((read) => !read.fallback).map((read) => read.token)).toEqual([]);
  });

  it("reads exactly the contract tokens", () => {
    expect(sorted(publicReads().map((read) => read.token))).toEqual(sorted(CONTRACT_TOKENS));
  });

  it("documents exactly the tokens it reads", () => {
    expect(sorted(documentedNames("### Theme tokens"))).toEqual(sorted(CONTRACT_TOKENS));
  });

  it("declares every private property it reads", () => {
    const declared = new Set([...css.matchAll(/(--_hy-[\w-]+)\s*:/g)].map((match) => match[1]));
    const read = sorted([...css.matchAll(/var\(\s*(--_hy-[\w-]+)/g)].map((match) => match[1]));
    expect(read.filter((name) => !declared.has(name))).toEqual([]);
  });

  it("does not paint an ambient glow by default", () => {
    expect(css).toContain("--_hy-ambient-opacity: var(--hydronicus-ambient-opacity, 0);");
  });

  it("does not animate the card in, like stock Home Assistant cards", () => {
    expect(css).not.toMatch(/card-enter/);
    expect(css).not.toMatch(/ha-card \{[^}]*animation:/);
  });
});

type CardElement = HTMLElement & { hass?: unknown; setConfig(config: Record<string, unknown>): void; updateComplete: Promise<boolean> };

function richSnapshot() {
  return makeSnapshot({
    alerts: [{ code: "stale", severity: "warning", priority: 1, scope: "plant", message: "Sensor is stale." }],
    delivery_paths: [{ id: "p", zone_id: "zone-1", circuit_id: "c", status: "active", problem: null, coupled: false, nodes: [{ kind: "zone", id: "zone-1", name: "Living room", state: "active" }, { kind: "circuit", id: "c", name: "Floor loop", state: "active" }] }],
    actuators: [{ id: "a", name: "Pump", kind: "pump", state: "active", requested: null, observed: "on", ready: true, blocked: false, mismatch: false, reason: null, active_consumers: [{ id: "c", name: "Floor loop" }] }],
    explanations: [{ order: 1, scope: "plant", code: "x", message: "Why." }],
    execution: { boundary: {}, operations: { proposed: [{ action: "open", actuator_name: "Valve", result: "proposed" }], executed: [], suppressed: [], failed: [], timed_out: [] } },
  });
}

async function mount(tag: string, config: Record<string, unknown>, parent: HTMLElement = document.body): Promise<CardElement> {
  const hass = makeHass();
  const card = document.createElement(tag) as CardElement;
  card.setConfig({ type: `custom:${tag}`, plant: PLANT_ID, ...config });
  card.hass = hass;
  parent.append(card);
  await settle(card);
  (hass.connection as FakeConnection).last.emit({ snapshot: richSnapshot() });
  await settle(card);
  return card;
}

function shadow(card: HTMLElement): ShadowRoot {
  if (!card.shadowRoot) throw new Error("The card has no shadow root.");
  return card.shadowRoot;
}

/** The part names of an element and its descendants, in document order. */
function parts(root: ParentNode & Node): string[] {
  const own = root instanceof Element && root.hasAttribute("part") ? [root] : [];
  return [...own, ...root.querySelectorAll("[part]")].flatMap((element) => (element.getAttribute("part") ?? "").split(/\s+/));
}

beforeEach(() => {
  document.body.replaceChildren();
});

afterEach(() => {
  document.body.replaceChildren();
  document.documentElement.removeAttribute("style");
});

describe("theme parts", () => {
  it("exposes exactly the documented parts from the Plant card", async () => {
    const card = await mount("hydronicus-plant-card", {});
    expect(sorted(parts(shadow(card)))).toEqual(sorted(documentedNames("### Parts")));
  });

  it("gives the Room card's tile the same parts as the Room in the Plant card", async () => {
    const plant = await mount("hydronicus-plant-card", {});
    const room = await mount("hydronicus-room-card", { room: "zone-1" });
    const inPlant = shadow(plant).querySelector("article.zone");
    const tile = shadow(room).querySelector("article.zone");
    if (!inPlant || !tile) throw new Error("A Room tile is missing.");
    expect(parts(tile)).toEqual(parts(inPlant));
    expect(parts(tile)).toContain("room-title");
    expect(shadow(room).querySelector("ha-card")?.getAttribute("part")).toBe("card");
  });

  it("marks the frame of state cards as the card part", async () => {
    const card = document.createElement("hydronicus-room-card") as CardElement;
    card.setConfig({ type: "custom:hydronicus-room-card", plant: PLANT_ID });
    document.body.append(card);
    await settle(card);
    expect(sorted(parts(shadow(card)))).toEqual(["card", "eyebrow", "mark", "notice", "title"]);
  });
});

describe("theme inheritance", () => {
  it("applies tokens that a theme sets on an ancestor", async () => {
    const view = document.createElement("div");
    view.style.setProperty("--hydronicus-text", "rgb(1, 2, 3)");
    document.documentElement.style.setProperty("--hydronicus-heating-color", "rgb(4, 5, 6)");
    document.body.append(view);
    const card = await mount("hydronicus-plant-card", {}, view);
    const root = shadow(card);
    const frame = root.querySelector("ha-card");
    const dot = root.querySelector(".status-dot");
    if (!frame || !dot) throw new Error("The card did not render.");
    expect(frame.getAttribute("data-visual")).toBe("heating");
    expect(getComputedStyle(frame).color).toBe("rgb(1, 2, 3)");
    expect(getComputedStyle(dot).backgroundColor).toBe("rgb(4, 5, 6)");
  });
});
