export type Density = "comfortable" | "compact";

export interface PlantCardConfig {
  type: "custom:hydronicus-plant-card";
  /** The Plant UUID; an empty string means the card still needs a Plant. */
  plant: string;
  density?: Density;
}

export interface PlantSummary {
  id: string;
  name: string;
  status?: string;
  health?: string;
  requested_mode?: string;
  active_mode?: string;
}

export interface Alert {
  code: string;
  severity: "critical" | "error" | "warning" | "info";
  priority: number;
  scope: string;
  message: string;
}

/** Every temperature in a snapshot is in degrees Celsius. */
export interface ZoneSnapshot {
  id: string;
  name: string;
  thermostat: {
    kind: "hydronicus" | "external_climate";
    state: "available" | "blocked";
    target_temperature: number | null;
    current_temperature: number | null;
    preset: string | null;
    preset_modes: string[];
    control_entity_id: string | null;
    explanation: string;
  };
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
    /** A temperature difference in kelvin (equal to a Celsius delta). */
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
    routes: Array<{ id: string; zone_id: string; circuit_id: string; enabled?: boolean }>;
    circuits: Array<{
      id: string;
      name: string;
      valve_ids: string[];
      pump_id: string;
      cooling_enabled?: boolean;
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

/** One event on the `hydronicus/subscribe_plant` stream. */
export interface PlantStreamEvent {
  snapshot?: unknown;
  status?: "unavailable" | "unauthorized" | "plant_not_found";
  plant_id?: string;
}

export type UnsubscribeFunc = () => Promise<void> | void;

/** The subset of home-assistant-js-websocket's Connection that the card uses. */
export interface HomeAssistantConnection {
  sendMessagePromise<T>(message: Record<string, unknown>): Promise<T>;
  subscribeMessage(
    callback: (message: PlantStreamEvent) => void,
    message: Record<string, unknown>,
    options?: { resubscribe?: boolean },
  ): Promise<UnsubscribeFunc>;
  addEventListener?(type: "ready" | "disconnected", listener: () => void): void;
  removeEventListener?(type: "ready" | "disconnected", listener: () => void): void;
}

export type CallService = (
  domain: string,
  service: string,
  data: Record<string, unknown>,
) => Promise<unknown>;

export interface FrontendLocale {
  language: string;
  number_format?: string;
}

export interface UnitSystem {
  temperature?: string;
}

/** The subset of the frontend `hass` object that the card falls back to. */
export interface HomeAssistantLike {
  connection: HomeAssistantConnection;
  callService: CallService;
  config?: { unit_system?: UnitSystem };
  language?: string;
  locale?: FrontendLocale;
}

/** Values of the Home Assistant frontend context groups the card consumes. */
export interface HassConnectionContextValue {
  connection: HomeAssistantConnection;
  connected?: boolean;
}

export interface HassApiContextValue {
  callService: CallService;
}

export interface HassConfigContextValue {
  config: { unit_system?: UnitSystem };
}

export interface HassInternationalizationContextValue {
  language: string;
  locale: FrontendLocale;
}
