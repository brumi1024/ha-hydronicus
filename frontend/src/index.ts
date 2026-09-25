import { CARD_TAG, ROOM_CARD_TAG, ROOM_EDITOR_TAG } from "./config";
import { HydronicusPlantCard } from "./hydronicus-plant-card";
import { HydronicusRoomCard } from "./hydronicus-room-card";
import { HydronicusRoomCardEditor } from "./hydronicus-room-card-editor";

declare global {
  interface Window {
    customCards?: Array<Record<string, unknown>>;
  }
}

const ELEMENTS: ReadonlyArray<[string, CustomElementConstructor]> = [
  [CARD_TAG, HydronicusPlantCard],
  [ROOM_CARD_TAG, HydronicusRoomCard],
  [ROOM_EDITOR_TAG, HydronicusRoomCardEditor],
];

/**
 * Define the elements on a registry unless it already knows a tag. Home
 * Assistant loads the cards automatically, and a leftover manual dashboard
 * resource can load the bundle a second time, which must not throw.
 */
function register(registry: CustomElementRegistry): void {
  for (const [tag, element] of ELEMENTS) {
    if (!registry.get(tag)) registry.define(tag, element);
  }
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
// The Room card editor is registered the same way, because the Room card
// creates it with `document.createElement`, which asks the active registry.
void bootRegistry.whenDefined("home-assistant").then(() => {
  register(window.customElements);
});

// The card picker lays its previews out in rows as tall as the tallest
// preview and centres the others, so a whole Plant would stretch its row
// and push a Room preview beside it out of view. The Plant card is listed
// by its description; the Room card is small enough to preview.
const CARDS: ReadonlyArray<Record<string, unknown>> = [
  {
    type: CARD_TAG,
    name: "Hydronicus Plant",
    description: "Topology-driven Hydronicus Plant status and controls.",
    preview: false,
  },
  {
    type: ROOM_CARD_TAG,
    name: "Hydronicus Room",
    description: "One Room of a Hydronicus Plant, with its thermostat and controls.",
    preview: true,
  },
];

window.customCards = window.customCards ?? [];
for (const card of CARDS) {
  if (window.customCards.some((known) => known.type === card.type)) continue;
  window.customCards.push({
    ...card,
    version: HYDRONICUS_FRONTEND_VERSION,
    documentationURL: "https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md",
  });
}
