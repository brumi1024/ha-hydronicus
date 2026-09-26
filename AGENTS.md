# Hydronicus

Hydronicus is a Home Assistant custom integration that coordinates a hydronic heating and cooling plant: the valves, the pumps, and the source behind them, described once as a Plant.

Read [CONTEXT.md](CONTEXT.md) for the domain glossary (Plant, Source, Pump, Loop, Zone, Demand, and the rest) before touching code that uses these words.
Read [docs/development.md](docs/development.md) for the boundary between the pure core (`custom_components/hydronicus/core/`) and the Home Assistant adapter around it, and for the numbered invariants every change keeps.

## The gate

`make verify` is the one gate (invariant 12): lint, the release check, format, mypy, and the full test suite with coverage.
Run the narrowest target while working (`make test-core`, `make test-integration`, `make test-sim`), then `make verify` before you're done.
Use the `hydronicus-verify` skill, also reachable at [.claude/skills/hydronicus-verify](.claude/skills/hydronicus-verify), to map a change onto its done criteria and the right test seam.

## Rules a diff won't show you

- `strings.json` is the source of every translation string; after editing it, copy it to `translations/en.json` byte for byte (see [Test boundaries](docs/development.md#test-boundaries)).
- There is no backward compatibility yet: rename stored names and drop migrations or aliases freely (see [Stored configuration](docs/development.md#stored-configuration)). Keep unique IDs stable regardless; they derive from the Plant ID and object slugs, and dashboards and automations depend on them.
- Never use an em dash.
- In Markdown, put each full sentence on its own physical line; keep normal Markdown structure otherwise.
- If a `CHANGELOG.md` ever appears here, never hand-edit it; treat it as generated.
- Commit messages: short, sentence-case, or a conventional prefix (`ci:`, `test:`, `docs:`, ...); never add a co-author or agent attribution line.

## Where things are

- [CONTRIBUTING.md](CONTRIBUTING.md): the contribution workflow.
- [docs/development.md](docs/development.md): environment setup, test layout, architecture boundaries, invariants.
- [docs/](docs/): user-facing documentation; [docs/releases/](docs/releases/) holds one file per version.
- [tests/README.md](tests/README.md): what belongs in `tests/core/`, `tests/integration/`, `tests/sim/`, and the repository root.
