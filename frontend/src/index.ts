import { CARD_TAG } from "./config";
import { HydronicusPlantCard } from "./hydronicus-plant-card";

declare global {
  interface Window {
    customCards?: Array<Record<string, unknown>>;
  }
}

/**
 * Define the card on a registry unless it already knows the tag. Home
 * Assistant loads the card automatically, and a leftover manual dashboard
 * resource can load the bundle a second time, which must not throw.
 */
function register(registry: CustomElementRegistry): void {
  if (!registry.get(CARD_TAG)) registry.define(CARD_TAG, HydronicusPlantCard);
}

const bootRegistry = window.customElements;
register(bootRegistry);

// Home Assistant imports this module in parallel with its app bundle, and
// the app bundle replaces `window.customElements` with a scoped custom
// element registry polyfill before it defines any element. When this module
// runs first, the card is only in the native registry, which Lovelace does
// not ask. The app's root element is defined through the polyfill, so once
// it exists the active registry is final; define the card there too. The
// polyfill accepts a tag the native registry already has without throwing.
void bootRegistry.whenDefined("home-assistant").then(() => {
  register(window.customElements);
});

window.customCards = window.customCards ?? [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Hydronicus Plant",
    version: HYDRONICUS_FRONTEND_VERSION,
    description: "Topology-driven Hydronicus Plant status and controls.",
    preview: true,
    documentationURL: "https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md",
  });
}
