import { CELSIUS, steppedTarget, type TemperatureUnit } from "./format";
import type { PlantSnapshot, ZoneSnapshot } from "./types";

export const PRESENTATION_SCHEMA_VERSION = 2;

export type ActionCall = {
  domain: string;
  service: string;
  data: Record<string, unknown>;
};

export type PlantVisualState = "attention" | "cooling" | "heating" | "idle";

const FLOWING_STATES = new Set([
  "active",
  "cooling",
  "heating",
  "open",
  "opening",
  "overrun",
  "ready",
  "requested",
  "running",
  "selected",
  "starting",
  "waiting",
]);

export function parseSnapshot(value: unknown): PlantSnapshot {
  if (!value || typeof value !== "object") {
    throw new Error("Hydronicus returned no Plant snapshot.");
  }
  const snapshot = value as Partial<PlantSnapshot>;
  if (snapshot.schema_version !== PRESENTATION_SCHEMA_VERSION) {
    throw new Error(`Unsupported Hydronicus snapshot schema: ${String(snapshot.schema_version)}.`);
  }
  if (!snapshot.plant || !Array.isArray(snapshot.zones) || !Array.isArray(snapshot.alerts)) {
    throw new Error("Hydronicus returned an incomplete Plant snapshot.");
  }
  return snapshot as PlantSnapshot;
}

export function prioritizedAlerts(snapshot: Pick<PlantSnapshot, "alerts">): PlantSnapshot["alerts"] {
  return [...snapshot.alerts].sort(
    (left, right) =>
      left.priority - right.priority ||
      left.code.localeCompare(right.code) ||
      left.scope.localeCompare(right.scope),
  );
}

export function plantVisualState(
  snapshot: Pick<PlantSnapshot, "alerts" | "plant" | "safe_shutdown">,
): PlantVisualState {
  const health = snapshot.plant.health.toLowerCase();
  const hasCriticalAlert = snapshot.alerts.some(
    (alert) => alert.severity === "critical" || alert.severity === "error",
  );
  if (
    snapshot.safe_shutdown.active ||
    hasCriticalAlert ||
    ["blocked", "critical", "error", "failed", "unhealthy"].includes(health)
  ) {
    return "attention";
  }

  const activeState = `${snapshot.plant.active_mode} ${snapshot.plant.status}`.toLowerCase();
  if (activeState.includes("cool")) return "cooling";
  if (activeState.includes("heat")) return "heating";
  return "idle";
}

/** A Zone card's presentation state, from its own demand and blocking. */
export function zoneVisualState(zone: Pick<ZoneSnapshot, "blocked" | "demand" | "cooling">): PlantVisualState {
  if (zone.blocked) return "attention";
  if (zone.cooling.demand) return "cooling";
  if (zone.demand) return "heating";
  return "idle";
}

export function isFlowingState(state: string): boolean {
  return FLOWING_STATES.has(state.toLowerCase());
}

/** What a Zone is asking for: cooling, heating, or nothing. */
export function zoneDemandKind(zone: Pick<ZoneSnapshot, "demand" | "cooling"> | undefined): "cooling" | "heating" | "none" {
  if (!zone) return "none";
  return zone.cooling.demand ? "cooling" : zone.demand ? "heating" : "none";
}

/**
 * Build a target change. `temperature` is in the user's unit system, because
 * Home Assistant converts `climate.set_temperature` from that unit.
 */
export function actionForTarget(zone: ZoneSnapshot, temperature: number): ActionCall | null {
  if (zone.thermostat.kind !== "hydronicus" || !zone.thermostat.control_entity_id) return null;
  return {
    domain: "climate",
    service: "set_temperature",
    data: { entity_id: zone.thermostat.control_entity_id, temperature },
  };
}

export function actionForPreset(zone: ZoneSnapshot, preset: string): ActionCall | null {
  if (zone.thermostat.kind !== "hydronicus" || !zone.thermostat.control_entity_id) return null;
  return {
    domain: "climate",
    service: "set_preset_mode",
    data: { entity_id: zone.thermostat.control_entity_id, preset_mode: preset },
  };
}

export function actionForHvacMode(zone: ZoneSnapshot, hvacMode: string): ActionCall | null {
  if (zone.thermostat.kind !== "hydronicus" || !zone.thermostat.control_entity_id) return null;
  if (!zoneHvacModes(zone).includes(hvacMode)) return null;
  return {
    domain: "climate",
    service: "set_hvac_mode",
    data: { entity_id: zone.thermostat.control_entity_id, hvac_mode: hvacMode },
  };
}

export function actionForMode(snapshot: PlantSnapshot, mode: string): ActionCall | null {
  if (!snapshot.controls.requested_mode) return null;
  return {
    domain: "select",
    service: "select_option",
    data: { entity_id: snapshot.controls.requested_mode, option: mode },
  };
}

export function actionForSafeShutdown(snapshot: PlantSnapshot): ActionCall | null {
  if (!snapshot.controls.safe_shutdown) return null;
  return {
    domain: "button",
    service: "press",
    data: { entity_id: snapshot.controls.safe_shutdown },
  };
}

export function operationLabel(operation: Record<string, unknown>): string {
  const verb = String(operation.action ?? "operation").replaceAll("_", " ");
  const name = String(operation.actuator_name ?? "actuator");
  const result = String(operation.result ?? "");
  if (result === "proposed") return `Would ${verb} ${name}`;
  if (result === "executed") return `Executed ${name} ${verb}`;
  if (result === "suppressed") return `Suppressed ${name} ${verb}`;
  return `${result || "Operation"}: ${name} ${verb}`;
}

export function phaseLabel(phase: string): string {
  return phase.replaceAll("_", " ");
}

/** Hydronicus entities whose states Home Assistant translates. */
export type TranslatedState = "select.requested_mode" | "sensor.operating_mode" | "sensor.controller_status";

/**
 * The label Home Assistant shows for a state of a Hydronicus entity, from
 * the integration's entity translations, or the readable raw value.
 */
export function stateLabel(localize: ((key: string) => string) | undefined, entity: TranslatedState, state: string): string {
  const [platform, key] = entity.split(".");
  return localize?.(`component.hydronicus.entity.${platform}.${key}.state.${state}`) || sentenceLabel(state);
}

/** A raw value with its first letter capitalized, such as "Dry run". */
export function sentenceLabel(value: string): string {
  const label = phaseLabel(value);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

const HVAC_MODE_LABELS: Record<string, string> = {
  off: "Off",
  heat: "Heat",
  cool: "Cool",
  heat_cool: "Heat/Cool",
  auto: "Auto",
};

/**
 * The label Home Assistant shows for a climate HVAC mode, or an English
 * fallback when no translation is available.
 */
export function hvacModeLabel(localize: ((key: string) => string) | undefined, mode: string): string {
  return localize?.(`component.climate.entity_component._.state.${mode}`) || HVAC_MODE_LABELS[mode] || sentenceLabel(mode);
}

/**
 * The HVAC modes the card offers for a Zone: exactly the modes its
 * Hydronicus climate entity supports, and none for an external thermostat.
 */
export function zoneHvacModes(zone: ZoneSnapshot): string[] {
  if (zone.thermostat.kind !== "hydronicus") return [];
  return [...new Set(zone.thermostat.hvac_modes ?? [])];
}

/**
 * The areas a Zone shows a line for: every area when it covers two or more,
 * and none otherwise, because one area's reading is the Zone's own.
 */
export function zoneAreaLines(zone: Pick<ZoneSnapshot, "areas">): ZoneSnapshot["areas"] {
  return zone.areas.length >= 2 ? zone.areas : [];
}

/** Masonry height in 50 px units of one Zone tile, with its area lines. */
export function zoneTileSize(zone: Pick<ZoneSnapshot, "areas">): number {
  return 5 + Math.ceil(zoneAreaLines(zone).length / 2);
}

/** The short badge label for the execution boundary. */
export function boundaryLabel(boundary: PlantSnapshot["plant"]["execution_boundary"]): string {
  if (boundary.dry_run || boundary.mode === "dry_run") return "Dry run";
  // "mixed" with nothing forced to shadow means every output may execute.
  if (boundary.mode === "mixed" && !boundary.forced_shadow.length) return "Live";
  return sentenceLabel(boundary.mode);
}

/** The CSS class for the execution boundary badge. */
export function boundaryClass(boundary: PlantSnapshot["plant"]["execution_boundary"]): string {
  if (boundary.dry_run || boundary.mode === "dry_run") return "dry-run";
  if (boundary.mode === "mixed" && !boundary.forced_shadow.length) return "live";
  return boundary.mode.replaceAll("_", "-");
}

/**
 * The header's source summary, or null when the Plant has no sources and
 * nothing to report.
 */
export function sourceSummary(snapshot: Pick<PlantSnapshot, "plant" | "sources">): string | null {
  const { active_name: active, recommended_name: recommended } = snapshot.plant.source;
  if (!snapshot.sources.length && !active && !recommended) return null;
  const parts = [active ?? "None active"];
  if (recommended && recommended !== active) parts.push(`recommended ${recommended}`);
  return parts.join(" · ");
}

const NODE_KIND_LABELS: Record<string, string> = {
  zone: "Zone",
  circuit: "Loop",
};

const ALERT_LABELS: Record<string, string> = {
  plant_initializing: "Starting",
  plant_unavailable: "Plant unavailable",
  binding_unavailable: "Entity unavailable",
  zone_sensor_blocked: "Sensor blocked",
  zone_mode_blocked: "Zone blocked",
  cooling_blocked: "Cooling blocked",
  actuator_mismatch: "Equipment mismatch",
  actuator_blocked: "Equipment blocked",
  mode_changeover: "Mode changeover",
};

/** The title of an alert, naming what it is about when that is not the whole Plant. */
export function alertTitle(alert: { code: string; scope: string; name?: string }): string {
  const label = ALERT_LABELS[alert.code] ?? sentenceLabel(alert.code);
  return alert.scope !== "plant" && alert.name ? `${alert.name} · ${label}` : label;
}

/** The user-facing name of a delivery path node kind. */
export function nodeKindLabel(kind: string): string {
  return NODE_KIND_LABELS[kind] ?? sentenceLabel(kind);
}

/** The presets a Zone offers besides "none"; empty when it has none. */
export function zonePresets(zone: ZoneSnapshot): string[] {
  return [...new Set(zone.thermostat.preset_modes)].filter((preset) => preset !== "none");
}

/**
 * The next target one step up or down, in the user's unit system, from the
 * Celsius target in the snapshot.
 */
export function adjustTarget(zone: ZoneSnapshot, direction: 1 | -1, unit: TemperatureUnit = CELSIUS): number | null {
  if (zone.thermostat.target_temperature === null) return null;
  return steppedTarget(zone.thermostat.target_temperature, direction, unit);
}
