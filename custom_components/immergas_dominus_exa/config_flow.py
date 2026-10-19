"""Read-only configuration validation and explicit control permissions."""
import math
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector
from .client import DominusClient, DominusError, normalize_mac
from .const import (CONF_CONTROLS, CONF_GAS_DHW, CONF_INTERVAL, CONF_MAC,
                    CONF_ROOM_SOURCE, CONF_ROOM_DESIRED, CONF_COMPENSATION_WRITE,
                    CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE,
                    CONF_ROOM_SOURCE_UPSTAIRS, CONF_ROOM_SOURCE_MODE,
                    DEFAULT_ROOM_SOURCE_MODE, RUNTIME_OPTIONS,
                    DEFAULT_ROOM_DESIRED, ROOM_MIN, ROOM_MAX, DEFAULT_INTERVAL, DOMAIN, NAME)


def _room_target(value):
    value = float(value)
    if not math.isfinite(value) or not ROOM_MIN <= value <= ROOM_MAX:
        raise vol.Invalid("Invalid desired room temperature")
    return value


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = DominusClient(user_input[CONF_HOST], user_input[CONF_MAC],
                                       user_input[CONF_PORT], user_input.get(CONF_PASSWORD, ""))
                await self.async_set_unique_id(normalize_mac(user_input[CONF_MAC]))
                self._abort_if_unique_id_configured()
                await client.probe()  # No activation or test heating.
            except ValueError:
                errors["base"] = "invalid_settings"
            except DominusError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=NAME, data=user_input)
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Required(CONF_MAC): str,
                             vol.Required(CONF_PORT, default=2000): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                             vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
                                 selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input = {**user_input, CONF_ROOM_DESIRED: _room_target(user_input.get(CONF_ROOM_DESIRED))}
            except (TypeError, ValueError, vol.Invalid):
                errors[CONF_ROOM_DESIRED] = "invalid_room_target"
                user_input = {**user_input, CONF_ROOM_DESIRED: self.config_entry.options.get(CONF_ROOM_DESIRED, DEFAULT_ROOM_DESIRED)}
            if not errors:
                runtime = getattr(self.config_entry, "runtime_data", None)
                changed = {k: v for k, v in user_input.items() if k not in RUNTIME_OPTIONS}
                if runtime is not None and runtime.client.owns_control and changed != runtime.connection_options:
                    errors["base"] = "release_control_first"
                else:
                    return self.async_create_entry(title="", data={**user_input, CONF_ROOM_SOURCE_MODE:
                        self.config_entry.options.get(CONF_ROOM_SOURCE_MODE, DEFAULT_ROOM_SOURCE_MODE)})
        options = user_input if user_input is not None else self.config_entry.options
        schema = vol.Schema({
            vol.Required(CONF_INTERVAL, default=options.get(CONF_INTERVAL, DEFAULT_INTERVAL)):
                vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
            vol.Required(CONF_CONTROLS, default=options.get(CONF_CONTROLS, False)): bool,
            vol.Required(CONF_GAS_DHW, default=options.get(CONF_GAS_DHW, False)): bool,
            vol.Optional(CONF_ROOM_SOURCE, default=options.get(CONF_ROOM_SOURCE, vol.UNDEFINED)):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Optional(CONF_ROOM_SOURCE_UPSTAIRS, default=options.get(CONF_ROOM_SOURCE_UPSTAIRS, vol.UNDEFINED)):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Required(CONF_SOURCE_MAX_AGE, default=options.get(CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE)):
                vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
            vol.Required(CONF_ROOM_DESIRED, default=options.get(CONF_ROOM_DESIRED, DEFAULT_ROOM_DESIRED)):
                vol.All(vol.Coerce(float), vol.Range(min=ROOM_MIN, max=ROOM_MAX)),
            vol.Required(CONF_COMPENSATION_WRITE, default=options.get(CONF_COMPENSATION_WRITE, False)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
