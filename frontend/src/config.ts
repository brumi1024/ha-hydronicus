import type { Density, HomeAssistantConnection, PlantCardConfig, PlantSummary } from "./types";

export const CARD_TAG = "hydronicus-plant-card";
export const CARD_TYPE = `custom:${CARD_TAG}` as const;
export const LIST_PLANTS = "hydronicus/list_plants";
const DENSITIES: readonly Density[] = ["comfortable", "compact"];

/**
 * Validate card YAML. `plant` must be present and a string; an empty string
 * is the stub state shown before a Plant exists or is chosen.
 */
export function validateConfig(config: unknown): PlantCardConfig {
  if (!config || typeof config !== "object") {
    throw new Error("Hydronicus Plant card requires a configuration.");
  }
  const candidate = config as Record<string, unknown>;
  if (candidate.type !== CARD_TYPE) {
    throw new Error(`Hydronicus Plant card type must be ${CARD_TYPE}.`);
  }
  if (typeof candidate.plant !== "string") {
    throw new Error("Hydronicus Plant card requires one Plant UUID in `plant`.");
  }
  const density = candidate.density ?? "comfortable";
  if (!DENSITIES.includes(density as Density)) {
    throw new Error("Hydronicus Plant card density must be comfortable or compact.");
  }
  return { type: CARD_TYPE, plant: candidate.plant.trim(), density: density as Density };
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

const LABELS: Record<string, string> = {
  plant: "Hydronicus Plant",
  density: "Density",
};

const HELPERS: Record<string, string> = {
  plant: "The Plant this card shows. Only Plants you can read are listed.",
  density: "Compact uses less spacing for dense dashboards.",
};

export interface ConfigForm {
  schema: Array<Record<string, unknown>>;
  computeLabel(schema: { name: string }): string | undefined;
  computeHelper(schema: { name: string }): string | undefined;
  assertConfig(config: Record<string, unknown>): void;
}

export async function configForm(): Promise<ConfigForm> {
  const plants = await plantDirectory.settled();
  return {
    schema: [
      {
        name: "plant",
        required: true,
        selector: {
          select: {
            mode: "dropdown",
            // Keep a Plant UUID that is not listed, for example one from YAML
            // or one the user cannot currently read, instead of clearing it.
            custom_value: true,
            options: plants.map((plant) => ({ value: plant.id, label: plant.name })),
          },
        },
      },
      {
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
      },
    ],
    computeLabel: (schema) => LABELS[schema.name],
    computeHelper: (schema) => HELPERS[schema.name],
    assertConfig: (config) => {
      validateConfig(config);
    },
  };
}
