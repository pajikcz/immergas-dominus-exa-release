"""Telemetry and diagnostic sensors. No network operations in properties."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from .entity import DominusEntity

PARALLEL_UPDATES = 0
TEMPERATURES = ("heating_water", "return_water", "dhw_water", "dhw_target", "room_temperature",
                "room_target", "ha_room_temperature", "desired_room_target", "compensated_room_target", "ch_setpoint", "max_flow", "otc_setpoint", "ch_min", "ch_max", "dhw_min", "dhw_max")
DIAGNOSTIC = {"otc_setpoint", "ch_min", "ch_max", "dhw_min", "dhw_max", "control_timer"}
MEASUREMENTS = {"heating_water", "return_water", "dhw_water", "room_temperature", "modulation"}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ValueSensor(entry.runtime_data, key)
                        for key in (*TEMPERATURES, "modulation", "control_timer", "mode", "compensation_status")])


class ValueSensor(DominusEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in TEMPERATURES:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_suggested_display_precision = 1 if key in {"heating_water", "dhw_water", "room_temperature", "room_target", "ha_room_temperature", "desired_room_target", "compensated_room_target"} else 0
        elif key == "modulation":
            self._attr_native_unit_of_measurement = "%"
        elif key == "control_timer":
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        if key in MEASUREMENTS:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key in DIAGNOSTIC:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def extra_state_attributes(self):
        if self.key == "room_temperature":
            # An unchanged temperature is still a new device observation. Expose
            # its actual read time, not HA's cached last_updated/last_reported.
            snapshot = self.coordinator.data
            observed = snapshot.observed.get(self.key) if snapshot else None
            return {"observed_at": observed.isoformat() if observed else None}
        if self.key in {"compensation_status", "ha_room_temperature"}:
            return {"last_error": self.coordinator.compensation_error,
                    "source_age_seconds": self.coordinator.source_age_seconds,
                    "source_selection": self.coordinator.data.values.get("room_source_mode") if self.coordinator.data else None,
                    "requested_control": getattr(self.coordinator, "restore_choice", {}),
                    "control_restore_status": getattr(self.coordinator, "restore_status", "not_requested")}
        return None

    @property
    def native_value(self):
        return self.value
