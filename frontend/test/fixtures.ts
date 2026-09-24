import type { PlantSnapshot, ZoneSnapshot } from "../src/types";

export const PLANT_ID = "00000000-0000-4000-8000-000000000001";
export const OTHER_PLANT_ID = "00000000-0000-4000-8000-000000000002";

export function makeZone(overrides: Partial<ZoneSnapshot> = {}): ZoneSnapshot {
  return {
    id: "zone-1",
    name: "Living room",
    thermostat: {
      kind: "hydronicus",
      state: "available",
      control_entity_id: "climate.hydronic_living_room",
      current_temperature: 20,
      target_temperature: 21,
      preset: "comfort",
      preset_modes: ["comfort", "eco"],
      explanation: "Hydronicus owns this Zone's digital thermostat.",
    },
    demand: true,
    phase: "heating",
    blocked: false,
    blocked_reason: null,
    sensor_status: { usable: 1, optional_excluded: 0, required_blocking: 0 },
    cooling: {
      demand: false,
      status: null,
      dew_point: null,
      condensation_margin: null,
      blocked: false,
      reason: null,
      interlocks: [],
    },
    route_ids: ["route-1"],
    coupling_group_ids: [],
    ...overrides,
  };
}

export function makeSnapshot(overrides: Partial<PlantSnapshot> = {}): PlantSnapshot {
  return {
    schema_version: 2,
    plant: {
      id: PLANT_ID,
      name: "Test plant",
      status: "heating",
      health: "healthy",
      requested_mode: "heating",
      active_mode: "heating",
      changeover: { phase: "idle", target_mode: null, reason: "" },
      controller: { evaluated: true, mode_explanation: "" },
      source: { active_id: null, active_name: null, recommended_id: null, recommended_name: null },
      execution_boundary: { mode: "dry_run", dry_run: true, forced_shadow: [], message: "" },
    },
    controls: { requested_mode: "select.hydronic_mode", safe_shutdown: "button.hydronic_shutdown" },
    zones: [makeZone()],
    alerts: [],
    topology: {
      routes: [],
      circuits: [],
      coupling_groups: [],
      summary: {},
      warnings: [],
      active_consumer_sets: { valves: [], pumps: [] },
    },
    delivery_paths: [],
    actuators: [],
    sources: [],
    explanations: [],
    execution: {
      boundary: {},
      operations: { proposed: [], executed: [], suppressed: [], failed: [], timed_out: [] },
    },
    safe_shutdown: { active: false, phase: "idle", message: "" },
    ...overrides,
  };
}

type Callback = (message: Record<string, unknown>) => void;

export interface FakeSubscription {
  message: Record<string, unknown>;
  callback: Callback;
  options: Record<string, unknown> | undefined;
  unsubscribed: boolean;
  resolve(): void;
  reject(error: unknown): void;
  emit(event: Record<string, unknown>): void;
}

/** A home-assistant-js-websocket Connection double with explicit control. */
export class FakeConnection {
  subscriptions: FakeSubscription[] = [];
  sent: Array<Record<string, unknown>> = [];
  autoResolve = true;
  plants: Array<Record<string, unknown>> = [];
  private listeners = new Map<string, Set<() => void>>();

  subscribeMessage(
    callback: Callback,
    message: Record<string, unknown>,
    options?: Record<string, unknown>,
  ): Promise<() => Promise<void>> {
    return new Promise((resolve, reject) => {
      const subscription: FakeSubscription = {
        message,
        callback,
        options,
        unsubscribed: false,
        resolve: () =>
          resolve(async () => {
            subscription.unsubscribed = true;
          }),
        reject,
        emit: (event) => callback(event),
      };
      this.subscriptions.push(subscription);
      if (this.autoResolve) subscription.resolve();
    });
  }

  async sendMessagePromise<T>(message: Record<string, unknown>): Promise<T> {
    this.sent.push(message);
    if (message.type === "hydronicus/list_plants") {
      return { schema_version: 2, plants: this.plants } as T;
    }
    throw { code: "unknown_command", message: "Unknown command." };
  }

  addEventListener(type: string, listener: () => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: () => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  fire(type: "ready" | "disconnected"): void {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }

  get active(): FakeSubscription[] {
    return this.subscriptions.filter((subscription) => !subscription.unsubscribed);
  }

  get last(): FakeSubscription {
    const subscription = this.subscriptions.at(-1);
    if (!subscription) throw new Error("No subscription was made.");
    return subscription;
  }
}

export interface FakeHass {
  connection: FakeConnection;
  connected: boolean;
  callService: (
    domain: string,
    service: string,
    data: Record<string, unknown>,
    target?: Record<string, unknown>,
    notifyOnError?: boolean,
  ) => Promise<void>;
  calls: Array<{ domain: string; service: string; data: Record<string, unknown>; notifyOnError: boolean }>;
  failNextCall: string | null;
  config: { unit_system: { temperature: string } };
  language: string;
  locale: { language: string; number_format: string };
  localize?: (key: string) => string;
}

export function makeHass(overrides: Partial<FakeHass> = {}): FakeHass {
  const hass: FakeHass = {
    connection: new FakeConnection(),
    connected: true,
    calls: [],
    failNextCall: null,
    config: { unit_system: { temperature: "°C" } },
    language: "en",
    locale: { language: "en", number_format: "language" },
    // Like Home Assistant, notify on error unless told not to.
    async callService(domain, service, data, _target, notifyOnError = true) {
      hass.calls.push({ domain, service, data, notifyOnError });
      if (hass.failNextCall) {
        const message = hass.failNextCall;
        hass.failNextCall = null;
        throw { code: "home_assistant_error", message };
      }
    },
    ...overrides,
  };
  return hass;
}

/** Let pending promise callbacks and Lit updates settle. */
export async function settle(element?: { updateComplete: Promise<unknown> }): Promise<void> {
  for (let index = 0; index < 5; index += 1) await Promise.resolve();
  if (element) await element.updateComplete;
}
