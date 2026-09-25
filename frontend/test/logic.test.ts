import { describe, expect, it } from "vitest";
import { actionForHvacMode, actionForMode, alertTitle, zoneAlerts, zoneBadge, zoneVisualState, actionForPreset, actionForSafeShutdown, actionForTarget, adjustTarget, boundaryLabel, hvacModeLabel, isFlowingState, nodeKindLabel, parseSnapshot, plantVisualState, prioritizedAlerts, sourceSummary, zoneAreaLines, zoneDemandKind, zoneHvacModes, zoneTileSize } from "../src/logic";
import type { PlantSnapshot, ZoneSnapshot } from "../src/types";

const zone: ZoneSnapshot = {
  id: "zone-1", name: "Living room", areas: [],
  thermostat: {
    kind: "hydronicus", state: "available", control_entity_id: "climate.hydronic_living_room",
    current_temperature: 20, target_temperature: 21, preset: "comfort", preset_modes: ["comfort", "eco"], hvac_mode: "heat", hvac_modes: ["off", "heat"],
    explanation: "Hydronicus owns this Zone's thermostat.",
  },
  demand: true, phase: "heating", blocked: false, blocked_reason: null,
  sensor_status: { usable: 1, optional_excluded: 0, required_blocking: 0 },
  cooling: { demand: false, status: null, dew_point: null, condensation_margin: null, blocked: false, reason: null, interlocks: [] },
  route_ids: ["route-1"], coupling_group_ids: [],
};

const snapshot = {
  schema_version: 2,
  plant: { id: "plant-1", name: "Test plant", status: "heating", health: "healthy", requested_mode: "heating", active_mode: "heating", changeover: { phase: "idle", target_mode: null, reason: "" }, controller: { evaluated: true, mode_explanation: "" }, source: { active_id: null, active_name: null, recommended_id: null, recommended_name: null }, execution_boundary: { mode: "dry_run", dry_run: true, forced_shadow: [], message: "" } },
  controls: { requested_mode: "select.hydronic_mode", safe_shutdown: "button.hydronic_shutdown" },
  zones: [zone], alerts: [], topology: { routes: [], circuits: [], coupling_groups: [], summary: {}, warnings: [], active_consumer_sets: { valves: [], pumps: [] } }, delivery_paths: [], actuators: [], sources: [], explanations: [], execution: { boundary: {}, operations: { proposed: [], executed: [], suppressed: [], failed: [], timed_out: [] } }, safe_shutdown: { active: false, phase: "idle", message: "" },
} satisfies PlantSnapshot;

describe("Hydronicus presentation logic", () => {
  it("rejects an unsupported schema without reconstructing behavior", () => {
    expect(() => parseSnapshot({ ...snapshot, schema_version: 1 })).toThrow("Unsupported");
  });

  it("prioritizes stable alert severity and code", () => {
    const alerts = prioritizedAlerts({ alerts: [
      { code: "z", severity: "warning", priority: 2, scope: "plant", message: "" },
      { code: "a", severity: "error", priority: 1, scope: "plant", message: "" },
    ] });
    expect(alerts.map((alert) => alert.code)).toEqual(["a", "z"]);
  });

  it("derives presentation-only Plant color from real operating state", () => {
    expect(plantVisualState(snapshot)).toBe("heating");
    expect(plantVisualState({
      ...snapshot,
      plant: { ...snapshot.plant, status: "cooling", active_mode: "cooling" },
    })).toBe("cooling");
    expect(plantVisualState({
      ...snapshot,
      alerts: [{ code: "blocked", severity: "error", priority: 1, scope: "plant", message: "Blocked" }],
    })).toBe("attention");
    expect(plantVisualState({
      ...snapshot,
      plant: { ...snapshot.plant, status: "idle", active_mode: "idle" },
    })).toBe("idle");
  });

  it("animates only states that represent hydraulic movement or preparation", () => {
    expect(isFlowingState("active")).toBe(true);
    expect(isFlowingState("opening")).toBe(true);
    expect(isFlowingState("waiting")).toBe(true);
    expect(isFlowingState("selected")).toBe(true);
    expect(isFlowingState("idle")).toBe(false);
    expect(isFlowingState("blocked")).toBe(false);
    expect(isFlowingState("unavailable")).toBe(false);
  });

  it("uses existing entity actions for every card write", () => {
    expect(actionForTarget(zone, 21.5)).toEqual({ domain: "climate", service: "set_temperature", data: { entity_id: zone.thermostat.control_entity_id, temperature: 21.5 } });
    expect(actionForPreset(zone, "eco")).toEqual({ domain: "climate", service: "set_preset_mode", data: { entity_id: zone.thermostat.control_entity_id, preset_mode: "eco" } });
    expect(actionForMode(snapshot, "cooling")).toEqual({ domain: "select", service: "select_option", data: { entity_id: "select.hydronic_mode", option: "cooling" } });
    expect(actionForSafeShutdown(snapshot)).toEqual({ domain: "button", service: "press", data: { entity_id: "button.hydronic_shutdown" } });
  });

  it("keeps target controls bounded and step-based", () => {
    expect(adjustTarget(zone, 1)).toBe(21.5);
    expect(adjustTarget(zone, -1)).toBe(20.5);
    expect(adjustTarget({ ...zone, thermostat: { ...zone.thermostat, target_temperature: 35 } }, 1)).toBe(35);
    expect(adjustTarget({ ...zone, thermostat: { ...zone.thermostat, target_temperature: 5 } }, -1)).toBe(5);
  });

  it("steps targets in the user's unit system and snaps to the step grid", () => {
    expect(adjustTarget(zone, 1, "°F")).toBe(70);
    expect(adjustTarget(zone, -1, "°F")).toBe(69);
    expect(adjustTarget({ ...zone, thermostat: { ...zone.thermostat, target_temperature: 35 } }, 1, "°F")).toBe(95);
    expect(adjustTarget({ ...zone, thermostat: { ...zone.thermostat, target_temperature: 21.3 } }, 1, "°C")).toBe(21.5);
  });

  it("does not create target or preset actions for an external thermostat", () => {
    const external: ZoneSnapshot = {
      ...zone,
      thermostat: {
        kind: "external_climate",
        state: "available",
        control_entity_id: null,
        current_temperature: null,
        target_temperature: null,
        preset: null,
        preset_modes: [],
        hvac_mode: "heat",
        hvac_modes: [],
        explanation: "External thermostat owns this Zone.",
      },
    };

    expect(actionForTarget(external, 21.5)).toBeNull();
    expect(actionForPreset(external, "eco")).toBeNull();
    expect(adjustTarget(external, 1)).toBeNull();
  });

  it("preserves a readable blocked external state with nullable diagnostics", () => {
    const blocked: ZoneSnapshot = {
      ...zone,
      thermostat: {
        kind: "external_climate",
        state: "blocked",
        control_entity_id: null,
        current_temperature: null,
        target_temperature: null,
        preset: null,
        preset_modes: [],
        hvac_mode: "heat",
        hvac_modes: [],
        explanation: "External thermostat blocked: HVAC action is missing or unsupported.",
      },
      blocked: true,
      blocked_reason: "External thermostat blocked: HVAC action is missing or unsupported.",
    };

    expect(blocked.thermostat.state).toBe("blocked");
    expect(blocked.thermostat.current_temperature).toBeNull();
    expect(blocked.thermostat.target_temperature).toBeNull();
    expect(blocked.blocked_reason).toContain("blocked");
  });
});

describe("Zone HVAC modes", () => {
  const coolingZone: ZoneSnapshot = { ...zone, thermostat: { ...zone.thermostat, hvac_mode: "off", hvac_modes: ["off", "heat", "cool", "heat_cool"] } };

  it("offers exactly the modes the Zone's climate entity supports", () => {
    expect(zoneHvacModes(zone)).toEqual(["off", "heat"]);
    expect(zoneHvacModes(coolingZone)).toEqual(["off", "heat", "cool", "heat_cool"]);
  });

  it("sets the HVAC mode on the Hydronicus climate entity", () => {
    expect(actionForHvacMode(coolingZone, "cool")).toEqual({ domain: "climate", service: "set_hvac_mode", data: { entity_id: "climate.hydronic_living_room", hvac_mode: "cool" } });
    // A mode the entity does not support would be rejected, so none is sent.
    expect(actionForHvacMode(zone, "cool")).toBeNull();
  });

  it("never writes to an external thermostat", () => {
    const external: ZoneSnapshot = { ...zone, thermostat: { ...zone.thermostat, kind: "external_climate", control_entity_id: null, hvac_modes: ["off", "heat"] } };
    expect(zoneHvacModes(external)).toEqual([]);
    expect(actionForHvacMode(external, "heat")).toBeNull();
  });

  it("names what a Zone is asking for, with cooling before heating", () => {
    expect(zoneDemandKind(zone)).toBe("heating");
    expect(zoneDemandKind({ ...zone, demand: false })).toBe("none");
    expect(zoneDemandKind({ ...zone, cooling: { ...zone.cooling, demand: true } })).toBe("cooling");
    expect(zoneDemandKind(undefined)).toBe("none");
  });

  it("labels modes with Home Assistant's climate translations or readable fallbacks", () => {
    expect(hvacModeLabel(undefined, "heat_cool")).toBe("Heat/Cool");
    expect(hvacModeLabel(undefined, "off")).toBe("Off");
    const localize = (key: string) => (key === "component.climate.entity_component._.state.heat" ? "Heizen" : "");
    expect(hvacModeLabel(localize, "heat")).toBe("Heizen");
  });
});

describe("Header summaries", () => {
  const boundary = snapshot.plant.execution_boundary;

  it("labels each execution boundary in sentence case", () => {
    expect(boundaryLabel(boundary)).toBe("Dry run");
    expect(boundaryLabel({ ...boundary, mode: "mixed", dry_run: false, forced_shadow: ["source_selection"] })).toBe("Mixed");
    expect(boundaryLabel({ ...boundary, mode: "mixed", dry_run: false, forced_shadow: [] })).toBe("Live");
  });

  it("omits the source summary for a Plant without sources", () => {
    expect(sourceSummary(snapshot)).toBeNull();
    const withSource = { ...snapshot, sources: [{ id: "boiler" }], plant: { ...snapshot.plant, source: { active_id: "boiler", active_name: "Boiler", recommended_id: "boiler", recommended_name: "Boiler" } } };
    expect(sourceSummary(withSource)).toBe("Boiler");
    const idle = { ...withSource, plant: { ...withSource.plant, source: { active_id: null, active_name: null, recommended_id: "boiler", recommended_name: "Boiler" } } };
    expect(sourceSummary(idle)).toBe("None active · recommended Boiler");
  });

  it("names path nodes with the Zone and Loop vocabulary", () => {
    expect(["zone", "circuit", "valve", "pump", "source"].map(nodeKindLabel)).toEqual(["Zone", "Loop", "Valve", "Pump", "Source"]);
  });
});

describe("Alert titles", () => {
  it("names the zone or equipment and uses a readable label", () => {
    expect(alertTitle({ code: "zone_sensor_blocked", scope: "zone-1", name: "Living" })).toBe("Living · Sensor blocked");
    expect(alertTitle({ code: "actuator_mismatch", scope: "valve-1", name: "Living loop valve" })).toBe("Living loop valve · Equipment mismatch");
  });

  it("leaves the Plant name out of Plant alerts and falls back without a name", () => {
    expect(alertTitle({ code: "binding_unavailable", scope: "plant", name: "Hydronic plant" })).toBe("Entity unavailable");
    expect(alertTitle({ code: "zone_mode_blocked", scope: "zone-1" })).toBe("Zone blocked");
    expect(alertTitle({ code: "something_new", scope: "plant" })).toBe("Something new");
  });
});

describe("area lines", () => {
  const area = { id: "kitchen", name: "Kitchen", missing: false, temperature: 20, humidity: 45, temperature_entity_id: "sensor.kitchen", humidity_entity_id: null };

  it("shows a line per area only for a Zone that covers several areas", () => {
    expect(zoneAreaLines({ areas: [] })).toEqual([]);
    expect(zoneAreaLines({ areas: [area] })).toEqual([]);
    expect(zoneAreaLines({ areas: [area, { ...area, id: "hall" }] })).toHaveLength(2);
  });

  it("grows a Zone tile's masonry size by one unit per two area lines", () => {
    expect(zoneTileSize({ areas: [area] })).toBe(5);
    expect(zoneTileSize({ areas: [area, area] })).toBe(6);
    expect(zoneTileSize({ areas: [area, area, area] })).toBe(7);
  });
});

describe("Plant and Zone attention", () => {
  const alert = (code: string, severity: "error" | "warning", scope: string) => ({ code, severity, priority: severity === "error" ? 1 : 2, scope, name: "Living room", message: code });

  it("needs attention while the Plant is degraded or an entity is unavailable", () => {
    // Only a warning is open, so the health alone must mark the Plant.
    const warned = { ...snapshot, alerts: [alert("zone_area_self_feed", "warning", "zone-1")] };
    expect(plantVisualState({ ...warned, plant: { ...snapshot.plant, health: "degraded" } })).toBe("attention");
    expect(plantVisualState({ ...warned, plant: { ...snapshot.plant, health: "unavailable" } })).toBe("attention");
    expect(plantVisualState(warned)).toBe("heating");
  });

  it("lists the alerts about one Zone, most urgent first", () => {
    const alerts = [
      alert("zone_area_self_feed", "warning", "zone-1"),
      alert("zone_sensor_blocked", "error", "zone-2"),
      alert("zone_area_missing", "error", "zone-1"),
      alert("binding_unavailable", "error", "plant"),
    ];
    expect(zoneAlerts({ alerts }, "zone-1").map((item) => item.code)).toEqual(["zone_area_missing", "zone_area_self_feed"]);
  });

  it("needs attention for a Zone with an error, but not for a warning", () => {
    const idle = { ...zone, demand: false, phase: "idle" };
    expect(zoneVisualState(idle, [alert("zone_area_missing", "error", "zone-1")])).toBe("attention");
    expect(zoneVisualState(idle, [alert("zone_area_self_feed", "warning", "zone-1")])).toBe("idle");
    expect(zoneVisualState(idle)).toBe("idle");
  });

  it("labels the area alerts and a missing sensor", () => {
    expect(alertTitle({ code: "zone_area_missing", scope: "zone-1", name: "Home" })).toBe("Home · Area missing");
    expect(alertTitle({ code: "zone_without_temperature_source", scope: "zone-1", name: "Home" })).toBe("Home · No temperature sensor");
    expect(alertTitle({ code: "zone_area_self_feed", scope: "zone-1", name: "Home" })).toBe("Home · Area sensor ignored");
    expect(alertTitle({ code: "optional_sensor_unavailable", scope: "zone-1", name: "Home" })).toBe("Home · Optional sensor missing");
    expect(alertTitle({ code: "sensor_unavailable", scope: "zone-1", name: "Home" })).toBe("Home · Sensor missing");
  });
});

describe("Zone badge", () => {
  const off = { ...zone.thermostat, hvac_mode: "off" };

  it("shows Off for an off thermostat, even when the Zone is blocked and idle", () => {
    expect(zoneBadge({ ...zone, thermostat: off, phase: "idle" }, undefined)).toEqual({ label: "Off", kind: "off" });
    expect(zoneBadge({ ...zone, thermostat: off, phase: "idle", blocked: true }, undefined)).toEqual({ label: "Off", kind: "off" });
    expect(zoneBadge({ ...zone, thermostat: off, phase: "blocked", blocked: true }, undefined)).toEqual({ label: "Off", kind: "off" });
  });

  it("shows Blocked for a blocked Zone that is on, whatever its phase", () => {
    expect(zoneBadge({ ...zone, phase: "idle", blocked: true }, undefined)).toEqual({ label: "Blocked", kind: "blocked" });
    expect(zoneBadge({ ...zone, phase: "blocked", blocked: true }, undefined)).toEqual({ label: "Blocked", kind: "blocked" });
  });

  it("shows the phase of a Zone that is on and not blocked", () => {
    expect(zoneBadge(zone, undefined)).toEqual({ label: "Heating", kind: "phase" });
    expect(zoneBadge({ ...zone, phase: "idle" }, undefined)).toEqual({ label: "Idle", kind: "phase" });
    expect(zoneBadge({ ...zone, thermostat: { ...zone.thermostat, hvac_mode: null }, phase: "idle" }, undefined)).toEqual({ label: "Idle", kind: "phase" });
  });

  it("uses Home Assistant's translation of Off", () => {
    const localize = (key: string) => (key === "component.climate.entity_component._.state.off" ? "Aus" : "");
    expect(zoneBadge({ ...zone, thermostat: off }, localize).label).toBe("Aus");
  });
});
