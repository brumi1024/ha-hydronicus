# Contributing

Read [the architecture](docs/architecture.md) first, and [CONTEXT.md](CONTEXT.md) for the domain words.

## Setup

Hydronicus needs Python 3.14.2 or newer and [`uv`](https://docs.astral.sh/uv/).
`uv.lock` pins every development dependency.

```console
make bootstrap
make hooks
```

`make bootstrap` creates `.venv` from the lockfile, and `make hooks` installs the pre-commit hooks, which format changed files, lint, and run the core tests.

## Commands

| Command | Runs |
| --- | --- |
| `make test-core` | The pure core tests, with coverage. |
| `make test-integration` | The Home Assistant tests: setup, runtime, persistence, flows, entities, Repairs. |
| `make test-sim` | The plant simulator and its invariants. |
| `make lint`, `make format-check`, `make typecheck` | Ruff, the formatter, and mypy. |
| `make release-check` | Builds and inspects the HACS archive. |
| `make verify` | Everything above; the gate CI runs. |

Run the narrowest target while you work, and `make verify` before you open a pull request.

The simulator's property tests are deterministic in CI.
To explore more random plants locally, which takes a few minutes and keeps failing examples in `.hypothesis/`:

```console
HYPOTHESIS_SIM_PROFILE=sim-dev make test-sim
```

## Rules

- Put control logic in the pure core, `custom_components/hydronicus/core/`, which never imports Home Assistant, and keep Home Assistant specifics in the modules around it.
- Keep [the invariants](docs/architecture.md#testing-and-invariants).
  Start a behaviour change with a test that fails without it: a core test for control and the plant file, a simulator scenario for a safety invariant, an integration test for setup, flows, entities, and lifecycle.
- Keep unique IDs stable: they derive from the Plant ID and object slugs, and dashboards and automations depend on them.
- Stored configuration is the plant file; there are no migrations or aliases for older formats.
- `strings.json` is the source of every UI string; copy it to `translations/en.json` byte for byte after editing it.
- A new plant file key goes into [the full example](docs/examples/full-plant.yaml), which a test checks.
- In Markdown, put each sentence on its own line, and never use an em dash.
- To change dependencies, edit `pyproject.toml`, run `uv lock` and `make bootstrap`, and commit both files.

## Workflow

1. Branch from `main`, one focused change per branch.
   Open an issue first for a larger change, so the approach is agreed before the code.
2. Commit as you like on the branch; pull requests are squash-merged, so only the pull request's title and description last.
3. Run `make verify`, then open a pull request against `main`.
   CI runs the same gate.
4. Fill in [the template](.github/pull_request_template.md).
   Each section's comment says what belongs there; delete the comments and any section that does not apply.

A good pull request title is short and sentence-case, says what changes for the user or the code, and reads well as the commit message on `main`, such as "Hold a quick bridge write for 30 s instead of refusing it".
A conventional prefix (`ci:`, `test:`, `docs:`) suits a change that touches no behaviour.

A good description is short.
It explains why the change is needed and what a user notices, because the diff already shows what changed line by line.
Leave out file lists, test counts, coverage numbers, command output, and the history of how you got there.

## Releases

Versions follow semantic versioning, and the public interface is the plant file, the entities' unique IDs, and the actions.

- A patch release (`1.0.x`) fixes a bug and changes nothing a user relies on.
- A minor release (`1.x.0`) adds features, keys, entities, or actions, or fixes a larger bug, and every existing plant file still imports and means the same.
- A major release (`x.0.0`) breaks something a user relies on: a removed or renamed plant file key, a value that changes meaning, a plant file that no longer imports, a changed unique ID, or a removed action.

There are still no migrations or aliases, so a breaking change is a major release, and its release note says exactly what to change in a plant file before importing it again.

Bump the version in `manifest.json` and `pyproject.toml`, add `docs/releases/v<version>.md`, and run the Release workflow.
