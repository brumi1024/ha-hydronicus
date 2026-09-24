import type { HomeAssistantConnection, PlantStreamEvent, UnsubscribeFunc } from "./types";

export const SUBSCRIBE_PLANT = "hydronicus/subscribe_plant";
export const RETRY_BASE_MS = 1_000;
export const RETRY_MAX_MS = 60_000;

export type StreamStatus =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "live" }
  | { kind: "unavailable" }
  | { kind: "reconnecting" }
  | { kind: "retrying"; attempt: number; delayMs: number; message: string }
  | { kind: "not_found" }
  | { kind: "unauthorized" };

export interface PlantStreamHost {
  onStatus(status: StreamStatus): void;
  onSnapshot(snapshot: unknown): void;
}

export interface Scheduler {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

const defaultScheduler: Scheduler = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
};

function errorCode(error: unknown): string | undefined {
  return typeof error === "object" && error !== null && "code" in error ? String(error.code) : undefined;
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null && "message" in error && error.message) {
    return String(error.message);
  }
  return fallback;
}

function release(unsubscribe: UnsubscribeFunc | undefined): void {
  if (!unsubscribe) return;
  try {
    // The backend may already have closed the subscription.
    void Promise.resolve(unsubscribe()).catch(() => undefined);
  } catch {
    // Ignore a synchronous failure for the same reason.
  }
}

/**
 * One Plant snapshot stream for one card.
 *
 * It subscribes exactly once per connection and Plant, retries transient
 * failures with exponential backoff, stops on terminal errors, and handles
 * reconnects itself so that a failed resubscribe is never silent.
 */
export class PlantStream {
  private connection: HomeAssistantConnection | undefined;
  private plantId: string | undefined;
  private generation = 0;
  private unsubscribe: UnsubscribeFunc | undefined;
  private retryHandle: unknown;
  private attempt = 0;
  private current: StreamStatus = { kind: "idle" };

  constructor(
    private readonly host: PlantStreamHost,
    private readonly scheduler: Scheduler = defaultScheduler,
  ) {}

  get status(): StreamStatus {
    return this.current;
  }

  /** Follow one Plant on one connection; repeated calls are no-ops. */
  connect(connection: HomeAssistantConnection | undefined, plantId: string | undefined): void {
    if (connection === this.connection && plantId === this.plantId) return;
    this.disconnect();
    if (!connection || !plantId) return;
    this.connection = connection;
    this.plantId = plantId;
    connection.addEventListener?.("disconnected", this.handleDisconnected);
    connection.addEventListener?.("ready", this.handleReady);
    this.subscribe();
  }

  disconnect(): void {
    this.cancelRetry();
    this.generation += 1;
    release(this.unsubscribe);
    this.unsubscribe = undefined;
    this.connection?.removeEventListener?.("disconnected", this.handleDisconnected);
    this.connection?.removeEventListener?.("ready", this.handleReady);
    this.connection = undefined;
    this.plantId = undefined;
    this.attempt = 0;
    this.setStatus({ kind: "idle" });
  }

  private subscribe(): void {
    const connection = this.connection;
    const plantId = this.plantId;
    if (!connection || !plantId) return;
    this.cancelRetry();
    const generation = ++this.generation;
    if (this.current.kind !== "reconnecting" && this.current.kind !== "retrying") {
      this.setStatus({ kind: "connecting" });
    }
    connection
      .subscribeMessage((event) => this.handleEvent(generation, event), { type: SUBSCRIBE_PLANT, plant_id: plantId }, { resubscribe: false })
      .then((unsubscribe) => {
        if (generation !== this.generation) {
          release(unsubscribe);
          return;
        }
        this.unsubscribe = unsubscribe;
      })
      .catch((error: unknown) => {
        if (generation !== this.generation) return;
        this.handleError(error);
      });
  }

  private handleEvent(generation: number, event: PlantStreamEvent): void {
    if (generation !== this.generation) return;
    if (event.snapshot !== undefined && event.snapshot !== null) {
      this.attempt = 0;
      this.setStatus({ kind: "live" });
      this.host.onSnapshot(event.snapshot);
      return;
    }
    if (event.status === "unavailable") this.setStatus({ kind: "unavailable" });
    else if (event.status === "unauthorized") this.stop({ kind: "unauthorized" });
    else if (event.status === "plant_not_found") this.stop({ kind: "not_found" });
  }

  private handleError(error: unknown): void {
    const code = errorCode(error);
    if (code === "plant_not_found") {
      this.stop({ kind: "not_found" });
      return;
    }
    if (code === "unauthorized") {
      this.stop({ kind: "unauthorized" });
      return;
    }
    const delayMs = Math.min(RETRY_BASE_MS * 2 ** this.attempt, RETRY_MAX_MS);
    this.attempt += 1;
    this.setStatus({
      kind: "retrying",
      attempt: this.attempt,
      delayMs,
      message: errorMessage(error, "The Hydronicus Plant stream failed."),
    });
    this.retryHandle = this.scheduler.setTimeout(() => {
      this.retryHandle = undefined;
      this.subscribe();
    }, delayMs);
  }

  /** Enter a terminal state; only a new Plant, connection, or reconnect restarts. */
  private stop(status: StreamStatus): void {
    this.cancelRetry();
    this.generation += 1;
    release(this.unsubscribe);
    this.unsubscribe = undefined;
    this.setStatus(status);
  }

  private readonly handleDisconnected = (): void => {
    // The socket is gone, and with it the subscription. Its unsubscribe
    // function must not be called later, because command IDs restart on the
    // next socket and could match another subscription.
    this.cancelRetry();
    this.generation += 1;
    this.unsubscribe = undefined;
    this.setStatus({ kind: "reconnecting" });
  };

  private readonly handleReady = (): void => {
    this.attempt = 0;
    this.subscribe();
  };

  private cancelRetry(): void {
    if (this.retryHandle !== undefined) this.scheduler.clearTimeout(this.retryHandle);
    this.retryHandle = undefined;
  }

  private setStatus(status: StreamStatus): void {
    this.current = status;
    this.host.onStatus(status);
  }
}
