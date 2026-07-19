import { describe, expect, it } from "vitest";
import { actionForMode, actionForPreset, actionForSafeShutdown, actionForTarget, adjustTarget, parseSnapshot, prioritizedAlerts } from "../src/logic";
import type { PlantSnapshot, ZoneSnapshot } from "../src/types";

const zone: ZoneSnapshot = {
  id: "zone-1", name: "Living room", climate_entity_id: "climate.hydronic_living_room",
  current_temperature: 20, target_temperature: 21, preset: "comfort", preset_modes: ["comfort", "eco"],
  demand: true, phase: "heating", blocked: false, blocked_reason: null,
  sensor_status: { usable: 1, optional_excluded: 0, required_blocking: 0 },
  cooling: { demand: false, status: null, dew_point: null, condensation_margin: null, blocked: false, reason: null, interlocks: [] },
  route_ids: ["route-1"], coupling_group_ids: [],
};

const snapshot = {
  schema_version: 1,
  plant: { id: "plant-1", name: "Test plant", status: "heating", health: "healthy", requested_mode: "heating", active_mode: "heating", changeover: { phase: "idle", target_mode: null, reason: "" }, controller: { evaluated: true, mode_explanation: "" }, source: { active_id: null, active_name: null, recommended_id: null, recommended_name: null }, execution_boundary: { mode: "dry_run", dry_run: true, forced_shadow: [], message: "" } },
  controls: { requested_mode: "select.hydronic_mode", safe_shutdown: "button.hydronic_shutdown" },
  zones: [zone], alerts: [], topology: { routes: [], circuits: [], coupling_groups: [], summary: {}, warnings: [], active_consumer_sets: { valves: [], pumps: [] } }, delivery_paths: [], actuators: [], sources: [], explanations: [], execution: { boundary: {}, operations: { proposed: [], executed: [], suppressed: [], failed: [], timed_out: [] } }, safe_shutdown: { active: false, phase: "idle", message: "" },
} satisfies PlantSnapshot;

describe("Hydronicus presentation logic", () => {
  it("rejects an unsupported schema without reconstructing behavior", () => {
    expect(() => parseSnapshot({ ...snapshot, schema_version: 2 })).toThrow("Unsupported");
  });

  it("prioritizes stable alert severity and code", () => {
    const alerts = prioritizedAlerts({ alerts: [
      { code: "z", severity: "warning", priority: 2, scope: "plant", message: "" },
      { code: "a", severity: "error", priority: 1, scope: "plant", message: "" },
    ] });
    expect(alerts.map((alert) => alert.code)).toEqual(["a", "z"]);
  });

  it("uses existing entity actions for every card write", () => {
    expect(actionForTarget(zone, 21.5)).toEqual({ domain: "climate", service: "set_temperature", data: { entity_id: zone.climate_entity_id, temperature: 21.5 } });
    expect(actionForPreset(zone, "eco")).toEqual({ domain: "climate", service: "set_preset_mode", data: { entity_id: zone.climate_entity_id, preset_mode: "eco" } });
    expect(actionForMode(snapshot, "cooling")).toEqual({ domain: "select", service: "select_option", data: { entity_id: "select.hydronic_mode", option: "cooling" } });
    expect(actionForSafeShutdown(snapshot)).toEqual({ domain: "button", service: "press", data: { entity_id: "button.hydronic_shutdown" } });
  });

  it("keeps target controls bounded and step-based", () => {
    expect(adjustTarget(zone, 0.5)).toBe(21.5);
    expect(adjustTarget({ ...zone, target_temperature: 35 }, 0.5)).toBe(35);
    expect(adjustTarget({ ...zone, target_temperature: 5 }, -0.5)).toBe(5);
  });
});
