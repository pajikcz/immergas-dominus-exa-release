"""Integration constants."""
DOMAIN = "immergas_dominus_exa"
NAME = "Immergas Dominus EXA"
CONF_MAC = "mac"
CONF_CONTROLS = "allow_controls"
CONF_GAS_DHW = "allow_gas_dhw"
CONF_INTERVAL = "scan_interval"
CONF_ROOM_SOURCE = "room_temperature_source"  # Downstairs; legacy selected source.
CONF_ROOM_SOURCE_UPSTAIRS = "upstairs_temperature_source"
CONF_ROOM_SOURCE_MODE = "room_temperature_source_mode"
ROOM_SOURCE_MODES = ("downstairs", "upstairs", "car")
DEFAULT_ROOM_SOURCE_MODE = "downstairs"
CONF_ROOM_DESIRED = "desired_room_target"
# Saved locally in OFF; consumed only by an explicit Summer/Winter selection.
CONF_PENDING_DHW = "pending_dhw_target"
RUNTIME_OPTIONS = frozenset({CONF_ROOM_DESIRED, CONF_ROOM_SOURCE_MODE, CONF_PENDING_DHW})
CONF_SOURCE_MAX_AGE = "room_source_max_age"
DEFAULT_SOURCE_MAX_AGE = 1800
CONF_COMPENSATION_WRITE = "allow_compensation_write"
DEFAULT_ROOM_DESIRED = 21.0
# Integration policy, not device-discovered bounds.
ROOM_MIN = 5.0
ROOM_MAX = 35.0
DEFAULT_INTERVAL = 60
PLATFORMS = ("sensor", "binary_sensor", "select", "number")
