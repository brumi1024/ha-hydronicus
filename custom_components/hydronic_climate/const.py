"""Constants for Hydronic Climate."""

from typing import Final

DOMAIN: Final = "hydronic_climate"
PLATFORMS: Final = ("binary_sensor", "sensor")
CONF_NAME: Final = "name"
CONF_PLANT_ID: Final = "plant_id"
CONF_SHADOW_MODE: Final = "shadow_mode"
CONF_TOPOLOGY: Final = "topology"
CONF_ZONES: Final = "zones"
CONF_VALVES: Final = "valves"
CONF_PUMPS: Final = "pumps"
CONF_CIRCUITS: Final = "circuits"
CONF_ROUTES: Final = "routes"
CONF_ENTITY_ID: Final = "entity_id"
CONF_VALVE_IDS: Final = "valve_ids"
CONF_OPENING_TIME: Final = "opening_time_seconds"
CONF_OVERRUN: Final = "overrun_seconds"
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"
CONF_TARGET_TEMPERATURE: Final = "target_temperature"
CONF_VALVE_ENTITY: Final = "valve_entity"
CONF_PUMP_ENTITY: Final = "pump_entity"
CONF_VALVE_OPENING_TIME: Final = "valve_opening_time_seconds"
CONF_PUMP_OVERRUN: Final = "pump_overrun_seconds"
DEFAULT_PLANT_NAME: Final = "Hydronic plant"
DEFAULT_TARGET_TEMPERATURE: Final = 21.0
DEFAULT_VALVE_OPENING_TIME: Final = 30.0
DEFAULT_PUMP_OVERRUN: Final = 120.0
