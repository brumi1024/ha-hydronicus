export type Density = "comfortable" | "compact";

export interface PlantCardConfig {
  type: "custom:hydronicus-plant-card";
  plant: string;
  density?: Density;
}

export interface PlantSummary {
  id: string;
  name: string;
  status: string;
  health: string;
  requested_mode: string;
  active_mode: string;
}

export interface Alert {
  code: string;
  severity: "critical" | "error" | "warning" | "info";
  priority: number;
  scope: string;
  message: string;
}

export interface ZoneSnapshot {
  id: string;
  name: string;
  climate_entity_id?: string;
  current_temperature: number | null;
  target_temperature: number;
  preset: string;
  preset_modes: string[];
  demand: boolean;
  phase: string;
  blocked: boolean;
  blocked_reason: string | null;
  sensor_status: {
    usable: number;
    optional_excluded: number;
    required_blocking: number;
  };
  cooling: {
    demand: boolean;
    status: string | null;
    dew_point: number | null;
    condensation_margin: number | null;
    blocked: boolean;
    reason: string | null;
    interlocks: Array<{ id: string; status: string; reason: string }>;
  };
  route_ids: string[];
  coupling_group_ids: string[];
}

export interface PlantSnapshot {
  schema_version: number;
  plant: {
    id: string;
    name: string;
    status: string;
    health: string;
    requested_mode: string;
    active_mode: string;
    changeover: { phase: string; target_mode: string | null; reason: string };
    controller: { evaluated: boolean; mode_explanation: string | null };
    source: {
      active_id: string | null;
      active_name: string | null;
      recommended_id: string | null;
      recommended_name: string | null;
    };
    execution_boundary: {
      mode: string;
      dry_run: boolean;
      forced_shadow: string[];
      message: string;
    };
  };
  controls: { requested_mode: string | null; safe_shutdown: string | null };
  zones: ZoneSnapshot[];
  topology: {
    routes: Array<{ id: string; zone_id: string; circuit_id: string; enabled: boolean }>;
    circuits: Array<{
      id: string;
      name: string;
      valve_ids: string[];
      pump_id: string;
      cooling_enabled: boolean;
      route_ids: string[];
    }>;
    coupling_groups: Array<{
      id: string;
      kind: string;
      actuator_id: string;
      circuit_ids: string[];
      zone_ids: string[];
      message: string;
    }>;
    summary: Record<string, number>;
    warnings: Array<{ code: string; message: string }>;
    active_consumer_sets: { valves: unknown[]; pumps: unknown[] };
  };
  delivery_paths: Array<{
    id: string;
    zone_id: string;
    circuit_id: string;
    status: string;
    problem: string | null;
    coupled: boolean;
    nodes: Array<{ kind: string; id: string; name: string; state: string }>;
  }>;
  actuators: Array<{
    id: string;
    name: string;
    kind: string;
    state: string;
    requested: string | null;
    observed: string;
    ready: boolean;
    blocked: boolean;
    mismatch: boolean;
    reason: string | null;
    active_consumers: Array<{ id: string; name: string }>;
  }>;
  sources: Array<Record<string, unknown>>;
  alerts: Alert[];
  explanations: Array<{ order: number; scope: string; code: string; message: string }>;
  execution: {
    boundary: Record<string, unknown>;
    operations: {
      proposed: Array<Record<string, unknown>>;
      executed: Array<Record<string, unknown>>;
      suppressed: Array<Record<string, unknown>>;
      failed: Array<Record<string, unknown>>;
      timed_out: Array<Record<string, unknown>>;
    };
  };
  safe_shutdown: { active: boolean; phase: string; message: string };
}

export interface HomeAssistantConnection {
  sendMessagePromise<T extends Record<string, unknown> = Record<string, unknown>>(
    message: Record<string, unknown>,
  ): Promise<T>;
  subscribeMessage(
    callback: (message: { snapshot?: unknown }) => void,
    message: Record<string, unknown>,
  ): Promise<() => void>;
}

export interface HomeAssistantLike {
  connection: HomeAssistantConnection;
  callService(domain: string, service: string, data: Record<string, unknown>): Promise<void>;
}
