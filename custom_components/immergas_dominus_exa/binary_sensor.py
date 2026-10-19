"""Reported flags, not inferred heat demand."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import DominusEntity

PARALLEL_UPDATES = 0
KEYS = ("heating_enabled", "dhw_enabled", "heating_active", "dhw_active", "flame",
        "dominus_active", "thermostat_input")


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FlagSensor(entry.runtime_data, key) for key in KEYS])


class FlagSensor(DominusEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_icon = "mdi:fire" if key == "flame" else "mdi:toggle-switch"
        if key.endswith("enabled") or key in {"dominus_active", "thermostat_input"}:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        return self.value
