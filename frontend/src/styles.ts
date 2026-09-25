import { css } from "lit";

/**
 * Card styles. They use Home Assistant theme tokens with fallbacks, and only
 * logical properties for inline direction, so right-to-left layouts mirror.
 *
 * Theming: a public `--hydronicus-*` token is only ever read, never
 * declared, so a value a theme sets on `html` or on a view element reaches
 * the card. `:host` resolves each public token once into a private
 * `--_hy-*` property, with a Home Assistant token and a literal as
 * fallbacks, and every rule reads the private property. The defaults
 * render a stock Home Assistant card.
 */
export const cardStyles = css`
  :host {
    display: block;
    --_hy-text: var(--hydronicus-text, var(--primary-text-color, #1c1c1c));
    --_hy-text-muted: var(--hydronicus-text-muted, var(--secondary-text-color, #5f6368));
    --_hy-surface: var(--hydronicus-surface, var(--ha-card-background, var(--card-background-color, #fff)));
    --_hy-surface-raised: var(--hydronicus-surface-raised, color-mix(in srgb, var(--_hy-text) 4%, transparent));
    --_hy-line: var(--hydronicus-line, var(--divider-color, color-mix(in srgb, var(--_hy-text) 13%, transparent)));
    --_hy-accent: var(--hydronicus-accent, var(--primary-color, #03a9f4));
    --_hy-heating: var(--hydronicus-heating-color, var(--state-climate-heat-color, #ff8100));
    --_hy-cooling: var(--hydronicus-cooling-color, var(--state-climate-cool-color, #2b9af9));
    --_hy-idle: var(--hydronicus-idle-color, var(--primary-color, #03a9f4));
    --_hy-attention: var(--hydronicus-attention-color, var(--error-color, #db4437));
    --_hy-success: var(--hydronicus-success-color, var(--success-color, #43a047));
    --_hy-warning: var(--hydronicus-warning-color, var(--warning-color, #ffa600));
    --_hy-danger: var(--hydronicus-danger-color, var(--error-color, #db4437));
    --_hy-radius: var(--hydronicus-radius, var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px)));
    --_hy-radius-inner: var(--hydronicus-radius-inner, var(--ha-border-radius-md, 8px));
    --_hy-radius-control: var(--hydronicus-radius-control, var(--_hy-radius-inner));
    --_hy-card-border: var(--hydronicus-card-border, var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)));
    --_hy-card-shadow: var(--hydronicus-card-shadow, var(--ha-card-box-shadow, none));
    --_hy-tile-border: var(--hydronicus-tile-border, 1px solid var(--_hy-line));
    --_hy-tile-shadow: var(--hydronicus-tile-shadow, none);
    --_hy-tile-active-shadow: var(--hydronicus-tile-active-shadow, var(--_hy-tile-shadow));
    --_hy-control-border: var(--hydronicus-control-border, 1px solid var(--_hy-line));
    --_hy-control-shadow: var(--hydronicus-control-shadow, none);
    --_hy-control-surface: var(--hydronicus-control-surface, var(--_hy-surface-raised));
    --_hy-control-color: var(--hydronicus-control-color, var(--_hy-text));
    --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-accent) 14%, transparent));
    --_hy-selected-color: var(--hydronicus-selected-color, var(--_hy-text));
    --_hy-font-body: var(--hydronicus-font-body, var(--ha-font-family-body, inherit));
    --_hy-font-display: var(--hydronicus-font-display, var(--_hy-font-body));
    --_hy-font-weight-display: var(--hydronicus-font-weight-display, var(--ha-font-weight-medium, 500));
    --_hy-ambient-opacity: var(--hydronicus-ambient-opacity, 0);
    --_hy-glass-blur: var(--hydronicus-glass-blur, 0px);
    --_hy-glass-opacity: var(--hydronicus-glass-opacity, 100%);
    --_hy-flow-duration: var(--hydronicus-flow-duration, 2.2s);
    --_hy-ambient-duration: var(--hydronicus-ambient-duration, 16s);
    /* Internal: the colour of the current state, and the inline-start side. */
    --_hy-state: var(--_hy-idle);
    --_hy-inline-start: left;
    font-variant-numeric: tabular-nums;
  }

  :host(:dir(rtl)) {
    --_hy-inline-start: right;
  }

  ha-card {
    display: block;
    box-sizing: border-box;
    container-type: inline-size;
    overflow: hidden;
    position: relative;
    isolation: isolate;
    height: 100%;
    border: var(--_hy-card-border);
    border-radius: var(--_hy-radius);
    box-shadow: var(--_hy-card-shadow);
    color: var(--_hy-text);
    font-family: var(--_hy-font-body);
    background: color-mix(in srgb, var(--_hy-surface) var(--_hy-glass-opacity), transparent);
    /* The glass blur adds to a backdrop filter the theme gives every card. */
    -webkit-backdrop-filter: blur(var(--_hy-glass-blur)) var(--ha-card-backdrop-filter,);
    backdrop-filter: blur(var(--_hy-glass-blur)) var(--ha-card-backdrop-filter,);
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
      radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--_hy-state) 16%, transparent) 0, transparent 32%),
      radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--_hy-accent) 9%, transparent) 0, transparent 30%);
    /* The ambient glow is decorative and off unless a theme turns it on. */
    opacity: var(--_hy-ambient-opacity);
    transform: translate3d(-2%, -1%, 0) scale(1.02);
    animation: hydronicus-ambient var(--_hy-ambient-duration) ease-in-out infinite alternate;
  }

  ha-card[data-visual="heating"] { --_hy-state: var(--_hy-heating); }
  ha-card[data-visual="cooling"] { --_hy-state: var(--_hy-cooling); }
  ha-card[data-visual="attention"] { --_hy-state: var(--_hy-attention); }
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
  h2, h3, h4, summary { font-family: var(--_hy-font-display); font-weight: var(--_hy-font-weight-display); }
  h2 { font-size: var(--ha-font-size-xl, 1.25rem); line-height: 1.3; overflow-wrap: anywhere; }
  h3 { font-size: var(--ha-font-size-m, 0.95rem); }
  h4 { font-size: var(--ha-font-size-m, 0.9rem); }
  .muted, .meta { color: var(--_hy-text-muted); font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.45; }
  .eyebrow { margin-block-end: 0.12rem; color: color-mix(in srgb, var(--_hy-state) 78%, var(--_hy-text)); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
  .plant-heading { align-items: flex-start; }
  .plant-mark {
    position: relative;
    flex: 0 0 2.7rem;
    inline-size: 2.7rem;
    block-size: 2.7rem;
    border-radius: var(--_hy-radius-inner);
    background: color-mix(in srgb, var(--_hy-state) 14%, transparent);
  }
  .plant-mark::before {
    content: "";
    position: absolute;
    inset: 0.58rem;
    border: 2px solid color-mix(in srgb, var(--_hy-state) 30%, transparent);
    border-block-start-color: var(--_hy-state);
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
    background: var(--_hy-state);
  }
  button.link {
    min-block-size: 0;
    border: 0;
    border-radius: 0.3rem;
    background: none;
    box-shadow: none;
    padding: 0;
    color: inherit;
    font: inherit;
    text-align: start;
    text-decoration: underline dotted color-mix(in srgb, currentColor 40%, transparent);
    text-underline-offset: 0.2em;
  }
  button.link:hover { background: none; text-decoration-color: var(--_hy-accent); }
  .status-line { flex-wrap: wrap; margin-block-start: 0.48rem; gap: 0.35rem; }
  .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 600; }
  .status-dot { inline-size: 0.45rem; block-size: 0.45rem; border-radius: 50%; background: var(--_hy-state); animation: hydronicus-pulse 2.8s ease-out infinite; }
  .mode-detail { border-inline-start: 1px solid var(--_hy-line); padding-inline-start: 0.55rem; }
  .source-line { margin-block-start: 0.35rem; }
  .source-line strong { color: var(--_hy-text); font-weight: 600; }
  .badge, .phase, .state { border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.72rem; line-height: 1.2; white-space: nowrap; }
  .badge { font-weight: 700; letter-spacing: 0.02em; background: color-mix(in srgb, var(--_hy-warning) 12%, transparent); }
  .badge.dry-run, .state.proposed { color: var(--_hy-warning); }
  .badge.mixed, .badge.live, .state.blocked, .state.mismatch { color: var(--_hy-danger); }
  .badge.mixed, .badge.live { background: color-mix(in srgb, var(--_hy-danger) 10%, transparent); }
  .phase.off { color: var(--_hy-text-muted); }
  .badge.active, .state.active, .state.ready { color: var(--_hy-success); }
  .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
  .mode-control { display: flex; align-items: center; min-block-size: 2.5rem; box-sizing: border-box; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); color: var(--_hy-control-color); padding-inline-start: 0.62rem; }
  .control-label { color: var(--_hy-text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  button, select { min-block-size: 2.5rem; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); color: var(--_hy-control-color); font: inherit; padding: 0.38rem 0.7rem; transition: border-color 180ms ease, background-color 180ms ease, transform 120ms ease; }
  .mode-control select { border: 0; background: transparent; box-shadow: none; min-block-size: 2.4rem; }
  button { cursor: pointer; }
  button:hover, select:hover { border-color: color-mix(in srgb, var(--_hy-state) 46%, var(--_hy-line)); background: color-mix(in srgb, var(--_hy-text) 8%, transparent); }
  button:active { transform: translateY(1px); }
  button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
  button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--_hy-accent); outline-offset: 2px; }
  .shutdown { position: relative; overflow: hidden; color: var(--_hy-danger); touch-action: none; user-select: none; -webkit-user-select: none; }
  .shutdown.quiet { color: var(--_hy-text-muted); }
  .shutdown.quiet:hover, .shutdown.quiet:focus-visible, .shutdown.quiet.is-holding { color: var(--_hy-danger); }
  .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--_hy-danger) 18%, transparent); transform: scaleX(0); transform-origin: var(--_hy-inline-start); }
  .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
  .button-label { position: relative; z-index: 1; }
  .hold-progress { flex-basis: 100%; text-align: end; font-size: 0.7rem; color: var(--_hy-danger); }
  .alert, .error, .boundary, .notice { margin-block-start: 0.9rem; border: 1px solid var(--_hy-line); border-radius: var(--_hy-radius-inner); background: var(--_hy-surface-raised); padding: 0.68rem 0.75rem; }
  .alert, .notice, .action-error { position: relative; overflow: hidden; padding-inline-start: 0.9rem; }
  .alert::before, .notice::before, .action-error::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--_hy-warning); }
  .alert.error::before, .action-error::before { background: var(--_hy-danger); }
  .action-error { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-block-start: 0.9rem; border: 1px solid color-mix(in srgb, var(--_hy-danger) 40%, var(--_hy-line)); border-radius: var(--_hy-radius-inner); padding-block: 0.4rem; padding-inline-end: 0.4rem; color: var(--_hy-danger); font-size: 0.85rem; }
  .action-error button { min-block-size: 2.2rem; color: inherit; }
  .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
  .boundary-orb { display: grid; place-items: center; inline-size: 1.75rem; block-size: 1.75rem; border-radius: var(--_hy-radius-inner); background: color-mix(in srgb, var(--_hy-state) 14%, transparent); color: var(--_hy-state); }
  .boundary-orb::before { content: ""; inline-size: 0.55rem; block-size: 0.55rem; border: 2px solid currentColor; border-radius: 50%; }
  .boundary-copy { min-inline-size: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
  .boundary-copy strong { font-size: 0.82rem; font-weight: 600; }
  section { margin-block-start: 1.05rem; }
  .section-head { justify-content: space-between; margin-block-end: 0.5rem; }
  .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
  .zone, .path, .actuator, details { border: var(--_hy-tile-border); border-radius: var(--_hy-radius-inner); background: var(--_hy-surface-raised); box-shadow: var(--_hy-tile-shadow); }
  .zone, .path, .actuator { padding: 0.72rem; }
  .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
  .zone::before { content: ""; position: absolute; inset-block-start: 0; inset-inline: 0; block-size: 2px; background: var(--_hy-state); opacity: 0; transform: scaleX(0.35); transform-origin: var(--_hy-inline-start); transition: opacity 220ms ease, transform 380ms ease; }
  .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
  /* A Room without demand is idle, whatever the Plant around it is doing. */
  .zone[data-demand-kind="none"] { --_hy-state: var(--_hy-idle); }
  .zone[data-demand-kind="heating"] { --_hy-state: var(--_hy-heating); }
  .zone[data-demand-kind="cooling"] { --_hy-state: var(--_hy-cooling); }
  /* An active tile's border follows its own state colour, so it resolves on the tile. */
  .zone[data-demand="true"] { --_hy-tile-active-border: var(--hydronicus-tile-active-border, 1px solid color-mix(in srgb, var(--_hy-state) 30%, var(--_hy-line))); background: color-mix(in srgb, var(--_hy-state) 7%, transparent); }
  .path[data-flowing="true"] { --_hy-tile-active-border: var(--hydronicus-tile-active-border, var(--_hy-tile-border)); }
  .zone[data-demand="true"], .path[data-flowing="true"] { border: var(--_hy-tile-active-border); box-shadow: var(--_hy-tile-active-shadow); }
  .zone[data-hvac-mode="off"] .metric.target { background: transparent; }
  .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--_hy-danger) 34%, var(--_hy-line)); }
  .row { justify-content: space-between; align-items: baseline; }
  .zone-title { min-inline-size: 0; overflow-wrap: anywhere; }
  .zone-owner { margin-block-start: 0.12rem; }
  .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin-block: 0.65rem 0.5rem; }
  .metric { min-inline-size: 0; border: 1px solid color-mix(in srgb, var(--_hy-line) 72%, transparent); border-radius: var(--_hy-radius-inner); padding: 0.52rem 0.58rem; }
  .metric.target { background: color-mix(in srgb, var(--_hy-state) 8%, transparent); }
  .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 600; letter-spacing: -0.02em; }
  .metric-unit { margin-inline-start: 0.15rem; color: var(--_hy-text-muted); font-size: 0.75rem; }
  .metric-label { display: block; margin-block-start: 0.06rem; color: var(--_hy-text-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .zone-note { margin-block-start: 0.28rem; }
  .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.45rem; }
  .diagnostic-chip { border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--_hy-text-muted); font-size: 0.7rem; }
  .diagnostic-chip.warning { color: var(--_hy-warning); border-color: color-mix(in srgb, var(--_hy-warning) 30%, var(--_hy-line)); }
  .diagnostic-chip.danger { color: var(--_hy-danger); border-color: color-mix(in srgb, var(--_hy-danger) 30%, var(--_hy-line)); }
  .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-block-start: 0.38rem; color: color-mix(in srgb, var(--_hy-warning) 80%, var(--_hy-text-muted)); }
  .hvac-modes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-block-start: 0.62rem; padding: 0.2rem; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); }
  .hvac-mode { flex: 1 1 auto; min-block-size: 2.2rem; padding-inline: 0.4rem; border: 1px solid transparent; border-radius: max(0px, calc(var(--_hy-radius-control) - 0.2rem)); background: transparent; box-shadow: none; font-size: 0.8rem; white-space: nowrap; }
  /* A selected segment keeps its per-mode tint unless the theme sets a selected background. */
  .hvac-mode[data-mode="heat"] { --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-heating) 16%, transparent)); }
  .hvac-mode[data-mode="cool"] { --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-cooling) 16%, transparent)); }
  .hvac-mode[data-mode="off"] { --_hy-selected-background: var(--hydronicus-selected-background, var(--_hy-surface-raised)); }
  [aria-pressed="true"] { background: var(--_hy-selected-background); color: var(--_hy-selected-color); }
  .hvac-mode[aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-accent) 50%, var(--_hy-line)); background: var(--_hy-selected-background); font-weight: 600; }
  .hvac-mode[data-mode="heat"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-heating) 55%, var(--_hy-line)); }
  .hvac-mode[data-mode="cool"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-cooling) 55%, var(--_hy-line)); }
  .hvac-mode[data-mode="off"][aria-pressed="true"] { border-color: var(--_hy-line); }
  .zone-actions { display: flex; gap: 0.35rem; margin-block-start: 0.45rem; }
  .zone-actions button { min-inline-size: 2.75rem; }
  .preset { flex: 1; min-inline-size: 0; }
  .path-list, .actuator-list { display: grid; gap: 0.55rem; }
  .path { overflow: hidden; }
  .path-head { justify-content: space-between; flex-wrap: wrap; }
  .path-heading { display: flex; align-items: center; gap: 0.42rem; min-inline-size: 0; }
  .path-heading::before { content: ""; flex: 0 0 auto; inline-size: 0.43rem; block-size: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--_hy-text-muted) 55%, transparent); }
  .path[data-flowing="true"] .path-heading::before { background: var(--_hy-state); animation: hydronicus-pulse 2.4s ease-out infinite; }
  .path[data-status="blocked"] .path-heading::before { background: var(--_hy-danger); }
  .path-track { display: flex; align-items: stretch; margin-block-start: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding-block: 0.08rem 0.25rem; padding-inline: 0.03rem; scroll-snap-type: inline proximity; scrollbar-width: thin; }
  .path-step { display: contents; }
  .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-inline-size: 0; border: 1px solid var(--_hy-line); border-radius: calc(var(--_hy-radius-inner) * 0.75); padding: 0.48rem 0.52rem; font-size: 0.76rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, background-color 220ms ease; }
  .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--_hy-state) 34%, var(--_hy-line)); background: color-mix(in srgb, var(--_hy-state) 8%, transparent); }
  .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--_hy-danger) 36%, var(--_hy-line)); }
  .node-kind { color: var(--_hy-text-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .node-name { margin-block-start: 0.18rem; font-weight: 600; line-height: 1.25; }
  .node-state { display: flex; align-items: center; gap: 0.28rem; margin-block-start: 0.3rem; color: var(--_hy-text-muted); font-size: 0.68rem; }
  .node-state::before { content: ""; inline-size: 0.3rem; block-size: 0.3rem; border-radius: 50%; background: currentColor; }
  .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--_hy-state) 78%, var(--_hy-text)); }
  .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-inline-size: 1.2rem; align-self: center; block-size: 2px; margin-inline: 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--_hy-text-muted) 24%, transparent); }
  :host(:dir(rtl)) .flow-link { transform: scaleX(-1); }
  .flow-link::before { content: ""; position: absolute; inset-inline-end: 0; inset-block-start: 50%; inline-size: 0.34rem; block-size: 0.34rem; border-block-start: 1px solid var(--_hy-text-muted); border-inline-end: 1px solid var(--_hy-text-muted); transform: translateY(-50%) rotate(45deg); }
  .flow-link::after { content: ""; position: absolute; inset-block: -1px; inset-inline-start: 0; inline-size: 58%; background: linear-gradient(90deg, transparent, var(--_hy-state), transparent); opacity: 0; transform: translateX(-120%); }
  .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--_hy-state) 24%, transparent); }
  .path[data-flowing="true"] .flow-link::before { border-color: var(--_hy-state); }
  .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--_hy-flow-duration) linear infinite; }
  .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--_hy-danger) 30%, transparent); }
  .path-problem { margin-block-start: 0.5rem; color: var(--_hy-danger); }
  .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
  .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
  .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.48rem; }
  .consumer-chip { max-inline-size: 100%; border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--_hy-text-muted); font-size: 0.7rem; overflow-wrap: anywhere; }
  .consumer-chip strong { color: var(--_hy-text); font-weight: 600; }
  details { overflow: hidden; padding: 0.62rem 0.72rem; }
  details + details { margin-block-start: 0.45rem; }
  summary { cursor: pointer; font-size: 0.85rem; }
  details[open] summary { margin-block-end: 0.25rem; }
  details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
  .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding-block: 0.48rem; border-block-start: 1px solid var(--_hy-line); font-size: 0.82rem; }
  .operation:first-of-type { border-block-start: 0; }
  .operation-marker { inline-size: 0.4rem; block-size: 0.4rem; margin-block-start: 0.35rem; border-radius: 50%; background: var(--_hy-text-muted); }
  .operation[data-result="proposed"] .operation-marker { background: var(--_hy-warning); }
  .operation[data-result="executed"] .operation-marker { background: var(--_hy-success); }
  .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--_hy-danger); }
  .operation-copy { min-inline-size: 0; }
  .empty-state { padding: 0.8rem; border: 1px dashed var(--_hy-line); border-radius: var(--_hy-radius-inner); text-align: center; }
  /* A Room card is the Room tile itself: the card frame replaces the tile's. */
  ha-card.room-card { padding: 0; }
  ha-card.room-card > .zone { border: 0; border-radius: inherit; box-shadow: none; }
  ha-card.room-card > .zone:not([data-demand="true"]) { background: transparent; }
  ha-card.room-card.compact > .zone { padding: 0.55rem; }
  ha-card.room-card > .notice, ha-card.room-card > .action-error { margin-block-start: 0.72rem; margin-inline: 0.72rem; }
  h2.zone-title { font-size: var(--ha-font-size-m, 0.9rem); }
  .state-card { display: grid; gap: 0.6rem; }
  .loading-card { min-block-size: 12rem; }
  .loading-head { display: flex; align-items: center; gap: 0.65rem; }
  .loading-mark, .skeleton { background: linear-gradient(105deg, var(--_hy-surface-raised) 20%, color-mix(in srgb, var(--_hy-text) 10%, transparent) 38%, var(--_hy-surface-raised) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
  .loading-mark { inline-size: 2.7rem; block-size: 2.7rem; border-radius: var(--_hy-radius-inner); }
  .skeleton { inline-size: min(16rem, 62cqi); block-size: 0.72rem; border-radius: 999px; }
  .skeleton.short { inline-size: min(10rem, 42cqi); margin-block-start: 0.45rem; }
  .loading-panel { block-size: 4.2rem; margin-block-start: 0.9rem; border: 1px solid var(--_hy-line); border-radius: var(--_hy-radius-inner); }
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
    0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--_hy-state) 38%, transparent); }
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
