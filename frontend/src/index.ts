import { CARD_TAG } from "./config";
import { HydronicusPlantCard } from "./hydronicus-plant-card";

declare global {
  interface Window {
    customCards?: Array<Record<string, unknown>>;
  }
}

// Home Assistant loads the card automatically. A leftover manual dashboard
// resource can load the bundle a second time, which must not throw.
if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, HydronicusPlantCard);
}

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
