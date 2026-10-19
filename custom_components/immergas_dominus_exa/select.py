"""Explicit ownership and mapped modes; antifreeze stays safely blocked."""
from homeassistant.components.select import SelectEntity
from .entity import DominusEntity
from .const import CONF_ROOM_SOURCE_MODE, DEFAULT_ROOM_SOURCE_MODE, ROOM_SOURCE_MODES

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ModeSelect(entry.runtime_data), OwnerSelect(entry.runtime_data),
                        PanelModeSelect(entry.runtime_data), RoomSourceSelect(entry.runtime_data)])


class RoomSourceSelect(DominusEntity, SelectEntity):
    """Temperature-source choice, independent of CAR/HA control ownership."""
    _attr_options = list(ROOM_SOURCE_MODES)

    def __init__(self, coordinator):
        super().__init__(coordinator, "room_source_mode")

    @property
    def available(self):
        # Local configuration remains selectable during stale data/transport loss.
        return True

    @property
    def current_option(self):
        value = self.coordinator.entry.options.get(CONF_ROOM_SOURCE_MODE, DEFAULT_ROOM_SOURCE_MODE)
        return value if value in self.options else None

    async def async_select_option(self, option):
        await self.coordinator.select_room_source(option)
        self.async_write_ha_state()


class ModeSelect(DominusEntity, SelectEntity):
    _attr_options = ["off", "summer", "winter"]

    def __init__(self, coordinator):
        super().__init__(coordinator, "mode")

    @property
    def current_option(self):
        return self.value if self.value in self.options else None

    async def async_select_option(self, option):
        await self.coordinator.command(option)


class PanelModeSelect(DominusEntity, SelectEntity):
    """CAR or an explicit Dominus mode, using the existing guarded operations."""
    _attr_options = ["local", "off", "summer", "winter"]

    def __init__(self, coordinator):
        super().__init__(coordinator, "mode")
        self._attr_unique_id += "_controller"
        self._attr_translation_key = "controller_mode"

    @property
    def current_option(self):
        if self.coordinator.data.values.get("dominus_active") is False:
            return "local"
        if not self.coordinator.client.owns_control:
            return None  # Do not claim a foreign session as our own.
        return self.value if self.value in self.options else None

    @property
    def extra_state_attributes(self):
        return {"last_command_error": self.coordinator.last_command_error,
                "command_in_progress": self.coordinator.command_in_progress}

    async def async_select_option(self, option):
        await self.coordinator.command("panel_mode", option)


class OwnerSelect(DominusEntity, SelectEntity):
    _attr_options = ["local", "dominus"]

    def __init__(self, coordinator):
        super().__init__(coordinator, "dominus_active")
        self._attr_unique_id += "_control"
        self._attr_translation_key = "control_owner"

    @property
    def current_option(self):
        if self.coordinator.data.values.get("control_timer") != 0:
            return None
        return "dominus" if self.value else "local"

    async def async_select_option(self, option):
        if option not in self.options:
            raise ValueError("Unknown control owner")
        await self.coordinator.command("take" if option == "dominus" else "release")
