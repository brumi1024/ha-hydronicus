import { afterEach, describe, expect, it, vi } from "vitest";

const TAG = "hydronicus-plant-card";
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
  it("defines the card on a registry that replaces customElements after the bundle ran", async () => {
    vi.resetModules();
    await import("../src/index");
    expect(nativeRegistry.get(TAG)).toBeDefined();

    // Home Assistant's app bundle evaluates after the card: it installs the
    // polyfill registry, then defines its root element through it.
    const scoped = new ScopedRegistry();
    install(scoped);
    expect(scoped.get(TAG)).toBeUndefined();
    scoped.define("home-assistant", class extends HTMLElement {});

    await vi.waitFor(() => expect(scoped.get(TAG)).toBeDefined());
  });

  it("defines the card once when the polyfill registry is already active", async () => {
    const scoped = new ScopedRegistry();
    install(scoped);
    vi.resetModules();
    await import("../src/index");
    expect(scoped.get(TAG)).toBeDefined();

    const defineSpy = vi.spyOn(scoped, "define");
    scoped.define("home-assistant", class extends HTMLElement {});
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(defineSpy.mock.calls.filter(([tag]) => tag === TAG)).toHaveLength(0);
  });
});
