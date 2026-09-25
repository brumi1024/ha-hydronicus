import { plantStore } from "./store";
import type { Density, HomeAssistantConnection, PlantCardConfig, PlantSection, PlantSummary, ZoneCardConfig, ZoneSnapshot } from "./types";

export const CARD_TAG = "hydronicus-plant-card";
export const CARD_TYPE = `custom:${CARD_TAG}` as const;
export const ZONE_CARD_TAG = "hydronicus-zone-card";
export const ZONE_CARD_TYPE = `custom:${ZONE_CARD_TAG}` as const;
export const ZONE_EDITOR_TAG = "hydronicus-zone-card-editor";
export const LIST_PLANTS = "hydronicus/list_plants";
const DENSITIES: readonly Density[] = ["comfortable", "compact"];

/** Every Plant card section in its default order, with its editor label. */
export const PLANT_SECTIONS: ReadonlyArray<{ value: PlantSection; label: string }> = [
  { value: "header", label: "Header and execution boundary" },
  { value: "alerts", label: "Alerts" },
  { value: "zones", label: "Zones" },
  { value: "paths", label: "Hydraulic flow" },
  { value: "equipment", label: "Equipment" },
  { value: "explanations", label: "Controller explanations" },
  { value: "operations", label: "Operation outcomes" },
];
const SECTION_NAMES = PLANT_SECTIONS.map((section) => section.value);

function configRecord(config: unknown, card: string, type: string): Record<string, unknown> {
  if (!config || typeof config !== "object") {
    throw new Error(`${card} requires a configuration.`);
  }
  const candidate = config as Record<string, unknown>;
  if (candidate.type !== type) {
    throw new Error(`${card} type must be ${type}.`);
  }
  if (typeof candidate.plant !== "string") {
    throw new Error(`${card} requires one Plant UUID in \`plant\`.`);
  }
  return candidate;
}

function validDensity(value: unknown, card: string): Density {
  const density = value ?? "comfortable";
  if (!DENSITIES.includes(density as Density)) {
    throw new Error(`${card} density must be comfortable or compact.`);
  }
  return density as Density;
}

/**
 * An ordered subset of the Plant card sections. An empty list, which the
 * visual editor produces when every choice is cleared, means every section.
 */
function validSections(value: unknown): PlantSection[] | undefined {
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value)) {
    throw new Error("Hydronicus Plant card `sections` must be a list of section names.");
  }
  const seen = new Set<string>();
  for (const section of value) {
    if (typeof section !== "string" || !SECTION_NAMES.includes(section as PlantSection)) {
      throw new Error(`Hydronicus Plant card section ${JSON.stringify(section)} is unknown. Use ${SECTION_NAMES.join(", ")}.`);
    }
    if (seen.has(section)) {
      throw new Error(`Hydronicus Plant card section ${section} is listed twice.`);
    }
    seen.add(section);
  }
  return value.length ? (value as PlantSection[]) : undefined;
}

/**
 * Validate card YAML. `plant` must be present and a string; an empty string
 * is the stub state shown before a Plant exists or is chosen.
 */
export function validateConfig(config: unknown): PlantCardConfig {
  const card = "Hydronicus Plant card";
  const candidate = configRecord(config, card, CARD_TYPE);
  const density = validDensity(candidate.density, card);
  const sections = validSections(candidate.sections);
  return { type: CARD_TYPE, plant: (candidate.plant as string).trim(), density, ...(sections ? { sections } : {}) };
}

/** The sections a Plant card shows, in order. */
export function shownSections(config: Pick<PlantCardConfig, "sections"> | undefined): readonly PlantSection[] {
  return config?.sections ?? SECTION_NAMES;
}

/**
 * Validate Zone card YAML. `zone` is the Zone's id in the Plant snapshot;
 * like `plant`, an empty string is the stub state before one is chosen.
 */
export function validateZoneConfig(config: unknown): ZoneCardConfig {
  const card = "Hydronicus Zone card";
  const candidate = configRecord(config, card, ZONE_CARD_TYPE);
  const zone = candidate.zone ?? "";
  if (typeof zone !== "string") {
    throw new Error(`${card} requires one Zone id in \`zone\`.`);
  }
  const density = validDensity(candidate.density, card);
  return { type: ZONE_CARD_TYPE, plant: (candidate.plant as string).trim(), zone: zone.trim(), density };
}

/**
 * The Plants the current user can read, shared by every card on the page.
 * The built-in form editor has no `hass`, so this cache is its only source.
 */
class PlantDirectory {
  private plants: PlantSummary[] = [];
  private pending: Promise<PlantSummary[]> | null = null;
  private connection: HomeAssistantConnection | null = null;

  get known(): PlantSummary[] {
    return this.plants;
  }

  /** Load once per connection; later calls share the result. */
  load(connection: HomeAssistantConnection): Promise<PlantSummary[]> {
    if (this.connection === connection && this.pending) return this.pending;
    this.connection = connection;
    this.pending = connection
      .sendMessagePromise<{ plants?: PlantSummary[] }>({ type: LIST_PLANTS })
      .then((result) => {
        this.plants = Array.isArray(result.plants) ? result.plants : [];
        return this.plants;
      })
      .catch(() => {
        // Let the next caller try again; the form falls back to free input.
        if (this.connection === connection) this.pending = null;
        return this.plants;
      });
    return this.pending;
  }

  /** Wait briefly for an in-flight load so a first edit sees the Plants. */
  async settled(timeoutMs = 2_000): Promise<PlantSummary[]> {
    if (!this.pending) return this.plants;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<PlantSummary[]>((resolve) => {
      timer = setTimeout(() => resolve(this.plants), timeoutMs);
    });
    try {
      return await Promise.race([this.pending, timeout]);
    } finally {
      clearTimeout(timer);
    }
  }

  /** Test seam. */
  reset(): void {
    this.plants = [];
    this.pending = null;
    this.connection = null;
  }
}

export const plantDirectory = new PlantDirectory();

export async function stubConfig(hass: { connection?: HomeAssistantConnection } | undefined): Promise<Omit<PlantCardConfig, "type">> {
  const plants = hass?.connection ? await plantDirectory.load(hass.connection) : plantDirectory.known;
  return { plant: plants[0]?.id ?? "", density: "comfortable" };
}

/** The first readable Plant and its first visible Zone, for the card picker. */
export async function zoneStubConfig(hass: { connection?: HomeAssistantConnection } | undefined): Promise<Omit<ZoneCardConfig, "type">> {
  const connection = hass?.connection;
  const plants = connection ? await plantDirectory.load(connection) : plantDirectory.known;
  const plant = plants[0]?.id ?? "";
  const snapshot = connection && plant ? await plantStore.snapshot(connection, plant) : null;
  return { plant, zone: snapshot?.zones[0]?.id ?? "", density: "comfortable" };
}

const LABELS: Record<string, string> = {
  plant: "Hydronicus Plant",
  zone: "Zone",
  density: "Density",
  sections: "Sections",
};

const HELPERS: Record<string, string> = {
  plant: "The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",
  zone: "The Zone this card shows. Only Zones you can read are listed; one that is not listed shows its id.",
  density: "Compact uses less spacing for dense dashboards.",
  sections: "The parts of the Plant to show, in this order. Leave empty to show every section.",
};

export interface ConfigForm {
  schema: Array<Record<string, unknown>>;
  computeLabel(schema: { name: string }): string | undefined;
  computeHelper(schema: { name: string }): string | undefined;
  assertConfig(config: Record<string, unknown>): void;
}

export const computeLabel = (schema: { name: string }): string | undefined => LABELS[schema.name];
export const computeHelper = (schema: { name: string }): string | undefined => HELPERS[schema.name];

/**
 * A plain dropdown shows the name of the chosen item. `custom_value` would
 * turn it into a combo box that shows the raw id instead. A dropdown keeps
 * an id that is not listed, for example one from YAML or one the user
 * cannot currently read, and shows it as the id until another is picked.
 * Without any listed item, free text input still lets the user enter one.
 */
function namedSelector(items: ReadonlyArray<{ id: string; name: string }>): Record<string, unknown> {
  if (items.length === 0) return { text: {} };
  return {
    select: {
      mode: "dropdown",
      options: items.map((item) => ({ value: item.id, label: item.name })),
    },
  };
}

const DENSITY_FIELD = {
  name: "density",
  selector: {
    select: {
      mode: "dropdown",
      options: [
        { value: "comfortable", label: "Comfortable" },
        { value: "compact", label: "Compact" },
      ],
    },
  },
};

export async function configForm(): Promise<ConfigForm> {
  const plants = await plantDirectory.settled();
  return {
    schema: [
      { name: "plant", required: true, selector: namedSelector(plants) },
      DENSITY_FIELD,
      {
        name: "sections",
        selector: { select: { multiple: true, reorder: true, mode: "dropdown", options: PLANT_SECTIONS.map((section) => ({ ...section })) } },
      },
    ],
    computeLabel,
    computeHelper,
    assertConfig: (config) => {
      validateConfig(config);
    },
  };
}

/**
 * The Zone card editor form: the Plant, then a Zone of that Plant by name.
 * `zones` are the visible Zones of the chosen Plant's snapshot.
 */
export function zoneConfigSchema(plants: PlantSummary[], zones: readonly Pick<ZoneSnapshot, "id" | "name">[]): Array<Record<string, unknown>> {
  return [
    { name: "plant", required: true, selector: namedSelector(plants) },
    { name: "zone", required: true, selector: namedSelector(zones) },
    DENSITY_FIELD,
  ];
}
