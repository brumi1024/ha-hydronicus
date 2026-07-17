"""Config flow for Hydronic Climate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_CIRCUIT_IDS,
    CONF_CIRCUITS,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_OVERRUN,
    CONF_PLANT_ID,
    CONF_PUMP_ENTITY,
    CONF_PUMP_OVERRUN,
    CONF_PUMPS,
    CONF_ROUTES,
    CONF_SHADOW_MODE,
    CONF_TARGET_TEMPERATURE,
    CONF_TEMPERATURE_SENSOR,
    CONF_TOPOLOGY,
    CONF_VALVE_ENTITY,
    CONF_VALVE_IDS,
    CONF_VALVE_OPENING_TIME,
    CONF_VALVES,
    CONF_ZONES,
    DEFAULT_PLANT_NAME,
    DEFAULT_PUMP_OVERRUN,
    DEFAULT_TARGET_TEMPERATURE,
    DEFAULT_VALVE_OPENING_TIME,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
)
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.topology import TopologyValidationError, compile_topology
from .entry_configuration import effective_plant_configuration


def _valve_actuator_data(
    user_input: Mapping[str, Any], actuator_id: str
) -> dict[str, Any]:
    """Normalize one valve actuator payload for persistent subentry storage."""
    return {
        "id": actuator_id,
        CONF_ACTUATOR_KIND: ACTUATOR_KIND_VALVE,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
        CONF_OPENING_TIME: user_input[CONF_OPENING_TIME],
        CONF_CIRCUIT_IDS: user_input[CONF_CIRCUIT_IDS],
    }


def _valve_actuator_schema(
    circuit_options: list[selector.SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the shared valve form schema with optional reconfigure defaults."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): str,
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve"])
            ),
            vol.Required(
                CONF_OPENING_TIME,
                default=defaults.get(CONF_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_CIRCUIT_IDS,
                default=defaults.get(CONF_CIRCUIT_IDS, vol.UNDEFINED),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=circuit_options,
                    multiple=True,
                )
            ),
        }
    )


def _actuator_validation_error(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> str | None:
    """Return a flow error after validating the complete proposed topology."""
    if not data[CONF_NAME]:
        return "name_required"
    try:
        effective = effective_plant_configuration(
            entry,
            proposed_actuators=(data,),
            excluded_subentry_id=excluded_subentry_id,
        )
        compile_topology(effective.configuration)
    except (StoredTopologyError, TopologyValidationError):
        return "invalid_actuator"
    return None


class ActuatorSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Add an actuator that extends one or more existing hydraulic circuits."""

    def _circuit_options(self) -> list[selector.SelectOptionDict]:
        entry = self._get_entry()
        configuration = plant_configuration_from_entry_data(entry.data)
        return [
            selector.SelectOptionDict(value=circuit.id, label=circuit.name)
            for circuit in configuration.circuits
        ]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Create one valve actuator attached to selected circuits."""
        entry = self._get_entry()
        circuit_options = self._circuit_options()
        if not circuit_options:
            return self.async_abort(reason="no_circuits")

        errors: dict[str, str] = {}
        if user_input is not None:
            actuator_id = str(uuid4())
            data = _valve_actuator_data(user_input, actuator_id)
            if error := _actuator_validation_error(entry, data):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=data[CONF_NAME],
                    data=data,
                    unique_id=actuator_id,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_valve_actuator_schema(circuit_options),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update one valve actuator without changing its stable UUID."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        circuit_options = self._circuit_options()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _valve_actuator_data(user_input, subentry.data["id"])
            if error := _actuator_validation_error(
                entry,
                data,
                excluded_subentry_id=subentry.subentry_id,
            ):
                errors["base"] = error
            else:
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    title=data[CONF_NAME],
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_valve_actuator_schema(circuit_options, subentry.data),
            errors=errors,
        )


class HydronicClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle creation of a hydronic plant config entry."""

    VERSION = 1

    _draft: dict[str, Any]

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return dynamic object types supported by this plant."""
        return {SUBENTRY_TYPE_ACTUATOR: ActuatorSubentryFlowHandler}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors["base"] = "name_required"
            else:
                self._draft = {
                    CONF_NAME: name,
                    CONF_PLANT_ID: str(uuid4()),
                    CONF_SHADOW_MODE: True,
                }
                return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_PLANT_NAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Collect the first shadow-mode comfort zone."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if name:
                self._draft[CONF_TOPOLOGY] = {
                    CONF_ZONES: [
                        {
                            "id": str(uuid4()),
                            CONF_NAME: name,
                            CONF_TARGET_TEMPERATURE: user_input[CONF_TARGET_TEMPERATURE],
                            CONF_TEMPERATURE_SENSOR: user_input[CONF_TEMPERATURE_SENSOR],
                        }
                    ]
                }
                return await self.async_step_circuit()
            errors["base"] = "name_required"

        return self.async_show_form(
            step_id="zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(
                        CONF_TARGET_TEMPERATURE, default=DEFAULT_TARGET_TEMPERATURE
                    ): vol.Coerce(float),
                    vol.Required(CONF_TEMPERATURE_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Collect the first hydraulic circuit and its shadow-only equipment path."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if name:
                circuit_id = str(uuid4())
                valve_id = str(uuid4())
                pump_id = str(uuid4())
                zone_id = self._draft[CONF_TOPOLOGY][CONF_ZONES][0]["id"]
                self._draft[CONF_TOPOLOGY][CONF_VALVES] = [
                    {
                        "id": valve_id,
                        CONF_NAME: f"{name} valve",
                        CONF_ENTITY_ID: user_input[CONF_VALVE_ENTITY],
                        CONF_OPENING_TIME: user_input[CONF_VALVE_OPENING_TIME],
                    }
                ]
                self._draft[CONF_TOPOLOGY][CONF_PUMPS] = [
                    {
                        "id": pump_id,
                        CONF_NAME: f"{name} pump",
                        CONF_ENTITY_ID: user_input[CONF_PUMP_ENTITY],
                        CONF_OVERRUN: user_input[CONF_PUMP_OVERRUN],
                    }
                ]
                self._draft[CONF_TOPOLOGY][CONF_CIRCUITS] = [
                    {
                        "id": circuit_id,
                        CONF_NAME: name,
                        CONF_VALVE_IDS: [valve_id],
                        "pump_id": pump_id,
                    }
                ]
                self._draft[CONF_TOPOLOGY][CONF_ROUTES] = [
                    {"id": str(uuid4()), "zone_id": zone_id, "circuit_id": circuit_id}
                ]
                return await self.async_step_review()
            errors["base"] = "name_required"

        return self.async_show_form(
            step_id="circuit",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_VALVE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["switch", "valve"])
                    ),
                    vol.Required(CONF_PUMP_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    ),
                    vol.Required(
                        CONF_VALVE_OPENING_TIME, default=DEFAULT_VALVE_OPENING_TIME
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                    vol.Required(CONF_PUMP_OVERRUN, default=DEFAULT_PUMP_OVERRUN): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Validate the initial topology before storing it in a config entry."""
        if user_input is not None:
            try:
                compile_topology(plant_configuration_from_entry_data(self._draft))
            except (StoredTopologyError, TopologyValidationError):
                return self.async_show_form(step_id="review", errors={"base": "invalid_topology"})

            await self.async_set_unique_id(self._draft[CONF_PLANT_ID])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._draft[CONF_NAME], data=self._draft)

        topology = self._draft[CONF_TOPOLOGY]
        return self.async_show_form(
            step_id="review",
            description_placeholders={
                "zone": topology[CONF_ZONES][0][CONF_NAME],
                "circuit": topology[CONF_CIRCUITS][0][CONF_NAME],
            },
        )
