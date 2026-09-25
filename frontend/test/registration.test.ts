import { afterEach, describe, expect, it, vi } from "vitest";

const TAGS = ["hydronicus-plant-card", "hydronicus-room-card", "hydronicus-room-card-editor"];
const CARD_TAGS = ["hydronicus-plant-card", "hydronicus-room-card"];
const nativeRegistry = window.customElements;

/**
 * A minimal stand-in for the scoped custom element registry polyfill that
 * Home Assistant's app bundle installs as `window.customElements`. Like the
 * real polyfill, it keeps its own definitions and forwards a definition to
 * the native registry only when the native registry does not have the tag.
 */
class ScopedRegistry {
  private readonly definitions = new Map<string, CustomElementConstructor>();
  private readonly waiting = new Map<string, (ctor: CustomElementConstructor) => void>();
  private readonly promises = new Map<string, Promise<CustomElementConstructor>>();

  define(tag: string, ctor: CustomElementConstructor): void {
    if (this.definitions.has(tag)) {
      throw new DOMException(`the name "${tag}" has already been used with this registry`);
    }
    this.definitions.set(tag, ctor);
    if (!nativeRegistry.get(tag)) nativeRegistry.define(tag, class extends HTMLElement {});
    this.waiting.get(tag)?.(ctor);
  }

  get(tag: string): CustomElementConstructor | undefined {
    return this.definitions.get(tag);
  }

  whenDefined(tag: string): Promise<CustomElementConstructor> {
    const defined = this.definitions.get(tag);
    if (defined) return Promise.resolve(defined);
    let promise = this.promises.get(tag);
    if (!promise) {
      promise = new Promise((resolve) => this.waiting.set(tag, resolve));
      this.promises.set(tag, promise);
    }
    return promise;
  }
}

function install(registry: ScopedRegistry | CustomElementRegistry): void {
  Object.defineProperty(window, "customElements", { value: registry, configurable: true, writable: true });
}

afterEach(() => {
  install(nativeRegistry);
});

describe("C10 registration on Home Assistant's element registry", () => {
  it("defines every element on a registry that replaces customElements after the bundle ran", async () => {
    vi.resetModules();
    await import("../src/index");
    for (const tag of TAGS) expect(nativeRegistry.get(tag), tag).toBeDefined();

    // Home Assistant's app bundle evaluates after the card: it installs the
    // polyfill registry, then defines its root element through it.
    const scoped = new ScopedRegistry();
    install(scoped);
    for (const tag of TAGS) expect(scoped.get(tag), tag).toBeUndefined();
    scoped.define("home-assistant", class extends HTMLElement {});

    await vi.waitFor(() => {
      for (const tag of TAGS) expect(scoped.get(tag), tag).toBeDefined();
    });
  });

  it("defines every element once when the polyfill registry is already active", async () => {
    const scoped = new ScopedRegistry();
    install(scoped);
    vi.resetModules();
    await import("../src/index");
    for (const tag of TAGS) expect(scoped.get(tag), tag).toBeDefined();

    const defineSpy = vi.spyOn(scoped, "define");
    scoped.define("home-assistant", class extends HTMLElement {});
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(defineSpy.mock.calls.filter(([tag]) => TAGS.includes(tag))).toHaveLength(0);
  });
});

describe("C10 double loading", () => {
  it("registers each element and card picker entry once when the bundle is evaluated twice", async () => {
    vi.resetModules();
    await import("../src/index");
    vi.resetModules();
    await expect(import("../src/index")).resolves.toBeDefined();

    for (const tag of TAGS) expect(nativeRegistry.get(tag), tag).toBeDefined();
    for (const tag of CARD_TAGS) {
      const entries = (window.customCards ?? []).filter((card) => card.type === tag);
      expect(entries, tag).toHaveLength(1);
      expect(entries[0]).toMatchObject({ version: "0.0.0-test" });
    }
    // The card picker sizes a row to its tallest preview, so only the Room card previews.
    const preview = (tag: string) => window.customCards?.find((card) => card.type === tag)?.preview;
    expect(preview("hydronicus-plant-card")).toBe(false);
    expect(preview("hydronicus-room-card")).toBe(true);
    expect(window.customCards?.find((card) => card.type === "hydronicus-room-card")?.name).toBe("Hydronicus Room");
  });
});
