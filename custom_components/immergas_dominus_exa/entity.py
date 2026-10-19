"""Shared identity and per-value freshness checks."""
from datetime import datetime, timezone
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, NAME, CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE


class DominusEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.client.mac}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.client.mac)},
                                           name=NAME, manufacturer="Immergas", model="Dominus EXA")

    @property
    def available(self):
        if not super().available or self.coordinator.data is None:
            return False
        observed = self.coordinator.data.observed.get(self.key)
        max_age = (self.coordinator.entry.options.get(CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE)
                   if self.key == "ha_room_temperature" and self.coordinator.data.values.get("room_source_mode") != "car"
                   else 2 * self.coordinator.interval + 30)
        return observed is not None and 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= max_age

    @property
    def value(self):
        return self.coordinator.data.values.get(self.key) if self.coordinator.data else None
