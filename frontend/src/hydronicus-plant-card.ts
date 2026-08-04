import { LitElement, css, html, nothing } from "lit";
import { actionForMode, actionForPreset, actionForSafeShutdown, actionForTarget, adjustTarget, isFlowingState, operationLabel, parseSnapshot, phaseLabel, plantVisualState, prioritizedAlerts } from "./logic";
import type { HomeAssistantLike, PlantCardConfig, PlantSnapshot, PlantSummary, ZoneSnapshot } from "./types";

const MODES = ["auto", "idle", "heating", "cooling"];

class HydronicusPlantCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _snapshot: { state: true },
    _error: { state: true },
    _reconnecting: { state: true },
    _holdingShutdown: { state: true },
  };

  static styles = css`
    :host {
      display: block;
      color: var(--primary-text-color, #1c1c1c);
      --hydronicus-border: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 13%, transparent);
      --hydronicus-muted: var(--secondary-text-color, #5f6368);
      --hydronicus-surface: var(--ha-card-background, var(--card-background-color, #fff));
      --hydronicus-danger: var(--error-color, #ba1a1a);
      --hydronicus-warning: var(--warning-color, #8a5a00);
      --hydronicus-accent: var(--primary-color, #03a9f4);
      --hydronicus-heating-color: #ff9b62;
      --hydronicus-cooling-color: #55c9f6;
      --hydronicus-idle-color: var(--primary-color, #7b9bb4);
      --hydronicus-attention-color: var(--error-color, #ef6a72);
      --hydronicus-glass-blur: 24px;
      --hydronicus-glass-opacity: 68%;
      --hydronicus-flow-duration: 2.2s;
      --hydronicus-ambient-duration: 16s;
      --hydronicus-state-color: var(--hydronicus-idle-color);
      --hydronicus-state-rgb: 123 155 180;
      font-variant-numeric: tabular-nums;
    }

    .card {
      box-sizing: border-box;
      container-type: inline-size;
      overflow: hidden;
      position: relative;
      isolation: isolate;
      border: 1px solid color-mix(in srgb, white 42%, var(--hydronicus-border));
      border-radius: var(--ha-card-border-radius, 22px);
      background: var(--hydronicus-surface);
      background: color-mix(in srgb, var(--hydronicus-surface) var(--hydronicus-glass-opacity), transparent);
      box-shadow:
        inset 0 1px 0 color-mix(in srgb, white 48%, transparent),
        inset 0 -1px 0 color-mix(in srgb, var(--primary-text-color, #1c1c1c) 5%, transparent),
        var(--ha-card-box-shadow, 0 20px 50px rgba(20, 35, 50, 0.12));
      -webkit-backdrop-filter: blur(var(--hydronicus-glass-blur)) saturate(145%);
      backdrop-filter: blur(var(--hydronicus-glass-blur)) saturate(145%);
      padding: 1.15rem;
      animation: hydronicus-card-enter 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
    }

    .card::before {
      content: "";
      position: absolute;
      z-index: -2;
      inset: -35%;
      pointer-events: none;
      background:
        radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent) 0, transparent 32%),
        radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--hydronicus-accent) 13%, transparent) 0, transparent 30%),
        radial-gradient(circle at 74% 92%, color-mix(in srgb, white 15%, transparent) 0, transparent 34%);
      opacity: 0.82;
      transform: translate3d(-2%, -1%, 0) scale(1.02);
      animation: hydronicus-ambient var(--hydronicus-ambient-duration) ease-in-out infinite alternate;
    }

    .card::after {
      content: "";
      position: absolute;
      z-index: -1;
      inset: 0;
      pointer-events: none;
      border-radius: inherit;
      background: linear-gradient(145deg, color-mix(in srgb, white 14%, transparent), transparent 34%, color-mix(in srgb, var(--hydronicus-state-color) 5%, transparent));
    }

    .card[data-visual="heating"] {
      --hydronicus-state-color: var(--hydronicus-heating-color);
      --hydronicus-state-rgb: 255 155 98;
    }

    .card[data-visual="cooling"] {
      --hydronicus-state-color: var(--hydronicus-cooling-color);
      --hydronicus-state-rgb: 85 201 246;
    }

    .card[data-visual="attention"] {
      --hydronicus-state-color: var(--hydronicus-attention-color);
      --hydronicus-state-rgb: 239 106 114;
    }

    .card.compact { padding: 0.8rem; }
    .header, .row, .path-head, .action-row, .section-head, .plant-heading, .status-line, .boundary-copy { display: flex; align-items: center; gap: 0.65rem; }
    .header { justify-content: space-between; align-items: flex-start; gap: 1.2rem; }
    .header-copy { min-width: 0; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: clamp(1.18rem, 3cqi, 1.5rem); font-weight: 650; letter-spacing: -0.025em; overflow-wrap: anywhere; }
    h2 { font-size: 0.92rem; font-weight: 650; letter-spacing: 0.01em; }
    h3 { font-size: 0.9rem; font-weight: 650; }
    .muted, .meta { color: var(--hydronicus-muted); font-size: 0.8rem; line-height: 1.45; }
    .eyebrow { margin-bottom: 0.12rem; color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); font-size: 0.64rem; font-weight: 750; letter-spacing: 0.13em; text-transform: uppercase; }
    .plant-heading { align-items: flex-start; }
    .plant-mark {
      position: relative;
      flex: 0 0 2.7rem;
      width: 2.7rem;
      height: 2.7rem;
      border: 1px solid color-mix(in srgb, white 38%, var(--hydronicus-border));
      border-radius: 1rem;
      background: linear-gradient(145deg, color-mix(in srgb, white 20%, transparent), color-mix(in srgb, var(--hydronicus-state-color) 13%, transparent));
      box-shadow: inset 0 1px 0 color-mix(in srgb, white 50%, transparent), 0 8px 22px color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
    }
    .plant-mark::before {
      content: "";
      position: absolute;
      inset: 0.58rem;
      border: 2px solid color-mix(in srgb, var(--hydronicus-state-color) 30%, transparent);
      border-top-color: var(--hydronicus-state-color);
      border-radius: 50%;
      animation: hydronicus-spin 3.8s linear infinite;
    }
    .plant-mark::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 50%;
      width: 0.42rem;
      height: 0.42rem;
      border-radius: 50%;
      background: var(--hydronicus-state-color);
      box-shadow: 0 0 0 0.28rem color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
      transform: translate(-50%, -50%);
    }
    .status-line { flex-wrap: wrap; margin-top: 0.48rem; gap: 0.35rem; }
    .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 650; }
    .status-dot { width: 0.45rem; height: 0.45rem; border-radius: 50%; background: var(--hydronicus-state-color); box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 40%, transparent); animation: hydronicus-pulse 2.8s ease-out infinite; }
    .mode-detail { border-left: 1px solid var(--hydronicus-border); padding-left: 0.55rem; }
    .source-line { margin-top: 0.35rem; }
    .source-line strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
    .badge, .phase, .state { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.69rem; line-height: 1.2; white-space: nowrap; }
    .badge { font-weight: 750; letter-spacing: 0.02em; background: color-mix(in srgb, var(--hydronicus-warning) 12%, transparent); }
    .badge.dry-run, .state.proposed { color: var(--hydronicus-warning); }
    .badge.mixed, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
    .badge.active, .state.active, .state.ready { color: var(--success-color, #287d34); }
    .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
    .mode-control { display: flex; align-items: center; min-height: 2.35rem; border: 1px solid var(--hydronicus-border); border-radius: 0.78rem; background: color-mix(in srgb, var(--hydronicus-surface) 36%, transparent); padding-left: 0.62rem; }
    .control-label { color: var(--hydronicus-muted); font-size: 0.7rem; font-weight: 650; letter-spacing: 0.04em; text-transform: uppercase; }
    button, select { min-height: 2.35rem; border: 1px solid var(--hydronicus-border); border-radius: 0.78rem; background: color-mix(in srgb, var(--hydronicus-surface) 44%, transparent); color: inherit; font: inherit; padding: 0.38rem 0.62rem; transition: border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease, transform 120ms ease; }
    .mode-control select { border: 0; background: transparent; min-height: 2.25rem; }
    button { cursor: pointer; }
    button:hover, select:hover { border-color: color-mix(in srgb, var(--hydronicus-state-color) 46%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-surface) 58%, transparent); }
    button:active { transform: translateY(1px); }
    button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
    button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--hydronicus-accent); outline-offset: 2px; }
    .shutdown { position: relative; overflow: hidden; color: var(--hydronicus-danger); }
    .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--hydronicus-danger) 18%, transparent); transform: scaleX(0); transform-origin: left; }
    .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
    .button-label { position: relative; z-index: 1; }
    .hold-progress { flex-basis: 100%; text-align: right; font-size: 0.67rem; color: var(--hydronicus-danger); }
    .alert, .error, .boundary { margin-top: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: 0.8rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); box-shadow: inset 0 1px 0 color-mix(in srgb, white 28%, transparent); padding: 0.68rem 0.75rem; }
    .alert { position: relative; overflow: hidden; padding-left: 0.9rem; }
    .alert::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--hydronicus-warning); }
    .alert.error::before, .error::before { background: var(--hydronicus-danger); }
    .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
    .boundary-orb { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border-radius: 0.65rem; background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent); color: var(--hydronicus-state-color); }
    .boundary-orb::before { content: ""; width: 0.55rem; height: 0.55rem; border: 2px solid currentColor; border-radius: 50%; box-shadow: inset 0 0 0 2px color-mix(in srgb, currentColor 18%, transparent); }
    .boundary-copy { min-width: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
    .boundary-copy strong { font-size: 0.8rem; }
    section { margin-top: 1.05rem; }
    .section-head { justify-content: space-between; margin-bottom: 0.5rem; }
    .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
    .section-kicker::before { content: ""; width: 0.38rem; height: 0.38rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-state-color) 80%, transparent); }
    .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
    .zone, .path, .actuator, details { border: 1px solid var(--hydronicus-border); border-radius: 0.9rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); box-shadow: inset 0 1px 0 color-mix(in srgb, white 26%, transparent); }
    .zone, .path, .actuator { padding: 0.72rem; }
    .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
    .zone::before { content: ""; position: absolute; inset: 0 0 auto; height: 2px; background: var(--hydronicus-state-color); opacity: 0.18; transform: scaleX(0.35); transform-origin: left; transition: opacity 220ms ease, transform 380ms ease; }
    .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
    .zone[data-demand="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 30%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 7%, var(--hydronicus-surface) 38%); }
    .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 34%, var(--hydronicus-border)); }
    .row { justify-content: space-between; align-items: baseline; }
    .zone-title { min-width: 0; overflow-wrap: anywhere; }
    .zone-owner { margin-top: 0.12rem; }
    .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin: 0.65rem 0 0.5rem; }
    .metric { min-width: 0; border: 1px solid color-mix(in srgb, var(--hydronicus-border) 72%, transparent); border-radius: 0.72rem; background: color-mix(in srgb, var(--hydronicus-surface) 34%, transparent); padding: 0.52rem 0.58rem; }
    .metric.target { background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
    .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 680; letter-spacing: -0.035em; }
    .metric-unit { margin-left: 0.15rem; color: var(--hydronicus-muted); font-size: 0.72rem; }
    .metric-label { display: block; margin-top: 0.06rem; color: var(--hydronicus-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; }
    .zone-note { margin-top: 0.28rem; }
    .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.45rem; }
    .diagnostic-chip { border: 1px solid var(--hydronicus-border); border-radius: 999px; background: color-mix(in srgb, var(--hydronicus-surface) 28%, transparent); padding: 0.2rem 0.42rem; color: var(--hydronicus-muted); font-size: 0.64rem; }
    .diagnostic-chip.warning { color: var(--hydronicus-warning); border-color: color-mix(in srgb, var(--hydronicus-warning) 30%, var(--hydronicus-border)); }
    .diagnostic-chip.danger { color: var(--hydronicus-danger); border-color: color-mix(in srgb, var(--hydronicus-danger) 30%, var(--hydronicus-border)); }
    .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-top: 0.38rem; color: color-mix(in srgb, var(--hydronicus-warning) 80%, var(--hydronicus-muted)); }
    .coupling-note::before { content: ""; width: 0.34rem; height: 0.34rem; border: 1px solid currentColor; border-radius: 50%; box-shadow: 0.24rem 0 0 -1px color-mix(in srgb, currentColor 30%, transparent); }
    .zone-actions { display: flex; gap: 0.35rem; margin-top: 0.62rem; }
    .zone-actions button { min-width: 2.65rem; }
    .preset { flex: 1; min-width: 0; }
    .path-list, .actuator-list { display: grid; gap: 0.55rem; }
    .path { overflow: hidden; }
    .path-head { justify-content: space-between; flex-wrap: wrap; }
    .path-heading { display: flex; align-items: center; gap: 0.42rem; min-width: 0; }
    .path-heading::before { content: ""; flex: 0 0 auto; width: 0.43rem; height: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-muted) 55%, transparent); }
    .path[data-flowing="true"] .path-heading::before { background: var(--hydronicus-state-color); box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 36%, transparent); animation: hydronicus-pulse 2.4s ease-out infinite; }
    .path[data-status="blocked"] .path-heading::before { background: var(--hydronicus-danger); }
    .path-track { display: flex; align-items: stretch; margin-top: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding: 0.08rem 0.03rem 0.25rem; scroll-snap-type: inline proximity; scrollbar-color: color-mix(in srgb, var(--hydronicus-state-color) 25%, transparent) transparent; scrollbar-width: thin; }
    .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-width: 0; border: 1px solid var(--hydronicus-border); border-radius: 0.72rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); padding: 0.48rem 0.52rem; font-size: 0.74rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, box-shadow 220ms ease, background-color 220ms ease; }
    .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 34%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 8%, var(--hydronicus-surface) 38%); box-shadow: inset 0 1px 0 color-mix(in srgb, white 22%, transparent); }
    .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 36%, var(--hydronicus-border)); }
    .node-kind { color: var(--hydronicus-muted); font-size: 0.59rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
    .node-name { margin-top: 0.18rem; font-weight: 620; line-height: 1.25; }
    .node-state { display: flex; align-items: center; gap: 0.28rem; margin-top: 0.3rem; color: var(--hydronicus-muted); font-size: 0.64rem; }
    .node-state::before { content: ""; width: 0.3rem; height: 0.3rem; border-radius: 50%; background: currentColor; }
    .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); }
    .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-width: 1.2rem; align-self: center; height: 2px; margin: 0 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--hydronicus-muted) 24%, transparent); }
    .flow-link::before { content: ""; position: absolute; right: 0; top: 50%; width: 0.34rem; height: 0.34rem; border-top: 1px solid var(--hydronicus-muted); border-right: 1px solid var(--hydronicus-muted); transform: translateY(-50%) rotate(45deg); }
    .flow-link::after { content: ""; position: absolute; inset: -1px auto -1px 0; width: 58%; background: linear-gradient(90deg, transparent, var(--hydronicus-state-color), transparent); opacity: 0; transform: translateX(-120%); }
    .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent); }
    .path[data-flowing="true"] .flow-link::before { border-color: var(--hydronicus-state-color); }
    .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--hydronicus-flow-duration) linear infinite; }
    .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--hydronicus-danger) 30%, transparent); }
    .path-problem { margin-top: 0.5rem; color: var(--hydronicus-danger); }
    .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
    .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
    .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.48rem; }
    .consumer-chip { max-width: 100%; border: 1px solid var(--hydronicus-border); border-radius: 999px; background: color-mix(in srgb, var(--hydronicus-surface) 32%, transparent); padding: 0.2rem 0.42rem; color: var(--hydronicus-muted); font-size: 0.66rem; overflow-wrap: anywhere; }
    .consumer-chip strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
    details { overflow: hidden; padding: 0.62rem 0.72rem; }
    details + details { margin-top: 0.45rem; }
    summary { cursor: pointer; font-size: 0.82rem; font-weight: 650; }
    details[open] summary { margin-bottom: 0.25rem; }
    details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
    .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding: 0.48rem 0; border-top: 1px solid var(--hydronicus-border); font-size: 0.8rem; }
    .operation:first-child { border-top: 0; }
    .operation-marker { width: 0.4rem; height: 0.4rem; margin-top: 0.35rem; border-radius: 50%; background: var(--hydronicus-muted); }
    .operation[data-result="proposed"] .operation-marker { background: var(--hydronicus-warning); }
    .operation[data-result="executed"] .operation-marker { background: var(--success-color, #287d34); }
    .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--hydronicus-danger); }
    .operation-copy { min-width: 0; }
    .empty-state { padding: 0.8rem; border: 1px dashed var(--hydronicus-border); border-radius: 0.8rem; text-align: center; }
    .loading-card { min-height: 12rem; }
    .loading-head { display: flex; align-items: center; gap: 0.65rem; }
    .loading-mark, .skeleton { background: linear-gradient(105deg, color-mix(in srgb, var(--hydronicus-surface) 30%, transparent) 20%, color-mix(in srgb, white 24%, transparent) 38%, color-mix(in srgb, var(--hydronicus-surface) 30%, transparent) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
    .loading-mark { width: 2.7rem; height: 2.7rem; border-radius: 1rem; }
    .skeleton { width: min(16rem, 62cqi); height: 0.72rem; border-radius: 999px; }
    .skeleton.short { width: min(10rem, 42cqi); margin-top: 0.45rem; }
    .loading-panel { height: 4.2rem; margin-top: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: 0.9rem; }
    @container (max-width: 680px) {
      .header { display: block; }
      .controls { justify-content: flex-start; margin-top: 0.7rem; }
      .hold-progress { text-align: left; }
    }
    @container (max-width: 440px) {
      .zone-grid { grid-template-columns: 1fr; }
      .mode-detail { flex-basis: 100%; border-left: 0; padding-left: 0; }
      .boundary-copy { display: block; }
      .boundary-copy .control-label { display: block; margin-bottom: 0.12rem; }
      .section-head { align-items: flex-start; }
      .section-head > .meta { text-align: right; }
    }
    @media (max-width: 560px) {
      .card { padding: 0.75rem; }
      .controls { justify-content: flex-start; }
    }
    @media (prefers-reduced-motion: reduce) {
      .card, .card::before, .plant-mark::before, .status-dot, .path-heading::before, .path[data-flowing="true"] .flow-link::after, details[open] .operation, .loading-mark, .skeleton { animation: none !important; }
      button, select, .zone, .node { transition-duration: 0.01ms !important; }
      .path[data-flowing="true"] .flow-link::after { opacity: 0.65; transform: translateX(40%); }
    }

    @keyframes hydronicus-card-enter {
      from { opacity: 0; transform: translateY(8px) scale(0.992); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes hydronicus-ambient {
      from { transform: translate3d(-2%, -1%, 0) scale(1.02); }
      to { transform: translate3d(3%, 2%, 0) scale(1.08); }
    }
    @keyframes hydronicus-spin { to { transform: rotate(360deg); } }
    @keyframes hydronicus-pulse {
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 38%, transparent); }
      58%, 100% { box-shadow: 0 0 0 0.48rem transparent; }
    }
    @keyframes hydronicus-flow {
      from { transform: translateX(-120%); }
      to { transform: translateX(230%); }
    }
    @keyframes hydronicus-hold {
      from { transform: scaleX(0); }
      to { transform: scaleX(1); }
    }
    @keyframes hydronicus-reveal {
      from { opacity: 0; transform: translateY(-3px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes hydronicus-shimmer {
      from { background-position: 100% 0; }
      to { background-position: -100% 0; }
    }
  `;

  hass?: HomeAssistantLike;
  _config?: PlantCardConfig;
  _snapshot: PlantSnapshot | null = null;
  _error: string | null = null;
  _reconnecting = false;
  _holdingShutdown = false;
  private _unsubscribe: (() => void) | null = null;
  private _holdTimer: number | null = null;
  private _subscriptionGeneration = 0;

  setConfig(config: PlantCardConfig): void {
    if (!config || config.type !== "custom:hydronicus-plant-card" || typeof config.plant !== "string" || !config.plant) {
      throw new Error("Hydronicus Plant card requires one Plant UUID.");
    }
    if (config.density && !["comfortable", "compact"].includes(config.density)) {
      throw new Error("Hydronicus Plant card density must be comfortable or compact.");
    }
    this._config = { ...config, density: config.density ?? "comfortable" };
    this._subscribe();
  }

  getCardSize(): number { return 7; }

  getGridOptions() {
    return { rows: 6, columns: 6, min_rows: 4, min_columns: 3, max_columns: 12 };
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._subscribe();
  }

  disconnectedCallback(): void {
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._subscriptionGeneration += 1;
    this._clearHold();
    super.disconnectedCallback();
  }

  protected updated(): void { this._subscribe(); }

  render() {
    const snapshot = this._snapshot;
    const config = this._config;
    if (!config) return html`<div class="card" role="status"><div class="empty-state">Configure one Hydronicus Plant.</div></div>`;
    if (this._error) return html`<div class="card" data-visual="attention" role="alert"><div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">Connection needs attention</p><h1>Hydronicus Plant</h1></div></div><p class="error">${this._error}</p><p class="meta">Check the Dashboard Resource and wait for the connection to recover.</p></div>`;
    if (!snapshot) return html`<div class="card loading-card" role="status" aria-busy="true"><div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div><div class="loading-panel"></div><p class="muted">${this._reconnecting ? "Reconnecting to Hydronicus…" : "Loading Plant snapshot…"}</p></div>`;
    return html`<article class="card ${config.density}" data-visual=${plantVisualState(snapshot)} aria-label=${snapshot.plant.name}>
      ${this._renderHeader(snapshot)}
      <div class="boundary" role="status">
        <span class="boundary-orb" aria-hidden="true"></span>
        <div class="boundary-copy"><span class="control-label">Execution boundary</span><strong>${snapshot.plant.execution_boundary.message || `${phaseLabel(snapshot.plant.execution_boundary.mode)} execution boundary is active.`}</strong></div>
      </div>
      ${this._renderAlerts(snapshot)}
      ${this._renderZones(snapshot)}
      ${this._renderPaths(snapshot)}
      ${this._renderActuators(snapshot)}
      ${this._renderExplanations(snapshot)}
      ${this._renderOperations(snapshot)}
    </article>`;
  }

  private _renderHeader(snapshot: PlantSnapshot) {
    const boundary = snapshot.plant.execution_boundary;
    return html`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h1>${snapshot.plant.name}</h1>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${phaseLabel(snapshot.plant.status)}</span>
            <span class="meta mode-detail">Requested ${phaseLabel(snapshot.plant.requested_mode)} · active ${phaseLabel(snapshot.plant.active_mode)}</span>
          </div>
          <p class="meta source-line"><strong>Source</strong> ${snapshot.plant.source.active_name ?? "none active"} · recommended ${snapshot.plant.source.recommended_name ?? "none"}</p>
          <p class="meta">${snapshot.plant.controller.mode_explanation ?? "The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${boundary.mode}" aria-label="Execution boundary">${phaseLabel(boundary.mode)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" .value=${snapshot.plant.requested_mode} @change=${this._modeChanged}>
          ${MODES.map((mode) => html`<option value=${mode}>${phaseLabel(mode)}</option>`)}
        </select></label>
        ${this._renderShutdown(snapshot)}
      </div>
    </header>`;
  }

  private _renderShutdown(snapshot: PlantSnapshot) {
    const disabled = !snapshot.controls.safe_shutdown;
    return html`<button class=${`shutdown ${this._holdingShutdown ? "is-holding" : ""}`} ?disabled=${disabled} aria-label="Hold to confirm Hydronicus Safe shutdown" aria-pressed=${this._holdingShutdown ? "true" : "false"} @pointerdown=${this._startHold} @pointerup=${this._clearHold} @pointercancel=${this._clearHold} @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd}><span class="button-label">Safe shutdown</span></button>${this._holdingShutdown ? html`<span class="hold-progress" role="status">Keep holding…</span>` : nothing}`;
  }

  private _renderAlerts(snapshot: PlantSnapshot) {
    const alerts = prioritizedAlerts(snapshot);
    if (!alerts.length) return nothing;
    return html`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-alerts">Alerts</h2></div><span class="meta">${alerts.length}</span></div>${alerts.slice(0, 3).map((alert) => html`<div class="alert ${alert.severity === "error" || alert.severity === "critical" ? "error" : ""}" data-severity=${alert.severity} role=${alert.severity === "error" || alert.severity === "critical" ? "alert" : "status"}><strong>${phaseLabel(alert.code)}</strong><span> · ${alert.message}</span></div>`)}</section>`;
  }

  private _renderZones(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-zones">Comfort Zones</h2></div><span class="meta">${snapshot.zones.length} visible</span></div><div class="zone-grid">${snapshot.zones.length ? snapshot.zones.map((zone) => this._renderZone(snapshot, zone)) : html`<p class="muted empty-state">No visible Zones are configured for this Plant.</p>`}</div></section>`;
  }

  private _renderZone(_snapshot: PlantSnapshot, zone: ZoneSnapshot) {
    const thermostat = zone.thermostat;
    const current = thermostat.current_temperature === null ? "--" : thermostat.current_temperature.toFixed(1);
    const target = thermostat.target_temperature === null ? "--" : thermostat.target_temperature.toFixed(1);
    const internal = thermostat.kind === "hydronicus";
    const hasDemand = zone.demand || zone.cooling.demand;
    return html`<article class="zone" data-phase=${zone.phase} data-demand=${String(hasDemand)} data-blocked=${String(zone.blocked)} aria-label=${`${zone.name} Zone`}>
      <div class="row"><div><h3 class="zone-title">${zone.name}</h3><p class="meta zone-owner">${internal ? "Hydronicus thermostat" : "External thermostat · read-only"}</p></div><span class="phase ${zone.blocked ? "state blocked" : ""}">${phaseLabel(zone.phase)}</span></div>
      <div class="temperature-panel">
        <div class="metric" aria-label=${`Current temperature ${thermostat.current_temperature === null ? "unavailable" : `${current} degrees Celsius`}`}><span class="metric-value">${current}</span>${thermostat.current_temperature === null ? nothing : html`<span class="metric-unit">°C</span>`}<span class="metric-label">Current</span></div>
        <div class="metric target" aria-label=${`Target temperature ${thermostat.target_temperature === null ? "unavailable" : `${target} degrees Celsius`}`}><span class="metric-value">${target}</span>${thermostat.target_temperature === null ? nothing : html`<span class="metric-unit">°C</span>`}<span class="metric-label">Target</span></div>
      </div>
      <p class="meta zone-note">${hasDemand ? `${zone.cooling.demand ? "Cooling" : "Heating"} demand active` : "No demand"} · ${thermostat.explanation}</p>
      <div class="diagnostic-list" aria-label="Zone diagnostics">
        <span class="diagnostic-chip">${zone.sensor_status.usable} sensor${zone.sensor_status.usable === 1 ? "" : "s"} ready</span>
        ${zone.sensor_status.optional_excluded ? html`<span class="diagnostic-chip warning">${zone.sensor_status.optional_excluded} optional excluded</span>` : nothing}
        ${zone.sensor_status.required_blocking ? html`<span class="diagnostic-chip danger">${zone.sensor_status.required_blocking} required blocked</span>` : nothing}
        ${zone.cooling.dew_point === null ? nothing : html`<span class="diagnostic-chip">Dew point ${zone.cooling.dew_point.toFixed(1)} °C</span>`}
        ${zone.cooling.condensation_margin === null ? nothing : html`<span class="diagnostic-chip ${zone.cooling.blocked ? "danger" : ""}">Margin ${zone.cooling.condensation_margin.toFixed(1)} °C</span>`}
      </div>
      ${thermostat.preset ? html`<p class="meta zone-note">Preset: ${phaseLabel(thermostat.preset)}</p>` : nothing}
      ${zone.blocked_reason ? html`<p class="meta zone-note" role="status">${zone.blocked_reason}</p>` : nothing}
      ${zone.coupling_group_ids.length ? html`<p class="meta coupling-note">Coupled delivery - this Zone shares hydraulic equipment.</p>` : nothing}
      ${internal ? html`<div class="zone-actions"><button ?disabled=${!thermostat.control_entity_id || thermostat.target_temperature === null} aria-label=${`Decrease ${zone.name} target by half a degree`} @click=${() => this._adjustZone(zone, -0.5)}>−0.5</button><button ?disabled=${!thermostat.control_entity_id || thermostat.target_temperature === null} aria-label=${`Increase ${zone.name} target by half a degree`} @click=${() => this._adjustZone(zone, 0.5)}>+0.5</button><select class="preset" aria-label=${`${zone.name} preset`} .value=${thermostat.preset ?? "none"} ?disabled=${!thermostat.control_entity_id} @change=${(event: Event) => this._presetChanged(zone, event)}>${["none", ...thermostat.preset_modes].map((preset) => html`<option value=${preset}>${phaseLabel(preset)}</option>`)}</select></div>` : html`<p class="meta" role="note">Adjust this thermostat in its owning Home Assistant integration.</p>`}
    </article>`;
  }

  private _renderPaths(snapshot: PlantSnapshot) {
    if (!snapshot.delivery_paths.length) return nothing;
    return html`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-paths">Hydraulic Flow</h2></div><span class="meta">Zone → Circuit → Valve → Pump → Source</span></div><div class="path-list">${snapshot.delivery_paths.map((path) => html`<article class="path" data-status=${path.status} data-flowing=${String(isFlowingState(path.status))}><div class="path-head"><div class="path-heading"><strong>${snapshot.zones.find((zone) => zone.id === path.zone_id)?.name ?? path.zone_id}</strong></div><div class="status-line"><span class="state ${path.status}">${phaseLabel(path.status)}</span>${path.coupled ? html`<span class="meta">coupled</span>` : nothing}</div></div><div class="path-track" aria-label="Ordered hydraulic delivery path">${path.nodes.map((node, index) => html`${index ? html`<span class="flow-link" aria-hidden="true"></span>` : nothing}<span class="node" data-kind=${node.kind} data-state=${node.state} data-flowing=${String(isFlowingState(node.state))} title=${`${node.name}: ${phaseLabel(node.state)}`}><span class="node-kind">${phaseLabel(node.kind)}</span><span class="node-name">${node.name}</span><span class="node-state">${phaseLabel(node.state)}</span></span>`)}</div>${path.problem ? html`<p class="meta path-problem" role="alert">${path.problem}</p>` : nothing}</article>`)}</div></section>`;
  }

  private _renderActuators(snapshot: PlantSnapshot) {
    if (!snapshot.actuators.length) return nothing;
    return html`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-actuators">Actuator Ownership</h2></div><span class="meta">Shared consumers stay visible</span></div><div class="actuator-list">${snapshot.actuators.map((actuator) => html`<article class="actuator" data-state=${actuator.state}><div class="row"><strong>${actuator.name}</strong><span class="state actuator-state ${actuator.state}">${phaseLabel(actuator.state)}</span></div><p class="meta">${phaseLabel(actuator.kind)} · ${actuator.reason ?? "No additional explanation."}</p>${actuator.active_consumers.length ? html`<div class="consumer-list" aria-label="Active circuit consumers">${actuator.active_consumers.map((consumer) => html`<span class="consumer-chip"><strong>${consumer.name}</strong> · ${consumer.id}</span>`)}</div>` : html`<p class="meta zone-note">No active circuit consumers.</p>`}</article>`)}</div></section>`;
  }

  private _renderExplanations(snapshot: PlantSnapshot) {
    return html`<section aria-labelledby="hydronicus-explanations"><details><summary id="hydronicus-explanations">Controller explanations</summary>${snapshot.explanations.map((step) => html`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${phaseLabel(step.scope)}</strong> · ${step.message}</p></div>`)}</details></section>`;
  }

  private _renderOperations(snapshot: PlantSnapshot) {
    const operations = Object.values(snapshot.execution.operations).flat();
    if (!operations.length) return nothing;
    return html`<section aria-labelledby="hydronicus-operations"><details open><summary id="hydronicus-operations">Latest operation outcomes (${operations.length})</summary>${operations.map((operation) => { const result = String(operation.result ?? "unknown"); return html`<div class="operation" data-result=${result}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${operationLabel(operation)}</strong><br><span class="meta">${String(operation.reason ?? operation.explanation ?? "")}</span></p></div>`; })}</details></section>`;
  }

  private _subscribe(): void {
    if (!this._config || !this.hass || this._unsubscribe) return;
    const generation = ++this._subscriptionGeneration;
    this._reconnecting = false;
    this._error = null;
    this.hass.connection.subscribeMessage(
      (message) => {
        if (generation !== this._subscriptionGeneration) return;
        const candidate = message.snapshot;
        if (!candidate) return;
        try {
          this._snapshot = parseSnapshot(candidate);
          this._error = null;
          this._reconnecting = false;
        } catch (error) {
          this._snapshot = null;
          this._error = error instanceof Error ? error.message : "Unsupported Hydronicus snapshot.";
        }
      },
      { type: "hydronicus/subscribe_plant", plant_id: this._config.plant },
    ).then((unsubscribe) => {
      if (generation !== this._subscriptionGeneration) {
        unsubscribe();
        return;
      }
      this._unsubscribe = unsubscribe;
    }).catch((error: unknown) => {
      if (generation !== this._subscriptionGeneration) return;
      this._reconnecting = true;
      this._error = error instanceof Error ? error.message : "Hydronicus connection failed.";
    });
  }

  private _call(action: { domain: string; service: string; data: Record<string, unknown> } | null): void {
    if (!action || !this.hass) return;
    void this.hass.callService(action.domain, action.service, action.data).catch((error: unknown) => {
      this._error = error instanceof Error ? error.message : "Home Assistant action failed.";
    });
  }

  private _modeChanged = (event: Event): void => {
    if (!this._snapshot) return;
    this._call(actionForMode(this._snapshot, (event.target as HTMLSelectElement).value));
  };

  private _adjustZone(zone: ZoneSnapshot, delta: number): void {
    const target = adjustTarget(zone, delta);
    if (target !== null) this._call(actionForTarget(zone, target));
  }

  private _presetChanged(zone: ZoneSnapshot, event: Event): void {
    this._call(actionForPreset(zone, (event.target as HTMLSelectElement).value));
  }

  private _startHold = (): void => {
    if (!this._snapshot || this._holdTimer !== null) return;
    this._holdingShutdown = true;
    this._holdTimer = window.setTimeout(() => {
      if (!this._snapshot) return;
      this._call(actionForSafeShutdown(this._snapshot));
      this._holdingShutdown = false;
      this._holdTimer = null;
    }, 1200);
  };

  private _clearHold = (): void => {
    if (this._holdTimer !== null) window.clearTimeout(this._holdTimer);
    this._holdTimer = null;
    this._holdingShutdown = false;
  };

  private _keyHoldStart = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      this._startHold();
    }
  };

  private _keyHoldEnd = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") this._clearHold();
  };

  static getConfigElement(): HTMLElement { return document.createElement("hydronicus-plant-card-editor"); }

  static getStubConfig(): Omit<PlantCardConfig, "type"> { return { plant: "", density: "comfortable" }; }
}

class HydronicusPlantCardEditor extends LitElement {
  static properties = { hass: { attribute: false }, _config: { state: true }, _plants: { state: true }, _error: { state: true } };
  static styles = css`
    :host { display: block; padding: 1rem; }
    label { display: grid; gap: 0.35rem; margin-bottom: 0.8rem; }
    select { box-sizing: border-box; min-height: 2.4rem; padding: 0.4rem; font: inherit; color: inherit; background: var(--card-background-color, transparent); border: 1px solid var(--divider-color); border-radius: 0.45rem; }
    select:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }
  `;
  hass?: HomeAssistantLike;
  _config: PlantCardConfig = { type: "custom:hydronicus-plant-card", plant: "", density: "comfortable" };
  _plants: PlantSummary[] = [];
  _error: string | null = null;
  private _loaded = false;

  setConfig(config: PlantCardConfig): void {
    this._config = { ...this._config, ...config };
    this._loadPlants();
  }

  protected updated(): void { this._loadPlants(); }

  render() {
    return html`<label>Hydronicus Plant<select aria-label="Hydronicus Plant" .value=${this._config.plant} @change=${this._plantChanged}><option value="">Select a Plant…</option>${this._plants.map((plant) => html`<option value=${plant.id}>${plant.name}</option>`)}</select></label><label>Density<select aria-label="Card density" .value=${this._config.density ?? "comfortable"} @change=${this._densityChanged}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>${this._error ? html`<p role="alert">${this._error}</p>` : nothing}`;
  }

  private _loadPlants(): void {
    if (!this.hass || this._loaded) return;
    this._loaded = true;
    this.hass.connection.sendMessagePromise<{ plants?: PlantSummary[] }>({ type: "hydronicus/list_plants" }).then((message) => {
      this._plants = message.plants ?? [];
    }).catch((error: unknown) => {
      this._error = error instanceof Error ? error.message : "Could not list Hydronicus Plants.";
    });
  }

  private _configChanged(): void {
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }

  private _plantChanged = (event: Event): void => {
    this._config = { ...this._config, plant: (event.target as HTMLSelectElement).value };
    this._configChanged();
  };

  private _densityChanged = (event: Event): void => {
    this._config = { ...this._config, density: (event.target as HTMLSelectElement).value as "comfortable" | "compact" };
    this._configChanged();
  };
}

customElements.define("hydronicus-plant-card", HydronicusPlantCard);
customElements.define("hydronicus-plant-card-editor", HydronicusPlantCardEditor);

declare global {
  interface Window { customCards?: Array<Record<string, unknown>>; }
}

window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "hydronicus-plant-card",
  name: "Hydronicus Plant",
  version: HYDRONICUS_FRONTEND_VERSION,
  description: "Topology-driven Hydronicus Plant status and controls.",
  preview: false,
  documentationURL: "https://github.com/brumi1024/ha-hydronicus",
});
