"""Constants for Hydronicus."""

from typing import Final

DOMAIN: Final = "hydronicus"
PLATFORMS: Final = ("binary_sensor", "climate", "select", "sensor", "switch")

# Version 5 stores the format 2 plant file: the Plant in the entry data and each
# zone in a ``zone`` subentry. Earlier versions are refused, never migrated.
CONFIG_ENTRY_VERSION: Final = 5
CONFIG_ENTRY_MINOR_VERSION: Final = 0
SUBENTRY_TYPE_ZONE: Final = "zone"

# Entry options (contract K6): the output entities the owner has confirmed, and
# the Control equipment switch.
OPTION_ARMED_OUTPUTS: Final = "armed_outputs"
OPTION_CONTROL: Final = "control"

# The init data of a reconfigure flow that opens it at the form of a plant file
# path, such as the loop that binds a missing valve.
INIT_PATH: Final = "path"

# The runtime's persisted state (``homeassistant.helpers.storage.Store``).
STORE_VERSION: Final = 1
STORE_SAVE_DELAY: Final = 1.0
