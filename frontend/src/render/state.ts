import { html, nothing, type TemplateResult } from "lit";
import type { PlantState } from "../store";
import type { StreamStatus } from "../stream";
import type { PlantSnapshot } from "../types";

export function retryText(delayMs: number): string {
  return `Retrying in ${Math.round(delayMs / 1000)} s.`;
}

/** A whole-card message, such as a setup prompt or a terminal stream state. */
export function renderState(eyebrow: string, title: string, message: string, role: "status" | "alert", detail?: string): TemplateResult {
  return html`<ha-card class="state-card" data-visual=${role === "alert" ? "attention" : "idle"}>
    <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">${eyebrow}</p><h2>${title}</h2></div></div>
    <p class=${role === "alert" ? "notice error" : "notice"} role=${role} dir="auto">${message}</p>
    ${detail ? html`<p class="meta" dir="auto">${detail}</p>` : nothing}
  </ha-card>`;
}

export function renderLoading(reconnecting: boolean): TemplateResult {
  return html`<ha-card class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${reconnecting ? "Reconnecting to Home Assistant…" : "Loading Plant snapshot…"}</p>
  </ha-card>`;
}

/** The snapshot a card can render, or null when it must show a state card. */
export function showableSnapshot(state: PlantState): PlantSnapshot | null {
  return state.snapshotError ? null : state.snapshot;
}

/**
 * The card for a Plant without a showable snapshot: an unsupported
 * snapshot, a terminal or unavailable stream, a retry, or loading.
 */
export function renderUnservedPlant(eyebrow: string, state: PlantState): TemplateResult {
  if (state.snapshotError) {
    return renderState(eyebrow, "Card update needed", state.snapshotError, "alert", "Reload the browser after upgrading Hydronicus so the card and the integration match.");
  }
  const stream = state.status;
  switch (stream.kind) {
    case "not_found":
      return renderState(eyebrow, "Plant not found", "This Hydronicus Plant was not found. Choose another Plant in the card editor.", "alert");
    case "unauthorized":
      return renderState(eyebrow, "No access", "You do not have access to this Hydronicus Plant.", "alert");
    case "unavailable":
      return renderState(eyebrow, "Plant unavailable", "The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.", "status");
    case "retrying":
      return renderState(eyebrow, "Connection needs attention", stream.message, "alert", retryText(stream.delayMs));
    default:
      return renderLoading(stream.kind === "reconnecting");
  }
}

/** The notice above a snapshot that may be out of date. */
export function renderStreamNotice(stream: StreamStatus): TemplateResult | typeof nothing {
  if (stream.kind === "reconnecting") {
    return html`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`;
  }
  if (stream.kind === "retrying") {
    return html`<p class="notice" role="status" dir="auto">${stream.message} ${retryText(stream.delayMs)} The values below may be out of date.</p>`;
  }
  return nothing;
}

export function renderActionError(message: string | null, dismiss: () => void): TemplateResult | typeof nothing {
  if (!message) return nothing;
  return html`<div class="action-error" role="alert"><span dir="auto">${message}</span><button type="button" @click=${dismiss}>Dismiss</button></div>`;
}
