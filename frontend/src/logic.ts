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

export function isFlowingState(state: string): boolean {
  return FLOWING_STATES.has(state.toLowerCase());
}

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

export function adjustTarget(zone: ZoneSnapshot, delta: number): number | null {
  if (zone.thermostat.target_temperature === null) return null;
  return Math.min(
    35,
    Math.max(5, Number((zone.thermostat.target_temperature + delta).toFixed(1))),
  );
}
