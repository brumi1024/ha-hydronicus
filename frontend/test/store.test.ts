import { afterEach, describe, expect, it, vi } from "vitest";
import { PlantStore, type PlantState } from "../src/store";
import type { HomeAssistantConnection } from "../src/types";
import { FakeConnection, makeSnapshot, OTHER_PLANT_ID, PLANT_ID, settle } from "./fixtures";

function connectionOf(fake: FakeConnection): HomeAssistantConnection {
  return fake as unknown as HomeAssistantConnection;
}

/** A listener that records every state it receives. */
function recorder(): { states: PlantState[]; listener: (state: PlantState) => void; get last(): PlantState } {
  const states: PlantState[] = [];
  return {
    states,
    listener: (state) => states.push(state),
    get last() {
      const state = states.at(-1);
      if (!state) throw new Error("No state was received.");
      return state;
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("Shared Plant store", () => {
  it("shares one subscription between listeners of the same Plant", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const first = recorder();
    const second = recorder();

    store.subscribe(connectionOf(fake), PLANT_ID, first.listener);
    store.subscribe(connectionOf(fake), PLANT_ID, second.listener);
    await settle();
    fake.last.emit({ snapshot: makeSnapshot() });

    expect(fake.subscriptions).toHaveLength(1);
    expect(first.last.snapshot?.plant.name).toBe("Test plant");
    // Both see the same parsed snapshot object.
    expect(second.last.snapshot).toBe(first.last.snapshot);
  });

  it("gives a late listener the current state immediately", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    await settle();
    fake.last.emit({ snapshot: makeSnapshot() });

    const late = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, late.listener);

    expect(late.states).toHaveLength(1);
    expect(late.last.status.kind).toBe("live");
    expect(late.last.snapshot?.plant.name).toBe("Test plant");
  });

  it("keeps separate subscriptions per Plant and per connection", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const other = new FakeConnection();
    store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    store.subscribe(connectionOf(fake), OTHER_PLANT_ID, () => undefined);
    store.subscribe(connectionOf(other), PLANT_ID, () => undefined);
    await settle();

    expect(fake.subscriptions.map((subscription) => subscription.message.plant_id)).toEqual([PLANT_ID, OTHER_PLANT_ID]);
    expect(other.subscriptions).toHaveLength(1);
  });

  it("unsubscribes only when the last listener is released", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const releaseFirst = store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    const releaseSecond = store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    await settle();

    releaseFirst();
    releaseFirst();
    await settle();
    expect(fake.last.unsubscribed).toBe(false);

    releaseSecond();
    await settle();
    expect(fake.last.unsubscribed).toBe(true);

    // A new listener starts a new subscription.
    store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    await settle();
    expect(fake.subscriptions).toHaveLength(2);
    expect(fake.last.unsubscribed).toBe(false);
  });

  it("keeps the subscription when a listener is replaced in the same task", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const release = store.subscribe(connectionOf(fake), PLANT_ID, () => undefined);
    await settle();

    // Lovelace moving a card detaches and reattaches it synchronously.
    release();
    const again = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, again.listener);
    await settle();

    expect(fake.subscriptions).toHaveLength(1);
    expect(fake.last.unsubscribed).toBe(false);
    expect(again.last.status.kind).toBe("connecting");
  });

  it("fans a reconnect out to every listener and resubscribes once", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const first = recorder();
    const second = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, first.listener);
    store.subscribe(connectionOf(fake), PLANT_ID, second.listener);
    await settle();
    fake.last.emit({ snapshot: makeSnapshot() });

    fake.fire("disconnected");
    for (const listener of [first, second]) {
      expect(listener.last.status.kind).toBe("reconnecting");
      // The last snapshot stays visible, with a notice, while reconnecting.
      expect(listener.last.snapshot).not.toBeNull();
    }

    fake.fire("ready");
    await settle();
    expect(fake.subscriptions).toHaveLength(2);
    expect(fake.subscriptions[0].unsubscribed).toBe(false);
    fake.last.emit({ snapshot: makeSnapshot() });
    expect(first.last.status.kind).toBe("live");
    expect(second.last.status.kind).toBe("live");
  });

  it("retries once for all listeners with backoff and stops for all on a terminal error", async () => {
    vi.useFakeTimers();
    const store = new PlantStore();
    const fake = new FakeConnection();
    fake.autoResolve = false;
    const first = recorder();
    const second = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, first.listener);
    store.subscribe(connectionOf(fake), PLANT_ID, second.listener);

    fake.last.reject({ code: "unknown_error", message: "Boom" });
    await settle();
    expect(second.last.status).toMatchObject({ kind: "retrying", attempt: 1, delayMs: 1_000 });

    await vi.advanceTimersByTimeAsync(1_000);
    expect(fake.subscriptions).toHaveLength(2);
    fake.last.reject({ code: "unauthorized", message: "No." });
    await settle();
    await vi.advanceTimersByTimeAsync(300_000);

    expect(fake.subscriptions).toHaveLength(2);
    expect(first.last.status.kind).toBe("unauthorized");
    expect(second.last.status.kind).toBe("unauthorized");
  });

  it("drops the snapshot while the Plant is not served", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const listener = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, listener.listener);
    await settle();
    fake.last.emit({ snapshot: makeSnapshot() });

    fake.last.emit({ status: "unavailable", plant_id: PLANT_ID });
    expect(listener.last).toMatchObject({ status: { kind: "unavailable" }, snapshot: null });
  });

  it("reports an unsupported snapshot once for every listener", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const listener = recorder();
    store.subscribe(connectionOf(fake), PLANT_ID, listener.listener);
    await settle();

    fake.last.emit({ snapshot: { ...makeSnapshot(), schema_version: 99 } });
    expect(listener.last.snapshot).toBeNull();
    expect(listener.last.snapshotError).toContain("Unsupported Hydronicus snapshot schema");

    fake.last.emit({ snapshot: makeSnapshot() });
    expect(listener.last.snapshotError).toBeNull();
  });

  it("reads one snapshot and releases the subscription afterwards", async () => {
    const store = new PlantStore();
    const fake = new FakeConnection();
    const pending = store.snapshot(connectionOf(fake), PLANT_ID);
    await settle();
    fake.last.emit({ snapshot: makeSnapshot() });

    expect((await pending)?.plant.name).toBe("Test plant");
    await settle();
    expect(fake.last.unsubscribed).toBe(true);
  });

  it("gives up reading a snapshot after the timeout", async () => {
    vi.useFakeTimers();
    const store = new PlantStore();
    const fake = new FakeConnection();
    const pending = store.snapshot(connectionOf(fake), PLANT_ID, 500);
    await vi.advanceTimersByTimeAsync(500);

    expect(await pending).toBeNull();
    await settle();
    expect(fake.last.unsubscribed).toBe(true);
  });
});
