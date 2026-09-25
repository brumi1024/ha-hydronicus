UV ?= uv

.PHONY: bootstrap hooks lint release-check public-beta-check format-check typecheck test-core test-integration test-sim test verify

bootstrap:
	$(UV) sync --frozen --extra test

hooks: bootstrap
	$(UV) run pre-commit install

lint:
	$(UV) run ruff check .
	$(UV) run python -m compileall -q custom_components tests
	$(UV) run python -m json.tool hacs.json >/dev/null
	$(UV) run python -m json.tool custom_components/hydronicus/manifest.json >/dev/null
	$(UV) run python -m json.tool custom_components/hydronicus/strings.json >/dev/null
	$(UV) run python -m json.tool custom_components/hydronicus/translations/en.json >/dev/null

release-check:
	$(UV) run python scripts/package_release.py --dry-run

public-beta-check:
	$(UV) run python scripts/public_beta_smoke.py

format-check:
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy custom_components/hydronicus

test-core:
	$(UV) run pytest tests/core --cov=custom_components/hydronicus/core --cov-report=term-missing

test-integration:
	$(UV) run pytest tests/integration

test-sim:
	$(UV) run pytest tests/sim

test:
	$(UV) run pytest --cov=custom_components/hydronicus/core --cov-report=term-missing

verify: lint release-check public-beta-check format-check typecheck test
