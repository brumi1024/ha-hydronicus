import { css } from "lit";

/**
 * Card styles. They use Home Assistant theme tokens with fallbacks, and only
 * logical properties for inline direction, so right-to-left layouts mirror.
 */
export const cardStyles = css`
  :host {
    display: block;
    --hydronicus-border: var(--divider-color, color-mix(in srgb, var(--primary-text-color, #1c1c1c) 13%, transparent));
    --hydronicus-muted: var(--secondary-text-color, #5f6368);
    --hydronicus-surface: var(--ha-card-background, var(--card-background-color, #fff));
    --hydronicus-raised: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 4%, transparent);
    --hydronicus-danger: var(--error-color, #db4437);
    --hydronicus-warning: var(--warning-color, #ffa600);
    --hydronicus-success: var(--success-color, #43a047);
    --hydronicus-accent: var(--primary-color, #03a9f4);
    --hydronicus-heating-color: var(--state-climate-heat-color, #ff8100);
    --hydronicus-cooling-color: var(--state-climate-cool-color, #2b9af9);
    --hydronicus-idle-color: var(--primary-color, #03a9f4);
    --hydronicus-attention-color: var(--error-color, #db4437);
    --hydronicus-glass-blur: 0px;
    --hydronicus-glass-opacity: 100%;
    --hydronicus-flow-duration: 2.2s;
    --hydronicus-ambient-duration: 16s;
    --hydronicus-state-color: var(--hydronicus-idle-color);
    --hydronicus-inline-start: left;
    --hydronicus-radius: var(--ha-border-radius-lg, 12px);
    font-variant-numeric: tabular-nums;
  }

  :host(:dir(rtl)) {
    --hydronicus-inline-start: right;
  }

  ha-card {
    display: block;
    box-sizing: border-box;
    container-type: inline-size;
    overflow: hidden;
    position: relative;
    isolation: isolate;
    height: 100%;
    color: var(--primary-text-color, #1c1c1c);
    background: color-mix(in srgb, var(--hydronicus-surface) var(--hydronicus-glass-opacity), transparent);
    -webkit-backdrop-filter: blur(var(--hydronicus-glass-blur));
    backdrop-filter: blur(var(--hydronicus-glass-blur));
    padding: var(--ha-space-4, 16px);
    animation: hydronicus-card-enter 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }

  ha-card::before {
    content: "";
    position: absolute;
    z-index: -1;
    inset: -35%;
    pointer-events: none;
    background:
      radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--hydronicus-state-color) 16%, transparent) 0, transparent 32%),
      radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--hydronicus-accent) 9%, transparent) 0, transparent 30%);
    opacity: 0.8;
    transform: translate3d(-2%, -1%, 0) scale(1.02);
    animation: hydronicus-ambient var(--hydronicus-ambient-duration) ease-in-out infinite alternate;
  }

  ha-card[data-visual="heating"] { --hydronicus-state-color: var(--hydronicus-heating-color); }
  ha-card[data-visual="cooling"] { --hydronicus-state-color: var(--hydronicus-cooling-color); }
  ha-card[data-visual="attention"] { --hydronicus-state-color: var(--hydronicus-attention-color); }
  ha-card.compact { padding: var(--ha-space-3, 12px); }

  .visually-hidden {
    position: absolute;
    inline-size: 1px;
    block-size: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .header, .row, .path-head, .section-head, .plant-heading, .status-line, .boundary-copy { display: flex; align-items: center; gap: 0.65rem; }
  .header { justify-content: space-between; align-items: flex-start; gap: 1.2rem; }
  .header-copy { min-inline-size: 0; }
  h2, h3, h4, p, ul, ol { margin: 0; }
  ul, ol { padding: 0; list-style: none; }
  h2 { font-size: var(--ha-font-size-xl, 1.25rem); font-weight: var(--ha-font-weight-medium, 500); line-height: 1.3; overflow-wrap: anywhere; }
  h3 { font-size: var(--ha-font-size-m, 0.95rem); font-weight: var(--ha-font-weight-medium, 500); }
  h4 { font-size: var(--ha-font-size-m, 0.9rem); font-weight: var(--ha-font-weight-medium, 500); }
  .muted, .meta { color: var(--hydronicus-muted); font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.45; }
  .eyebrow { margin-block-end: 0.12rem; color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
  .plant-heading { align-items: flex-start; }
  .plant-mark {
    position: relative;
    flex: 0 0 2.7rem;
    inline-size: 2.7rem;
    block-size: 2.7rem;
    border-radius: var(--hydronicus-radius);
    background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
  }
  .plant-mark::before {
    content: "";
    position: absolute;
    inset: 0.58rem;
    border: 2px solid color-mix(in srgb, var(--hydronicus-state-color) 30%, transparent);
    border-block-start-color: var(--hydronicus-state-color);
    border-radius: 50%;
    animation: hydronicus-spin 3.8s linear infinite;
  }
  .plant-mark::after {
    content: "";
    position: absolute;
    inset: 0;
    margin: auto;
    inline-size: 0.42rem;
    block-size: 0.42rem;
    border-radius: 50%;
    background: var(--hydronicus-state-color);
  }
  button.link {
    min-block-size: 0;
    border: 0;
    border-radius: 0.3rem;
    background: none;
    padding: 0;
    color: inherit;
    font: inherit;
    text-align: start;
    text-decoration: underline dotted color-mix(in srgb, currentColor 40%, transparent);
    text-underline-offset: 0.2em;
  }
  button.link:hover { background: none; text-decoration-color: currentColor; }
  .status-line { flex-wrap: wrap; margin-block-start: 0.48rem; gap: 0.35rem; }
  .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 600; }
  .status-dot { inline-size: 0.45rem; block-size: 0.45rem; border-radius: 50%; background: var(--hydronicus-state-color); animation: hydronicus-pulse 2.8s ease-out infinite; }
  .mode-detail { border-inline-start: 1px solid var(--hydronicus-border); padding-inline-start: 0.55rem; }
  .source-line { margin-block-start: 0.35rem; }
  .source-line strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
  .badge, .phase, .state { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.72rem; line-height: 1.2; white-space: nowrap; }
  .badge { font-weight: 700; letter-spacing: 0.02em; background: color-mix(in srgb, var(--hydronicus-warning) 12%, transparent); }
  .badge.dry-run, .state.proposed { color: var(--hydronicus-warning); }
  .badge.mixed, .badge.live, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
  .badge.mixed, .badge.live { background: color-mix(in srgb, var(--hydronicus-danger) 10%, transparent); }
  .phase.off { color: var(--hydronicus-muted); }
  .badge.active, .state.active, .state.ready { color: var(--hydronicus-success); }
  .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
  .mode-control { display: flex; align-items: center; min-block-size: 2.5rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); padding-inline-start: 0.62rem; }
  .control-label { color: var(--hydronicus-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  button, select { min-block-size: 2.5rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); color: inherit; font: inherit; padding: 0.38rem 0.7rem; transition: border-color 180ms ease, background-color 180ms ease, transform 120ms ease; }
  .mode-control select { border: 0; background: transparent; min-block-size: 2.4rem; }
  button { cursor: pointer; }
  button:hover, select:hover { border-color: color-mix(in srgb, var(--hydronicus-state-color) 46%, var(--hydronicus-border)); background: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 8%, transparent); }
  button:active { transform: translateY(1px); }
  button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
  button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--hydronicus-accent); outline-offset: 2px; }
  .shutdown { position: relative; overflow: hidden; color: var(--hydronicus-danger); touch-action: none; user-select: none; -webkit-user-select: none; }
  .shutdown.quiet { color: var(--hydronicus-muted); }
  .shutdown.quiet:hover, .shutdown.quiet:focus-visible, .shutdown.quiet.is-holding { color: var(--hydronicus-danger); }
  .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--hydronicus-danger) 18%, transparent); transform: scaleX(0); transform-origin: var(--hydronicus-inline-start); }
  .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
  .button-label { position: relative; z-index: 1; }
  .hold-progress { flex-basis: 100%; text-align: end; font-size: 0.7rem; color: var(--hydronicus-danger); }
  .alert, .error, .boundary, .notice { margin-block-start: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); padding: 0.68rem 0.75rem; }
  .alert, .notice, .action-error { position: relative; overflow: hidden; padding-inline-start: 0.9rem; }
  .alert::before, .notice::before, .action-error::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--hydronicus-warning); }
  .alert.error::before, .action-error::before { background: var(--hydronicus-danger); }
  .action-error { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-block-start: 0.9rem; border: 1px solid color-mix(in srgb, var(--hydronicus-danger) 40%, var(--hydronicus-border)); border-radius: var(--hydronicus-radius); padding-block: 0.4rem; padding-inline-end: 0.4rem; color: var(--hydronicus-danger); font-size: 0.85rem; }
  .action-error button { min-block-size: 2.2rem; color: inherit; }
  .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
  .boundary-orb { display: grid; place-items: center; inline-size: 1.75rem; block-size: 1.75rem; border-radius: 0.65rem; background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent); color: var(--hydronicus-state-color); }
  .boundary-orb::before { content: ""; inline-size: 0.55rem; block-size: 0.55rem; border: 2px solid currentColor; border-radius: 50%; }
  .boundary-copy { min-inline-size: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
  .boundary-copy strong { font-size: 0.82rem; font-weight: 600; }
  section { margin-block-start: 1.05rem; }
  .section-head { justify-content: space-between; margin-block-end: 0.5rem; }
  .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
  .section-kicker::before { content: ""; inline-size: 0.38rem; block-size: 0.38rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-state-color) 80%, transparent); }
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
  .zone, .path, .actuator, details { border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); }
  .zone, .path, .actuator { padding: 0.72rem; }
  .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
  .zone::before { content: ""; position: absolute; inset-block-start: 0; inset-inline: 0; block-size: 2px; background: var(--hydronicus-state-color); opacity: 0.18; transform: scaleX(0.35); transform-origin: var(--hydronicus-inline-start); transition: opacity 220ms ease, transform 380ms ease; }
  .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
  .zone[data-demand="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 30%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 7%, transparent); }
  .zone[data-demand-kind="heating"] { --hydronicus-state-color: var(--hydronicus-heating-color); }
  .zone[data-demand-kind="cooling"] { --hydronicus-state-color: var(--hydronicus-cooling-color); }
  .zone[data-hvac-mode="off"] .metric.target { background: transparent; }
  .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 34%, var(--hydronicus-border)); }
  .row { justify-content: space-between; align-items: baseline; }
  .zone-title { min-inline-size: 0; overflow-wrap: anywhere; }
  .zone-owner { margin-block-start: 0.12rem; }
  .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin-block: 0.65rem 0.5rem; }
  .metric { min-inline-size: 0; border: 1px solid color-mix(in srgb, var(--hydronicus-border) 72%, transparent); border-radius: var(--hydronicus-radius); padding: 0.52rem 0.58rem; }
  .metric.target { background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
  .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 600; letter-spacing: -0.02em; }
  .metric-unit { margin-inline-start: 0.15rem; color: var(--hydronicus-muted); font-size: 0.75rem; }
  .metric-label { display: block; margin-block-start: 0.06rem; color: var(--hydronicus-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .zone-note { margin-block-start: 0.28rem; }
  .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.45rem; }
  .diagnostic-chip { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--hydronicus-muted); font-size: 0.7rem; }
  .diagnostic-chip.warning { color: var(--hydronicus-warning); border-color: color-mix(in srgb, var(--hydronicus-warning) 30%, var(--hydronicus-border)); }
  .diagnostic-chip.danger { color: var(--hydronicus-danger); border-color: color-mix(in srgb, var(--hydronicus-danger) 30%, var(--hydronicus-border)); }
  .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-block-start: 0.38rem; color: color-mix(in srgb, var(--hydronicus-warning) 80%, var(--hydronicus-muted)); }
  .hvac-modes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-block-start: 0.62rem; padding: 0.2rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); }
  .hvac-mode { flex: 1 1 auto; min-block-size: 2.2rem; padding-inline: 0.4rem; border-color: transparent; background: transparent; font-size: 0.8rem; white-space: nowrap; }
  .hvac-mode[aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-accent) 50%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-accent) 14%, transparent); font-weight: 600; }
  .hvac-mode[data-mode="heat"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-heating-color) 55%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-heating-color) 16%, transparent); }
  .hvac-mode[data-mode="cool"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-cooling-color) 55%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-cooling-color) 16%, transparent); }
  .hvac-mode[data-mode="off"][aria-pressed="true"] { border-color: var(--hydronicus-border); background: var(--hydronicus-raised); }
  .zone-actions { display: flex; gap: 0.35rem; margin-block-start: 0.45rem; }
  .zone-actions button { min-inline-size: 2.75rem; }
  .preset { flex: 1; min-inline-size: 0; }
  .path-list, .actuator-list { display: grid; gap: 0.55rem; }
  .path { overflow: hidden; }
  .path-head { justify-content: space-between; flex-wrap: wrap; }
  .path-heading { display: flex; align-items: center; gap: 0.42rem; min-inline-size: 0; }
  .path-heading::before { content: ""; flex: 0 0 auto; inline-size: 0.43rem; block-size: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-muted) 55%, transparent); }
  .path[data-flowing="true"] .path-heading::before { background: var(--hydronicus-state-color); animation: hydronicus-pulse 2.4s ease-out infinite; }
  .path[data-status="blocked"] .path-heading::before { background: var(--hydronicus-danger); }
  .path-track { display: flex; align-items: stretch; margin-block-start: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding-block: 0.08rem 0.25rem; padding-inline: 0.03rem; scroll-snap-type: inline proximity; scrollbar-width: thin; }
  .path-step { display: contents; }
  .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-inline-size: 0; border: 1px solid var(--hydronicus-border); border-radius: calc(var(--hydronicus-radius) * 0.75); padding: 0.48rem 0.52rem; font-size: 0.76rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, background-color 220ms ease; }
  .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 34%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
  .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 36%, var(--hydronicus-border)); }
  .node-kind { color: var(--hydronicus-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .node-name { margin-block-start: 0.18rem; font-weight: 600; line-height: 1.25; }
  .node-state { display: flex; align-items: center; gap: 0.28rem; margin-block-start: 0.3rem; color: var(--hydronicus-muted); font-size: 0.68rem; }
  .node-state::before { content: ""; inline-size: 0.3rem; block-size: 0.3rem; border-radius: 50%; background: currentColor; }
  .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); }
  .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-inline-size: 1.2rem; align-self: center; block-size: 2px; margin-inline: 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--hydronicus-muted) 24%, transparent); }
  :host(:dir(rtl)) .flow-link { transform: scaleX(-1); }
  .flow-link::before { content: ""; position: absolute; inset-inline-end: 0; inset-block-start: 50%; inline-size: 0.34rem; block-size: 0.34rem; border-block-start: 1px solid var(--hydronicus-muted); border-inline-end: 1px solid var(--hydronicus-muted); transform: translateY(-50%) rotate(45deg); }
  .flow-link::after { content: ""; position: absolute; inset-block: -1px; inset-inline-start: 0; inline-size: 58%; background: linear-gradient(90deg, transparent, var(--hydronicus-state-color), transparent); opacity: 0; transform: translateX(-120%); }
  .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent); }
  .path[data-flowing="true"] .flow-link::before { border-color: var(--hydronicus-state-color); }
  .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--hydronicus-flow-duration) linear infinite; }
  .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--hydronicus-danger) 30%, transparent); }
  .path-problem { margin-block-start: 0.5rem; color: var(--hydronicus-danger); }
  .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
  .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
  .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.48rem; }
  .consumer-chip { max-inline-size: 100%; border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--hydronicus-muted); font-size: 0.7rem; overflow-wrap: anywhere; }
  .consumer-chip strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
  details { overflow: hidden; padding: 0.62rem 0.72rem; }
  details + details { margin-block-start: 0.45rem; }
  summary { cursor: pointer; font-size: 0.85rem; font-weight: 600; }
  details[open] summary { margin-block-end: 0.25rem; }
  details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
  .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding-block: 0.48rem; border-block-start: 1px solid var(--hydronicus-border); font-size: 0.82rem; }
  .operation:first-of-type { border-block-start: 0; }
  .operation-marker { inline-size: 0.4rem; block-size: 0.4rem; margin-block-start: 0.35rem; border-radius: 50%; background: var(--hydronicus-muted); }
  .operation[data-result="proposed"] .operation-marker { background: var(--hydronicus-warning); }
  .operation[data-result="executed"] .operation-marker { background: var(--hydronicus-success); }
  .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--hydronicus-danger); }
  .operation-copy { min-inline-size: 0; }
  .empty-state { padding: 0.8rem; border: 1px dashed var(--hydronicus-border); border-radius: var(--hydronicus-radius); text-align: center; }
  /* A Room card is the Room tile itself: the card frame replaces the tile's. */
  ha-card.room-card { padding: 0; }
  ha-card.room-card > .zone { border-color: transparent; border-radius: inherit; }
  ha-card.room-card.compact > .zone { padding: 0.55rem; }
  ha-card.room-card > .notice, ha-card.room-card > .action-error { margin-block-start: 0.72rem; margin-inline: 0.72rem; }
  h2.zone-title { font-size: var(--ha-font-size-m, 0.9rem); }
  .state-card { display: grid; gap: 0.6rem; }
  .loading-card { min-block-size: 12rem; }
  .loading-head { display: flex; align-items: center; gap: 0.65rem; }
  .loading-mark, .skeleton { background: linear-gradient(105deg, var(--hydronicus-raised) 20%, color-mix(in srgb, var(--primary-text-color, #1c1c1c) 10%, transparent) 38%, var(--hydronicus-raised) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
  .loading-mark { inline-size: 2.7rem; block-size: 2.7rem; border-radius: var(--hydronicus-radius); }
  .skeleton { inline-size: min(16rem, 62cqi); block-size: 0.72rem; border-radius: 999px; }
  .skeleton.short { inline-size: min(10rem, 42cqi); margin-block-start: 0.45rem; }
  .loading-panel { block-size: 4.2rem; margin-block-start: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); }
  @container (max-width: 680px) {
    .header { display: block; }
    .controls { justify-content: flex-start; margin-block-start: 0.7rem; }
    .hold-progress { text-align: start; }
  }
  @container (max-width: 440px) {
    .zone-grid { grid-template-columns: 1fr; }
    .mode-detail { flex-basis: 100%; border-inline-start: 0; padding-inline-start: 0; }
    .boundary-copy { display: block; }
    .boundary-copy .control-label { display: block; margin-block-end: 0.12rem; }
    .section-head { align-items: flex-start; }
    .section-head > .meta { text-align: end; }
  }
  @media (prefers-reduced-motion: reduce) {
    ha-card, ha-card::before, .plant-mark::before, .status-dot, .path-heading::before, .path[data-flowing="true"] .flow-link::after, details[open] .operation, .loading-mark, .skeleton { animation: none !important; }
    button, select, .zone, .node { transition-duration: 0.01ms !important; }
    .path[data-flowing="true"] .flow-link::after { opacity: 0.65; transform: translateX(40%); }
    .shutdown.is-holding::after { animation: none; transform: scaleX(1); }
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
