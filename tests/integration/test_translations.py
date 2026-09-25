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
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
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
    SUBENTRY_TYPE_ROOM,
    SUBENTRY_TYPE_SOURCE,
)
from tests.integration.plant_fixtures import plant_data, plant_entry

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


@dataclass(eq=False)
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
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
            ):
                # One element of a helper's tuple result, such as (errors, placeholders).
                return self._function_returns(module, node.value, depth, index=node.slice.value)
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
                # errors[field] = "key" also adds a value to a mapping bound to the name.
                if any(
                    (isinstance(t, ast.Name) and t.id == name)
                    or (
                        isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == name
                    )
                    for t in child.targets
                ):
                    yield child.value
                # errors, placeholders = helper(...) binds one element of the helper's result.
                for target in child.targets:
                    if isinstance(target, ast.Tuple) and isinstance(child.value, ast.Call):
                        for index, element in enumerate(target.elts):
                            if isinstance(element, ast.Name) and element.id == name:
                                yield ast.copy_location(
                                    ast.Subscript(value=child.value, slice=ast.Constant(index)),
                                    child,
                                )
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

    def _function_returns(
        self, module: _Module, call: ast.Call, depth: int, index: int | None = None
    ) -> set[str]:
        """Resolve what a helper returns, or one element of the tuples it returns."""
        if depth > 8:
            raise Unresolved(module.location(call))
        name = _call_name(call)
        # A helper is looked up in the calling module first, then in the modules it imports from.
        for owner in (module, *(other for other in self.modules if other is not module)):
            for function in ast.walk(owner.tree):
                if (
                    isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
                    and function.name == name
                ):
                    values: set[str] = set()
                    for node in ast.walk(function):
                        if not isinstance(node, ast.Return) or node.value is None:
                            continue
                        value = node.value
                        if index is not None and isinstance(value, ast.Tuple):
                            values |= self.resolve(owner, value.elts[index], depth + 1)
                        elif index is not None and isinstance(value, ast.Call):
                            values |= self._function_returns(owner, value, depth + 1, index)
                        else:
                            values |= self.resolve(owner, value, depth + 1)
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
    # Flow step mixins live in their own modules, so classes are indexed across modules.
    all_classes = {
        node.name: (module, node)
        for module in modules
        for node in ast.walk(module.tree)
        if isinstance(node, ast.ClassDef)
    }

    def with_mixins(module: _Module, flow: ast.ClassDef) -> list[tuple[_Module, ast.ClassDef]]:
        owners = [(module, flow)]
        for base in flow.bases:
            if isinstance(base, ast.Name) and base.id in all_classes:
                owners.extend(with_mixins(*all_classes[base.id]))
        return owners

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

        classes = {n.name: n for n in ast.walk(module.tree) if isinstance(n, ast.ClassDef)}
        for flow in classes.values():
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
            paths: set[tuple[str, _Module, ast.AST]] = set()
            # A flow also owns the keys of the mixins it inherits, from any module.
            for owner_module, node in (
                (owner_module, node)
                for owner_module, owner in with_mixins(module, flow)
                for node in ast.walk(owner)
            ):
                if isinstance(node, ast.Call):
                    name = _call_name(node)
                    if (step_node := _keyword(node, "step_id")) is not None:
                        for step in keys(owner_module, step_node):
                            steps.add(step)
                            paths.add((f"step.{step}", owner_module, node))
                    if (errors := _keyword(node, "errors")) is not None:
                        for error in keys(owner_module, errors):
                            paths.add((f"error.{error}", owner_module, node))
                    # errors.update(helper(...)) merges the errors a helper returns.
                    if (
                        name == "update"
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "errors"
                        and node.args
                    ):
                        for error in keys(owner_module, node.args[0]):
                            paths.add((f"error.{error}", owner_module, node))
                    if name == "async_abort" and (reason := _keyword(node, "reason")):
                        for abort in keys(owner_module, reason):
                            paths.add((f"abort.{abort}", owner_module, node))
                    if name == "AbortFlow" and node.args:
                        for abort in keys(owner_module, node.args[0]):
                            paths.add((f"abort.{abort}", owner_module, node))
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
                        implicit = keys(owner_module, reason)
                    for abort in implicit:
                        paths.add((f"abort.{abort}", owner_module, node))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "errors"
                        ):
                            for error in keys(owner_module, node.value):
                                paths.add((f"error.{error}", owner_module, node))
            # Errors returned through helper methods such as _details_form(error=...).
            for path, owner_module, node in sorted(paths, key=lambda item: item[0]):
                for prefix in prefixes:
                    requirement = _Requirement(f"{prefix}.{path}", owner_module.location(node))
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
        "options.abort.settings_saved",
        "options.error.dry_run_confirmation_required",
        "config.error.thermostat_loop",
        # Returned by the room basics helper for its Cooling section.
        "config.error.cooling_requires_room_loop",
        "config_subentries.room.error.cooling_requires_room_loop",
        "config.error.name_required",
        # Returned inside an (errors, placeholders) tuple by the room basics helper.
        "config.error.delivery_required",
        "config.error.invalid_document",
        "selector.temperature_aggregation",
        "selector.source_type",
    } <= paths
    assert "config_subentries.source.error.dry_run_shutdown_in_progress" in paths
    assert "config_subentries.source.abort.reconfigure_successful" in paths
    assert {
        "config_subentries.room.abort.no_pumps",
        "config_subentries.room.error.delivery_required",
        # Returned inside an (errors, placeholders) tuple by a room helper.
        "config_subentries.room.error.actuator_entity_in_use",
    } <= paths
    assert found.form_steps["config_subentries.room"] == {
        "user",
        "review",
        "reconfigure",
        "room",
        "thermostat",
        "sensors",
        "sensor_metadata",
        "sensor_policy",
        "edit_loop",
        "loop",
        "valve_details",
    }
    assert found.form_steps["config_subentries.source"] == {"user", "reconfigure", "review"}
    assert {"user", "guided", "room", "review", "import_plant", "import_review"} <= (
        found.form_steps["config"]
    )


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
        elif result["type"] == FlowResultType.MENU:
            step = f"{self.flow_prefix}.step.{result['step_id']}"
            self.steps.add(result["step_id"])
            self._need(f"{step}.title")
            for option in result["menu_options"]:
                self._need(f"{step}.menu_options.{option}")
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


async def test_setup_flow_steps_are_fully_translated(hass) -> None:
    """Every guided setup and import menu, form, field, section, error, and abort is translated."""
    audit = _FormAudit("config")
    flow = hass.config_entries.flow

    async def start(option: str) -> Mapping[str, Any]:
        result = audit.check(await flow.async_init(DOMAIN, context={"source": "user"}))
        return audit.check(await flow.async_configure(result["flow_id"], {"next_step_id": option}))

    async def submit(result: Mapping[str, Any], user_input: Mapping[str, Any]) -> Mapping[str, Any]:
        return audit.check(await flow.async_configure(result["flow_id"], dict(user_input)))

    plant = {CONF_NAME: "Plant", "pump_entity": "switch.pump"}
    result = await start("guided")
    result = await submit(result, {**plant, CONF_NAME: " "})
    assert result["errors"] == {CONF_NAME: "name_required"}
    result = await submit(result, plant)
    result = await submit(result, {CONF_NAME: "Living room", "valves": ["switch.pump"]})
    assert result["errors"] == {"temperature_sensors": "temperature_sensors_required"}
    room = {CONF_NAME: "Living room", "temperature_sensors": ["sensor.room"]}
    result = await submit(result, room)
    assert result["errors"] == {"base": "delivery_required"}
    result = await submit(result, {**room, "valves": ["switch.pump"]})
    assert result["errors"] == {"valves": "actuator_entity_in_use"}
    result = await submit(result, {**room, "valves": ["switch.living"], "add_another": True})
    result = await submit(
        result,
        {CONF_NAME: "Bedroom", "temperature_sensors": ["sensor.bed"], "valves": ["switch.bed"]},
    )
    # Two rooms on one pump carry a warning, so the review asks for confirmation.
    result = await submit(result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await flow.async_configure(result["flow_id"], {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    document = yaml.safe_load(
        (Path(__file__).parents[1] / "fixtures" / "plant_files" / "sources.yaml").read_text(
            encoding="utf-8"
        )
    )
    result = await start("import_plant")
    result = await submit(result, {"document": {"name": "No format version"}})
    assert result["errors"] == {"base": "invalid_document"}
    own_entity = next(
        registry_entry.entity_id
        for registry_entry in er.async_get(hass).entities.values()
        if registry_entry.platform == DOMAIN and registry_entry.domain == "sensor"
    )
    owning = deepcopy(document)
    owning["rooms"]["living_room"]["temperature_sensors"] = [own_entity]
    result = await submit(result, {"document": owning})
    assert result["errors"] == {"base": "document_own_entity"}
    result = await submit(result, {"document": document})
    assert result["step_id"] == "import_review"
    # The first Plant already binds switch.pump, which needs confirming.
    result = await submit(result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await flow.async_configure(result["flow_id"], {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    result = await start("import_plant")
    (imported,) = (
        entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.title == "Sources"
    )
    result = await submit(result, {"document": {**document, "id": imported.data[CONF_PLANT_ID]}})
    assert result["reason"] == "already_configured"

    assert audit.steps == {"user", "guided", "room", "review", "import_plant", "import_review"}
    assert audit.missing == []


async def test_plant_settings_steps_are_fully_translated(hass) -> None:
    """Every Plant settings menu, form, error, and abort renders translated."""
    audit = _FormAudit("options")
    flow = hass.config_entries.options
    entry = plant_entry(dict(_plant_entry().data))
    entry.add_to_hass(hass)

    async def menu(option: str) -> Mapping[str, Any]:
        result = audit.check(await flow.async_init(entry.entry_id))
        return audit.check(await flow.async_configure(result["flow_id"], {"next_step_id": option}))

    async def submit(result: Mapping[str, Any], user_input: Mapping[str, Any]) -> Mapping[str, Any]:
        return audit.check(await flow.async_configure(result["flow_id"], dict(user_input)))

    result = await menu("dry_run")
    result = await submit(result, {CONF_DRY_RUN: False})
    result = await submit(result, {})
    assert result["errors"] == {"base": "dry_run_confirmation_required"}
    result = await submit(result, {CONF_DRY_RUN_CONFIRMATION: True})
    assert result["errors"] == {"base": "dry_run_runtime_unavailable"}
    result = await submit(result, {CONF_DRY_RUN: True})
    assert result["reason"] == "settings_saved"

    pump = {CONF_NAME: "Spare pump", "entity_id": "switch.spare_pump", "overrun_seconds": 0.0}
    result = await menu("add_pump")
    result = await submit(result, {**pump, CONF_NAME: " "})
    assert result["errors"] == {CONF_NAME: "name_required"}
    result = await submit(result, {**pump, "entity_id": "switch.floor_valve"})
    assert result["errors"] == {"entity_id": "actuator_entity_in_use"}
    result = await submit(result, pump)
    assert result["reason"] == "settings_saved"

    # A pump entity another Plant binds is reviewed before it is saved.
    other_pump = {
        "id": "00000000-0000-4000-8000-0000000000fd",
        "name": "Other pump",
        "entity_id": "switch.other_plant_pump",
        "overrun_seconds": 0.0,
    }
    plant_entry(
        plant_data(
            {"pumps": [other_pump]},
            name="Other plant",
            plant_id="00000000-0000-4000-8000-0000000000fe",
        )
    ).add_to_hass(hass)
    result = await menu("add_pump")
    result = await submit(
        result, {**pump, CONF_NAME: "Shared pump", "entity_id": "switch.other_plant_pump"}
    )
    assert result["step_id"] == "pump_review"
    result = await submit(result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await submit(result, {"confirm": True})
    assert result["reason"] == "settings_saved"

    result = await menu("edit_pump")
    result = await submit(result, {"pump": PUMP_ID})
    result = await submit(
        result,
        {
            CONF_NAME: "Floor pump",
            "entity_id": "switch.floor_pump",
            "overrun_seconds": 120.0,
            "remove_pump": True,
        },
    )
    assert result["errors"] == {"remove_pump": "equipment_in_use"}

    result = await menu("export_plant")
    assert result["reason"] == "plant_exported"
    document = yaml.safe_load(
        result["description_placeholders"]["document"].removeprefix("```yaml\n").removesuffix("```")
    )

    own_entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "translation_own_sensor", suggested_object_id="translation_own"
    )
    result = await menu("edit_plant")
    result = await submit(result, {"document": {}})
    assert result["errors"] == {"base": "invalid_document"}
    result = await submit(
        result, {"document": {**document, "id": "00000000-0000-4000-8000-0000000000ff"}}
    )
    assert result["errors"] == {"base": "plant_id_mismatch"}
    owned = deepcopy(document)
    owned["pumps"]["floor_pump"]["power_feedback_entity"] = own_entity.entity_id
    result = await submit(result, {"document": owned})
    assert result["errors"] == {"base": "document_own_entity"}
    result = await submit(result, {"document": document})
    assert result["reason"] == "no_changes"

    renamed = deepcopy(document)
    renamed["name"] = "Renamed plant"
    # A newly shared valve is a warning the edit introduces, so it needs a confirmation.
    renamed.setdefault("valves", {})["newly_shared_valve"] = "switch.shared_equipment"
    loops = [*renamed.get("loops", {}).values()]
    loops += [
        loop
        for room in renamed.get("rooms", {}).values()
        for loop in room.get("loops", {}).values()
    ]
    for loop in loops:
        loop["valves"].append("newly_shared_valve")
    result = await menu("edit_plant")
    result = await submit(result, {"document": renamed})
    assert result["step_id"] == "edit_plant_review"
    result = await submit(result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await submit(result, {"confirm": True})
    assert result["reason"] == "settings_saved"

    assert audit.steps == {
        "init",
        "dry_run",
        "dry_run_confirmation",
        "pump",
        "pump_review",
        "edit_pump",
        "edit_plant",
        "edit_plant_review",
    }
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

    room = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_ROOM}")
    for option, steps in {
        "room": [{CONF_NAME: "Living room", "temperature_sensors": ["sensor.missing_room"]}],
        "thermostat": [{}],
        "sensors": [
            {"temperature_aggregation": "mean", "configure_sensor_metadata": True},
            {"sensor_entity": "sensor.missing_room"},
            {"temperature_aggregation": "mean"},
        ],
        "edit_loop": [
            {"loop": FLOOR_CIRCUIT_ID},
            {
                CONF_NAME: "Floor loop",
                "valves": ["switch.floor_valve"],
                "pump": PUMP_ID,
                "configure_valve_feedback": True,
            },
            {},
        ],
    }.items():
        result = await _reconfigure(
            hass,
            entry,
            SUBENTRY_TYPE_ROOM,
            room,
            [{"next_step_id": option}, *steps],
        )
        # The warnings already existed, so a save is reviewed only when it adds one.
        if result["type"] == FlowResultType.FORM and result["step_id"] == "review":
            result = room.check(
                await hass.config_entries.subentries.async_configure(
                    result["flow_id"], {"confirm": True}
                )
            )
        assert result["reason"] == "reconfigure_successful"
    menu = await _reconfigure(hass, entry, SUBENTRY_TYPE_ROOM, room, [])
    room.check(menu)
    hass.config_entries.subentries.async_abort(menu["flow_id"])
    # Another Plant already binds the Bedroom valve, so adding the room is reviewed.
    plant_entry(
        plant_data(
            {
                "valves": [
                    {
                        "id": "00000000-0000-4000-8000-0000000000f1",
                        "name": "Return valve",
                        "entity_id": "switch.return_valve",
                    }
                ]
            },
            plant_id="00000000-0000-4000-8000-0000000000f0",
        ),
        title="Other plant",
    ).add_to_hass(hass)
    bedroom = {
        CONF_NAME: "Bedroom",
        "temperature_sensors": ["sensor.bedroom"],
        "valves": ["switch.return_valve"],
    }
    result = await _subentry_flow(
        hass,
        entry,
        SUBENTRY_TYPE_ROOM,
        room,
        [{**bedroom, CONF_NAME: " "}, bedroom, {"confirm": False}, {"confirm": True}],
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    source = _FormAudit(f"config_subentries.{SUBENTRY_TYPE_SOURCE}")
    boiler = {CONF_NAME: "Boiler", "source_type": "external", "priority": 1}
    result = await _subentry_flow(
        hass, entry, SUBENTRY_TYPE_SOURCE, source, [{**boiler, CONF_NAME: " "}, boiler]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _reconfigure(hass, entry, SUBENTRY_TYPE_SOURCE, source, [boiler])
    assert result["reason"] == "reconfigure_successful"

    assert room.steps == {
        "user",
        "review",
        "reconfigure",
        "room",
        "thermostat",
        "sensors",
        "sensor_metadata",
        "sensor_policy",
        "edit_loop",
        "loop",
        "valve_details",
    }
    assert source.steps == {"user", "reconfigure"}
    assert [*room.missing, *source.missing] == []


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
