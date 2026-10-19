"""Explicitly requested diagnostic export; no raw frames or identification."""
from homeassistant.components.diagnostics import async_redact_data

REDACT = {"host", "mac", "password", "serial_number", "unique_id", "room_temperature_source", "upstairs_temperature_source"}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = coordinator.data
    return {"configuration": async_redact_data(dict(entry.data), REDACT),
            "options": async_redact_data(dict(entry.options), REDACT),
            "last_compensation_error": coordinator.compensation_error,
            "readings": dict(data.values) if data else {},
            "observed_at": {k: v.isoformat() for k, v in data.observed.items()} if data else {},
            "last_update_success": coordinator.last_update_success,
            "last_command_error": coordinator.last_command_error}
