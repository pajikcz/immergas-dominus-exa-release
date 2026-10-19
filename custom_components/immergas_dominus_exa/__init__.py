"""Immergas Dominus EXA. Setup and unload never send control commands."""
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from .client import DominusClient
from .const import CONF_CONTROLS, CONF_GAS_DHW, CONF_MAC, CONF_COMPENSATION_WRITE, PLATFORMS, RUNTIME_OPTIONS
from .coordinator import DominusCoordinator


async def async_setup_entry(hass, entry):
    client = DominusClient(entry.data[CONF_HOST], entry.data[CONF_MAC],
                           entry.data.get(CONF_PORT, 2000), entry.data.get(CONF_PASSWORD, ""),
                           allow_controls=entry.options.get(CONF_CONTROLS, False),
                           allow_gas_dhw=entry.options.get(CONF_GAS_DHW, False),
                           require_native_room=entry.options.get(CONF_COMPENSATION_WRITE, False),
                           persistent_readonly=True)
    coordinator = DominusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass, entry):
    # Target/source-choice adjustments must not tear down an owned control session.
    changed = {k: v for k, v in entry.options.items() if k not in RUNTIME_OPTIONS}
    if changed != entry.runtime_data.connection_options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
