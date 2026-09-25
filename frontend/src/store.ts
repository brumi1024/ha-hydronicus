import { parseSnapshot } from "./logic";
import { errorMessage, PlantStream, type Scheduler, type StreamStatus } from "./stream";
import type { HomeAssistantConnection, PlantSnapshot } from "./types";

/** What every card following one Plant sees. */
export interface PlantState {
  readonly status: StreamStatus;
  /** The last valid snapshot; null while none is known or the Plant is not served. */
  readonly snapshot: PlantSnapshot | null;
  /** Why the last snapshot could not be shown, such as an unsupported schema. */
  readonly snapshotError: string | null;
}

export type PlantListener = (state: PlantState) => void;
export type Release = () => void;

export const IDLE_PLANT_STATE: PlantState = { status: { kind: "idle" }, snapshot: null, snapshotError: null };

/** Statuses in which the backend no longer serves the Plant to this user. */
const UNSERVED = new Set<StreamStatus["kind"]>(["idle", "unavailable", "not_found", "unauthorized"]);

/**
 * One `hydronicus/subscribe_plant` stream shared by every listener of the
 * same connection and Plant. It parses each snapshot once and fans the
 * resulting state out.
 */
class PlantFeed {
  readonly listeners = new Set<PlantListener>();
  private current: PlantState = IDLE_PLANT_STATE;
  private readonly stream: PlantStream;

  constructor(scheduler: Scheduler | undefined) {
    this.stream = new PlantStream(
      {
        onStatus: (status) => this.statusChanged(status),
        onSnapshot: (snapshot) => this.snapshotReceived(snapshot),
      },
      scheduler,
    );
  }

  get state(): PlantState {
    return this.current;
  }

  open(connection: HomeAssistantConnection, plantId: string): void {
    this.stream.connect(connection, plantId);
  }

  close(): void {
    this.stream.disconnect();
  }

  private statusChanged(status: StreamStatus): void {
    // Controls must never act on a Plant the backend no longer serves.
    const snapshot = UNSERVED.has(status.kind) ? null : this.current.snapshot;
    this.publish({ ...this.current, status, snapshot });
  }

  private snapshotReceived(candidate: unknown): void {
    try {
      this.publish({ ...this.current, snapshot: parseSnapshot(candidate), snapshotError: null });
    } catch (error) {
      this.publish({ ...this.current, snapshot: null, snapshotError: errorMessage(error, "Unsupported Hydronicus snapshot.") });
    }
  }

  private publish(state: PlantState): void {
    this.current = state;
    for (const listener of [...this.listeners]) listener(state);
  }
}

/**
 * The per-page source of Plant state. Any number of cards for the same
 * connection and Plant share one subscription, with its retry, reconnect,
 * and terminal-status handling. Releasing the last listener unsubscribes.
 */
export class PlantStore {
  private readonly feeds = new WeakMap<HomeAssistantConnection, Map<string, PlantFeed>>();

  constructor(private readonly scheduler?: Scheduler) {}

  /**
   * Follow one Plant. The listener receives the current state immediately
   * and every change after it, until the returned function is called.
   */
  subscribe(connection: HomeAssistantConnection, plantId: string, listener: PlantListener): Release {
    let byPlant = this.feeds.get(connection);
    if (!byPlant) {
      byPlant = new Map();
      this.feeds.set(connection, byPlant);
    }
    let feed = byPlant.get(plantId);
    const created = !feed;
    if (!feed) {
      feed = new PlantFeed(this.scheduler);
      byPlant.set(plantId, feed);
    }
    feed.listeners.add(listener);
    if (created) feed.open(connection, plantId);
    else listener(feed.state);

    const owner = byPlant;
    const shared = feed;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      shared.listeners.delete(listener);
      if (shared.listeners.size) return;
      // Close on the next microtask, so a card that Lovelace moves within
      // the page, which detaches and reattaches it synchronously, keeps the
      // subscription instead of ending and starting it again.
      queueMicrotask(() => {
        if (shared.listeners.size || owner.get(plantId) !== shared) return;
        owner.delete(plantId);
        shared.close();
      });
    };
  }

  /**
   * The Plant's current snapshot, waiting briefly for the first one. It
   * joins a shared stream when one exists and releases it afterwards.
   */
  snapshot(connection: HomeAssistantConnection, plantId: string, timeoutMs = 2_000): Promise<PlantSnapshot | null> {
    return new Promise((resolve) => {
      let done = false;
      const finish = (snapshot: PlantSnapshot | null) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        // The listener can fire during subscribe, before `release` is assigned.
        queueMicrotask(() => release());
        resolve(snapshot);
      };
      const timer = setTimeout(() => finish(null), timeoutMs);
      const release = this.subscribe(connection, plantId, (state) => {
        if (state.snapshot) finish(state.snapshot);
        else if (["not_found", "unauthorized"].includes(state.status.kind) || state.snapshotError) finish(null);
      });
    });
  }
}

export const plantStore = new PlantStore();
