"""Translation contract: every key the integration can emit exists in strings.json.

Keys are discovered from the integration source, not from a hand-kept list:

- A static pass parses every integration module with ``ast`` and resolves the
  literal keys behind flow step IDs, flow errors, abort reasons (including the
  ones Home Assistant emits implicitly), ``translation_key`` arguments and
  attributes for entities, selectors, exceptions, and issues.
- A dynamic pass drives every config and subentry flow step, and loads a plant,
  then checks every form field, section, selector option, entity name, enum
  state, and repair issue that Home Assistant actually produced.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from probatio import to_field_list
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_NAME,
    CONF_PLANT_ID,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)

COMPONENT_DIR = Path(__file__).parents[2] / "custom_components" / DOMAIN
STRINGS_PATH = COMPONENT_DIR / "strings.json"
EN_PATH = COMPONENT_DIR / "translations" / "en.json"
ENTITY_PLATFORMS = frozenset(
    {"binary_sensor", "button", "climate", "number", "select", "sensor", "switch"}
)

# Abort reasons that Home Assistant raises on the integration's behalf.
IMPLICIT_ABORTS = {
    "ConfigFlow": {
        "_abort_if_unique_id_configured": {"already_configured"},
        "async_set_unique_id": {"already_in_progress"},
        "_abort_if_unique_id_mismatch": {"unique_id_mismatch"},
        "async_update_reload_and_abort": {"reconfigure_successful"},
        "async_update_and_abort": {"reconfigure_successful"},
    },
    "ConfigSubentryFlow": {
        "async_create_entry": {"already_configured"},
        "async_update_reload_and_abort": {"reconfigure_successful"},
        "async_update_and_abort": {"reconfigure_successful"},
    },
}
FLOW_BASES = {
    "ConfigFlow": "ConfigFlow",
    "ConfigSubentryFlow": "ConfigSubentryFlow",
    "OptionsFlow": "OptionsFlow",
    "OptionsFlowWithReload": "OptionsFlow",
    "RepairsFlow": "RepairsFlow",
    "ConfirmRepairFlow": "RepairsFlow",
}


def _strings() -> dict[str, Any]:
    return json.loads(STRINGS_PATH.read_text(encoding="utf-8"))


def _flatten(tree: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def _lookup(tree: Mapping[str, Any], dotted: str) -> Any:
    node: Any = tree
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


# --------------------------------------------------------------------------
# Static discovery
# --------------------------------------------------------------------------


class Unresolved(Exception):
    """A key expression that the static pass cannot reduce to literals."""


@dataclass
class _Module:
    path: Path
    tree: ast.Module
    parents: dict[ast.AST, ast.AST] = field(default_factory=dict)

    @property
    def stem(self) -> str:
        return self.path.stem

    def location(self, node: ast.AST) -> str:
        return f"{self.path.relative_to(COMPONENT_DIR.parent.parent)}:{getattr(node, 'lineno', 0)}"

    def enclosing(self, node: ast.AST, kinds: tuple[type, ...]) -> ast.AST | None:
        current = self.parents.get(node)
        while current is not None and not isinstance(current, kinds):
            current = self.parents.get(current)
        return current


def _load_modules() -> list[_Module]:
    modules = []
    for path in sorted(COMPONENT_DIR.rglob("*.py")):
        if "core" in path.relative_to(COMPONENT_DIR).parts:
            continue  # core/ has no Home Assistant imports and emits no translation keys
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = _Module(path, tree)
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                module.parents[child] = parent
        modules.append(module)
    return modules


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


class _Resolver:
    """Reduce key expressions to the string literals they can take."""

    def __init__(self, modules: list[_Module]) -> None:
        self.modules = modules
        self.constants: dict[str, set[str]] = {}
        self.mappings: dict[tuple[int, str], ast.Dict] = {}
        for module in modules:
            for node in module.tree.body:
                targets: list[ast.expr] = []
                value: ast.expr | None = None
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    targets, value = [node.target], node.value
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        self.constants.setdefault(target.id, set()).add(value.value)
                    elif isinstance(value, ast.Dict):
                        self.mappings[(id(module), target.id)] = value

    def resolve(self, module: _Module, node: ast.expr, depth: int = 0) -> set[str]:
        if depth > 8:
            raise Unresolved(module.location(node))
        if isinstance(node, ast.Constant):
            if node.value is None:
                return set()
            if isinstance(node.value, str):
                return {node.value}
            raise Unresolved(module.location(node))
        if isinstance(node, ast.IfExp):
            return self.resolve(module, node.body, depth + 1) | self.resolve(
                module, node.orelse, depth + 1
            )
        if isinstance(node, ast.Dict):
            values: set[str] = set()
            for value in node.values:
                values |= self.resolve(module, value, depth + 1)
            return values
        if isinstance(node, ast.Subscript):
            return self.resolve(module, node.value, depth + 1)
        if isinstance(node, ast.Name):
            return self._resolve_name(module, node, depth)
        if isinstance(node, ast.Call):
            return self._function_returns(module, node, depth)
        raise Unresolved(module.location(node))

    def _resolve_name(self, module: _Module, node: ast.Name, depth: int) -> set[str]:
        function = module.enclosing(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if function is not None:
            bound = [
                value
                for value in self._bindings(function, node.id)
                if value is not None and value is not node
            ]
            if bound:
                values: set[str] = set()
                for value in bound:
                    values |= self.resolve(module, value, depth + 1)
                return values
            if node.id in {arg.arg for arg in _all_args(function)}:
                return self._call_site_arguments(module, function, node.id, depth)
        if node.id in self.constants:
            return self.constants[node.id]
        mapping = self.mappings.get((id(module), node.id))
        if mapping is not None:
            return self.resolve(module, mapping, depth + 1)
        raise Unresolved(module.location(node))

    @staticmethod
    def _bindings(function: ast.AST, name: str) -> Iterator[ast.expr | None]:
        for child in ast.walk(function):
            if isinstance(child, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == name for t in child.targets):
                    yield child.value
            elif isinstance(child, ast.AnnAssign | ast.NamedExpr):
                target = child.target
                if isinstance(target, ast.Name) and target.id == name:
                    yield child.value

    def _call_site_arguments(
        self, module: _Module, function: ast.AST, parameter: str, depth: int
    ) -> set[str]:
        assert isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        positional = [arg.arg for arg in (*function.args.posonlyargs, *function.args.args)]
        is_method = bool(positional) and positional[0] in {"self", "cls"}
        values: set[str] = set()
        for other in self.modules:
            for call in (n for n in ast.walk(other.tree) if isinstance(n, ast.Call)):
                if _call_name(call) != function.name:
                    continue
                argument = _keyword(call, parameter)
                if argument is None and parameter in positional:
                    index = positional.index(parameter) - (1 if is_method else 0)
                    if 0 <= index < len(call.args):
                        argument = call.args[index]
                if argument is not None:
                    values |= self.resolve(other, argument, depth + 1)
        return values

    def _function_returns(self, module: _Module, call: ast.Call, depth: int) -> set[str]:
        name = _call_name(call)
        for function in ast.walk(module.tree):
            if (
                isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
                and function.name == name
            ):
                values: set[str] = set()
                for node in ast.walk(function):
                    if isinstance(node, ast.Return) and node.value is not None:
                        values |= self.resolve(module, node.value, depth + 1)
                return values
        raise Unresolved(module.location(call))


def _all_args(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = function.args
    return [*args.posonlyargs, *args.args, *args.kwonlyargs]


@dataclass
class _Requirement:
    path: str
    location: str

    def satisfied_by(self, strings: Mapping[str, Any]) -> bool:
        return _lookup(strings, self.path) is not None


@dataclass
class _Discovery:
    requirements: list[_Requirement] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    form_steps: dict[str, set[str]] = field(default_factory=dict)
    fix_flow_requirements: list[_Requirement] = field(default_factory=list)


def _subentry_types(module: _Module, resolver: _Resolver) -> dict[str, str]:
    """Map subentry flow class names to their subentry type from the parent flow."""
    types: dict[str, str] = {}
    for function in ast.walk(module.tree):
        if (
            isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
            and function.name == "async_get_supported_subentry_types"
        ):
            for node in ast.walk(function):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                    for key, value in zip(node.value.keys, node.value.values, strict=True):
                        if key is not None and isinstance(value, ast.Name):
                            (subentry_type,) = resolver.resolve(module, key)
                            types[value.id] = subentry_type
    return types


def _flow_kind(node: ast.ClassDef) -> str | None:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name in FLOW_BASES:
            return FLOW_BASES[name]
    return None


def _discover() -> _Discovery:
    modules = _load_modules()
    resolver = _Resolver(modules)
    found = _Discovery()
    subentry_types: dict[str, str] = {}
    for module in modules:
        subentry_types |= _subentry_types(module, resolver)

    def keys(module: _Module, node: ast.expr, *, skip_attributes: bool = False) -> set[str]:
        if skip_attributes and isinstance(node, ast.Attribute):
            return set()  # e.g. description.translation_key; the literal is found elsewhere
        try:
            return resolver.resolve(module, node)
        except Unresolved as err:
            found.unresolved.append(f"{err} ({ast.unparse(node)})")
            return set()

    def require(path: str, module: _Module, node: ast.AST) -> None:
        found.requirements.append(_Requirement(path, module.location(node)))

    for module in modules:
        platform = module.stem if module.stem in ENTITY_PLATFORMS else None
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                key_node = _keyword(node, "translation_key")
                if key_node is None:
                    continue
                if name.endswith("SelectorConfig"):
                    for key in keys(module, key_node):
                        require(f"selector.{key}", module, node)
                elif _keyword(node, "translation_domain") is not None:
                    for key in keys(module, key_node):
                        require(f"exceptions.{key}.message", module, node)
                elif name == "async_create_issue":
                    for key in keys(module, key_node):
                        require(f"issues.{key}.title", module, node)
                elif platform is not None:
                    for key in keys(module, key_node, skip_attributes=True):
                        require(f"entity.{platform}.{key}", module, node)
            elif isinstance(node, ast.Assign | ast.AnnAssign) and platform is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    target_name = (
                        target.attr
                        if isinstance(target, ast.Attribute)
                        else getattr(target, "id", None)
                    )
                    if target_name == "_attr_translation_key" and node.value is not None:
                        for key in keys(module, node.value, skip_attributes=True):
                            require(f"entity.{platform}.{key}", module, node)

        for flow in (n for n in ast.walk(module.tree) if isinstance(n, ast.ClassDef)):
            kind = _flow_kind(flow)
            if kind is None:
                continue
            if kind == "ConfigFlow":
                prefixes = ["config"]
            elif kind == "ConfigSubentryFlow":
                assert flow.name in subentry_types, f"{flow.name} is not a supported subentry type"
                prefixes = [f"config_subentries.{subentry_types[flow.name]}"]
            elif kind == "OptionsFlow":
                prefixes = ["options"]
            else:
                prefixes = [
                    f"issues.{issue}.fix_flow"
                    for issue, value in _strings().get("issues", {}).items()
                    if isinstance(value, Mapping) and "fix_flow" in value
                ]
                if not prefixes:
                    found.unresolved.append(
                        f"{module.location(flow)}: repairs flow {flow.name} has no issue fix_flow"
                    )
            steps = found.form_steps.setdefault(prefixes[0] if prefixes else flow.name, set())
            paths: set[tuple[str, ast.AST]] = set()
            for node in ast.walk(flow):
                if isinstance(node, ast.Call):
                    name = _call_name(node)
                    if (step_node := _keyword(node, "step_id")) is not None:
                        for step in keys(module, step_node):
                            steps.add(step)
                            paths.add((f"step.{step}", node))
                    if (errors := _keyword(node, "errors")) is not None:
                        for error in keys(module, errors):
                            paths.add((f"error.{error}", node))
                    if name == "async_abort" and (reason := _keyword(node, "reason")):
                        for abort in keys(module, reason):
                            paths.add((f"abort.{abort}", node))
                    if name == "AbortFlow" and node.args:
                        for abort in keys(module, node.args[0]):
                            paths.add((f"abort.{abort}", node))
                    implicit = IMPLICIT_ABORTS.get(kind, {}).get(name, set())
                    if name == "async_set_unique_id" and any(
                        kw.arg == "raise_on_progress"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is False
                        for kw in node.keywords
                    ):
                        implicit = set()
                    if (reason := _keyword(node, "reason")) is not None and name.endswith(
                        "_and_abort"
                    ):
                        implicit = keys(module, reason)
                    for abort in implicit:
                        paths.add((f"abort.{abort}", node))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "errors"
                        ):
                            for error in keys(module, node.value):
                                paths.add((f"error.{error}", node))
            # Errors returned through helper methods such as _details_form(error=...).
            for path, node in sorted(paths, key=lambda item: item[0]):
                for prefix in prefixes:
                    requirement = _Requirement(f"{prefix}.{path}", module.location(node))
                    if kind == "RepairsFlow":
                        found.fix_flow_requirements.append(requirement)
                    else:
                        found.requirements.append(requirement)
    return found


def test_en_json_is_byte_identical_to_strings_json() -> None:
    """The shipped English translation is a verbatim copy of strings.json."""
    assert EN_PATH.read_bytes() == STRINGS_PATH.read_bytes()


def test_every_statically_discovered_key_exists() -> None:
    """Every key literal used in the integration source has a translation."""
    found = _discover()
    strings = _strings()

    assert found.unresolved == []
    missing = sorted(
        f"{requirement.path} (used at {requirement.location})"
        for requirement in (*found.requirements, *found.fix_flow_requirements)
        if not requirement.satisfied_by(strings)
    )
    assert missing == []


def test_static_discovery_sees_the_flow_contract() -> None:
    """Guard the discovery itself so a refactor cannot silently empty it."""
    found = _discover()
    paths = {requirement.path for requirement in found.requirements}

    assert {
        "config.abort.already_configured",
        "config.abort.reconfigure_successful",
        "config.error.thermostat_loop",
        "config.error.name_required",
        "selector.thermostat_kind",
        "selector.temperature_aggregation",
        "selector.source_type",
    } <= paths
    for subentry_type in ("actuator", "circuit", "zone", "source"):
        assert f"config_subentries.{subentry_type}.error.dry_run_shutdown_in_progress" in paths
        assert f"config_subentries.{subentry_type}.abort.reconfigure_successful" in paths
    assert "config_subentries.zone.error.invalid_zone" in paths
    assert "config_subentries.zone.error.thermostat_loop" in paths
    assert found.form_steps["config_subentries.zone"] == {
        "user",
        "reconfigure",
        "details",
        "sensor_metadata",
        "sensor_policy",
        "review",
    }


def test_every_section_entry_is_a_nonempty_string() -> None:
    """strings.json holds only non-empty strings, so no key renders blank."""
    empty = [key for key, value in _flatten(_strings()).items() if not value or not value.strip()]
    assert empty == []


# --------------------------------------------------------------------------
# Dynamic discovery through real flows and a loaded plant
# --------------------------------------------------------------------------

PLANT_ID = "00000000-0000-4000-8000-0000000000a1"
ZONE_ID = "00000000-0000-4000-8000-0000000000a2"
VALVE_ID = "00000000-0000-4000-8000-0000000000a3"
PUMP_ID = "00000000-0000-4000-8000-0000000000a4"
FLOOR_CIRCUIT_ID = "00000000-0000-4000-8000-0000000000a5"
CEILING_CIRCUIT_ID = "00000000-0000-4000-8000-0000000000a6"


class _FormAudit:
    """Collect every translation gap in the flow results seen by a test."""

    def __init__(self, flow_prefix: str) -> None:
        self.strings = _strings()
        self.flow_prefix = flow_prefix
        self.missing: list[str] = []
        self.steps: set[str] = set()

    def _need(self, path: str) -> None:
        if _lookup(self.strings, path) is None:
            self.missing.append(path)

    def _fields(self, prefix: str, fields: list[dict[str, Any]]) -> None:
        for item in fields:
            name = item["name"]
            if item.get("type") == "expandable":
                section = f"{prefix}.sections.{name}"
                self._need(f"{section}.name")
                self._fields(section, item["schema"])
                continue
            self._need(f"{prefix}.data.{name}")
            self._need(f"{prefix}.data_description.{name}")
            select = item.get("selector", {}).get("select")
            if select is not None and (key := select.get("translation_key")):
                for option in select["options"]:
                    value = option if isinstance(option, str) else option["value"]
                    self._need(f"selector.{key}.options.{value}")

    def check(self, result: Mapping[str, Any]) -> Mapping[str, Any]:
        if result["type"] == FlowResultType.FORM:
            step = f"{self.flow_prefix}.step.{result['step_id']}"
            self.steps.add(result["step_id"])
            self._need(f"{step}.title")
            if result.get("data_schema") is not None:
                self._fields(
                    step,
                    to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer),
                )
            for error in (result.get("errors") or {}).values():
                self._need(f"{self.flow_prefix}.error.{error}")
        elif result["type"] == FlowResultType.ABORT:
            self._need(f"{self.flow_prefix}.abort.{result['reason']}")
        return result


def _plant_entry(*, dry_run: bool = True) -> MockConfigEntry:
    """Two circuits share one pump, so every topology change carries a warning."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: dry_run,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_ID,
                        "name": "Living room",
                        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                        "temperature_sensor_metadata": [{"entity_id": "sensor.missing_room"}],
                    }
                ],
                "valves": [
                    {
                        "id": VALVE_ID,
                        "name": "Floor valve",
                        "entity_id": "switch.floor_valve",
                        "opening_time_seconds": 30.0,
                    }
                ],
                "pumps": [
                    {
                        "id": PUMP_ID,
                        "name": "Floor pump",
                        "entity_id": "switch.floor_pump",
                        "overrun_seconds": 120.0,
                    }
                ],
                "circuits": [
                    {
                        "id": FLOOR_CIRCUIT_ID,
                        "name": "Floor loop",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                    },
                    {
                        "id": CEILING_CIRCUIT_ID,
                        "name": "Ceiling loop",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                    },
                ],
                "routes": [
                    {
                        "id": "00000000-0000-4000-8000-0000000000a7",
                        "zone_id": ZONE_ID,
                        "circuit_id": FLOOR_CIRCUIT_ID,
                    },
                    {
                        "id": "00000000-0000-4000-8000-0000000000a8",
                        "zone_id": ZONE_ID,
                        "circuit_id": CEILING_CIRCUIT_ID,
                    },
                ],
            },
        },
    )


async def test_initial_flow_steps_are_fully_translated(hass) -> None:
    """Every initial setup form, field, section, option, error, and abort is translated."""
    audit = _FormAudit("config")
    flow = hass.config_entries.flow

    result = audit.check(await flow.async_init(DOMAIN, context={"source": "user"}))
    result = audit.check(
        await flow.async_configure(result["flow_id"], {CONF_NAME: " ", CONF_DRY_RUN: False})
    )
    assert result["errors"] == {"base": "name_required"}
    result = audit.check(
        await flow.async_configure(result["flow_id"], {CONF_NAME: "Plant", CONF_DRY_RUN: False})
    )
    external = audit.check(await flow.async_init(DOMAIN, context={"source": "user"}))
    external = audit.check(await flow.async_configure(external["flow_id"], {CONF_NAME: "Plant"}))
    external = audit.check(
        await flow.async_configure(external["flow_id"], {"thermostat_kind": "external_climate"})
    )
    assert external["step_id"] == "zone_details"
    flow.async_abort(external["flow_id"])

    result = audit.check(
        await flow.async_configure(result["flow_id"], {"thermostat_kind": "hydronicus"})
    )
    result = audit.check(
        await flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: " ",
                "temperature_sensors": ["sensor.room"],
                "temperature_aggregation": "mean",
            },
        )
    )
    assert result["errors"] == {"base": "name_required"}
    result = audit.check(
        await flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Living room",
                "temperature_sensors": ["sensor.room"],
                "temperature_aggregation": "mean",
                "configure_sensor_metadata": True,
            },
        )
    )
    result = audit.check(
        await flow.async_configure(result["flow_id"], {"sensor_entity": "sensor.room"})
    )
    result = audit.check(
        await flow.async_configure(result["flow_id"], {"temperature_aggregation": "mean"})
    )
    circuit = {
        CONF_NAME: "Floor loop",
        "valve_entity": "switch.floor_valve",
        "pump_entity": "switch.floor_valve",
    }
    result = audit.check(await flow.async_configure(result["flow_id"], circuit))
    assert result["errors"] == {"base": "duplicate_actuator_entity"}
    result = audit.check(
        await flow.async_configure(
            result["flow_id"], {**circuit, "pump_entity": "switch.floor_pump"}
        )
    )
    result = audit.check(await flow.async_configure(result["flow_id"], {}))
    assert result["errors"] == {"base": "dry_run_confirmation_required"}
    result = await flow.async_configure(result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert audit.steps == {
        "user",
        "zone",
        "zone_details",
        "sensor_metadata",
        "sensor_policy",
        "circuit",
        "review",
    }
    assert audit.missing == []


async def test_parent_reconfigure_steps_are_fully_translated(hass) -> None:
    """The Dry run reconfigure path renders translated forms, errors, and aborts."""
    audit = _FormAudit("config")
    entry = _plant_entry()
    entry.add_to_hass(hass)

    result = audit.check(await entry.start_reconfigure_flow(hass))
    result = audit.check(
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_DRY_RUN: False})
    )
    result = audit.check(await hass.config_entries.flow.async_configure(result["flow_id"], {}))
    assert result["errors"] == {"base": "dry_run_confirmation_required"}
    result = audit.check(
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True}
        )
    )
    assert result["errors"] == {"base": "dry_run_runtime_unavailable"}
    result = audit.check(
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_DRY_RUN: True})
    )
    assert result["reason"] == "reconfigure_successful"

    assert audit.steps == {"reconfigure", "dry_run_confirmation"}
    assert audit.missing == []


async def _subentry_flow(hass, entry, subentry_type: str, audit: _FormAudit, steps):
    """Run one subentry flow through a list of inputs, auditing each result."""
    result = audit.check(
        await hass.config_entries.subentries.async_init(
            (entry.entry_id, subentry_type), context={"source": config_entries.SOURCE_USER}
        )
    )
    for user_input in steps:
        result = audit.check(
            await hass.config_entries.subentries.async_configure(result["flow_id"], user_input)
        )
        await hass.async_block_till_done()
    return result


async def _reconfigure(hass, entry, subentry_type: str, audit: _FormAudit, steps):
    subentry = next(
        item for item in entry.subentries.values() if item.subentry_type == subentry_type
    )
    result = audit.check(await entry.start_subentry_reconfigure_flow(hass, subentry.subentry_id))
    for user_input in steps:
        result = audit.check(
            await hass.config_entries.subentries.async_configure(result["flow_id"], user_input)
        )
        await hass.async_block_till_done()
    return result


async def test_subentry_flow_steps_are_fully_translated(hass) -> None:
    """Every subentry form, field, section, option, error, and abort is translated."""
    entry = _plant_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    confirm = {"confirm": True}

    actuator = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_ACTUATOR}")
    valve = {
        CONF_NAME: "Return valve",
        "entity_id": "switch.return_valve",
        "opening_time_seconds": 30,
        "circuit_ids": [FLOOR_CIRCUIT_ID],
    }
    result = await _subentry_flow(
        hass, entry, SUBENTRY_TYPE_ACTUATOR, actuator, [{**valve, CONF_NAME: " "}, valve, {}]
    )
    assert result["step_id"] == "review"
    assert result["errors"] == {"base": "confirm_required"}
    result = actuator.check(
        await hass.config_entries.subentries.async_configure(result["flow_id"], confirm)
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _reconfigure(hass, entry, SUBENTRY_TYPE_ACTUATOR, actuator, [valve, confirm])
    assert result["reason"] == "reconfigure_successful"

    circuit = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_CIRCUIT}")
    loop = {
        CONF_NAME: "Wall loop",
        "zone_ids": [ZONE_ID],
        "valve_ids": [VALVE_ID],
        "pump_id": PUMP_ID,
    }
    result = await _subentry_flow(
        hass, entry, SUBENTRY_TYPE_CIRCUIT, circuit, [{**loop, CONF_NAME: " "}, loop, confirm]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _reconfigure(hass, entry, SUBENTRY_TYPE_CIRCUIT, circuit, [loop, confirm])
    assert result["reason"] == "reconfigure_successful"

    zone = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_ZONE}")
    office = {
        CONF_NAME: "Office",
        "temperature_sensors": ["sensor.office"],
        "temperature_aggregation": "mean",
        "circuit_ids": [FLOOR_CIRCUIT_ID],
    }
    result = await _subentry_flow(
        hass,
        entry,
        SUBENTRY_TYPE_ZONE,
        zone,
        [
            {"thermostat_kind": "hydronicus"},
            {**office, CONF_NAME: " "},
            {**office, "configure_sensor_metadata": True},
            {"sensor_entity": "sensor.office"},
            {"temperature_aggregation": "weighted_mean"},
            confirm,
        ],
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _reconfigure(
        hass,
        entry,
        SUBENTRY_TYPE_ZONE,
        zone,
        [
            {"thermostat_kind": "external_climate"},
            {**office, "external_climate_entity": "climate.hydronic_plant_living_room"},
            {**office, "external_climate_entity": "climate.office"},
            confirm,
        ],
    )
    assert result["reason"] == "reconfigure_successful"

    source = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_SOURCE}")
    boiler = {CONF_NAME: "Boiler", "source_type": "external", "priority": 1}
    result = await _subentry_flow(
        hass, entry, SUBENTRY_TYPE_SOURCE, source, [{**boiler, CONF_NAME: " "}, boiler]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _reconfigure(hass, entry, SUBENTRY_TYPE_SOURCE, source, [boiler])
    assert result["reason"] == "reconfigure_successful"

    assert actuator.steps == {"user", "reconfigure", "review"}
    assert circuit.steps == {"user", "reconfigure", "review"}
    assert zone.steps == {
        "user",
        "reconfigure",
        "details",
        "sensor_metadata",
        "sensor_policy",
        "review",
    }
    assert source.steps == {"user", "reconfigure"}
    assert [*actuator.missing, *circuit.missing, *zone.missing, *source.missing] == []


async def test_runtime_entities_and_issues_are_translated(hass) -> None:
    """Entity names, enum states, select options, and raised issues are translated."""
    strings = _strings()
    entry = _plant_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    missing: list[str] = []
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert entities
    for registry_entry in entities:
        key = registry_entry.translation_key
        if key is None:
            continue
        prefix = f"entity.{registry_entry.domain}.{key}"
        if _lookup(strings, prefix) is None:
            missing.append(prefix)
            continue
        state = hass.states.get(registry_entry.entity_id)
        for option in (state.attributes.get("options") or []) if state else []:
            if _lookup(strings, f"{prefix}.state.{option}") is None:
                missing.append(f"{prefix}.state.{option}")

    issues = [
        issue
        for (domain, _issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ]
    assert issues, "the synthetic plant binds a missing sensor, so it raises an issue"
    for issue in issues:
        if _lookup(strings, f"issues.{issue.translation_key}.title") is None:
            missing.append(f"issues.{issue.translation_key}.title")

    assert missing == []
