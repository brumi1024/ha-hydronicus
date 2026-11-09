# Hydronicus

Hydronicus is a Home Assistant custom integration that coordinates a hydronic heating and cooling plant: the valves, the pumps, and the source behind them, described once as a Plant.

## Read first

- [CONTEXT.md](CONTEXT.md): the domain glossary (Plant, Source, Pump, Loop, Zone, Demand, and the rest). Use these words exactly.
- [docs/architecture.md](docs/architecture.md): the control loop, the pure core and the Home Assistant side, adapters, and the invariants every change keeps.
- [CONTRIBUTING.md](CONTRIBUTING.md): setup, commands, and project rules.

## The gate

`make verify` is the one gate: lint, the release check, format, mypy, and the full test suite with coverage.
Run the narrowest target while working (`make test-core`, `make test-integration`, `make test-sim`), then `make verify` before you are done.
Use the `hydronicus-verify` skill ([.agents/skills/hydronicus-verify](.agents/skills/hydronicus-verify/SKILL.md), linked from `.claude/skills/`) to map a change onto its done criteria and the right test seam.

## Rules a diff won't show you

- `custom_components/hydronicus/core/` never imports Home Assistant and keeps at least 90 percent coverage; control decisions belong there.
- No backward compatibility: stored configuration is the current plant file, so rename stored names freely and never add migrations, aliases, or fallbacks to older behaviour.
  Keep unique IDs stable regardless; they derive from the Plant ID and object slugs, and dashboards and automations depend on them.
- `strings.json` is the source of every UI string; after editing it, copy it to `translations/en.json` byte for byte.
- A new or renamed plant file key goes into [docs/examples/full-plant.yaml](docs/examples/full-plant.yaml); `tests/test_docs_examples.py` fails otherwise.
- Adapters in [adapters/](adapters/) hold no control logic; Hydronicus stays the only place that decides.
- Never use an em dash. In Markdown, put each sentence on its own line.
- Commit messages are short and sentence-case, or use a conventional prefix (`ci:`, `test:`, `docs:`); no co-author or agent attribution lines.
- Pull requests follow [the workflow in CONTRIBUTING.md](CONTRIBUTING.md#workflow) and fill in [the template](.github/pull_request_template.md); see [Pull requests](#pull-requests) below.
- Verify against synthetic entities, such as the trial kit in `docs/examples/trial/`, with **Control equipment** off; never arm physical equipment to finish a check.

## Pull requests

Write the pull request for a human reviewer, not as a report of your session.

- Use the template's sections in order, replace every comment, and delete a section that does not apply instead of writing "N/A" under it.
- Keep it short: "What and why" in two to four sentences, and every other section in a few bullets at most.
- Say why and what a user notices; never list changed files, restate the diff, or narrate the steps you took.
- Never paste test counts, coverage numbers, or command output; `make verify` passing is assumed, so mention it only when it did not pass.
- Fill in "Safety" only when the change touches control decisions, sequencing, condensation, frost, arming, Dry run, or commands; then name the invariants and the tests that hold them.
- Tick a checklist box only when it is true for this change.
- The title follows [CONTRIBUTING.md](CONTRIBUTING.md#workflow): short, sentence-case, the squash commit message on `main`.
- No attribution, signature, or "generated with" lines.

## Where things are

| Path | What |
| --- | --- |
| `custom_components/hydronicus/core/` | The pure core: model, plant file, `step()`, reconciler. |
| `custom_components/hydronicus/` | The Home Assistant side: runtime, flows, entities, Repairs. |
| `tests/core/`, `tests/integration/`, `tests/sim/` | Core tests, Home Assistant tests, and the plant simulator; see [tests/README.md](tests/README.md). |
| `adapters/` | Heat pump adapters and their contract. |
| `docs/examples/` | Plant files and the trial kit, all imported by the tests. |
| `docs/releases/` | One release note per version; the release workflow requires it. |

Machine-specific notes, such as a local Home Assistant instance or credentials, belong in `AGENTS.local.md` or `CLAUDE.local.md`, which git ignores, never in this file.
