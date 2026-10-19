"""The verified user maximum, not a direct burner-power control."""
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from .entity import DominusEntity
from .const import CONF_ROOM_DESIRED, DEFAULT_ROOM_DESIRED, ROOM_MIN, ROOM_MAX

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FlowLimit(entry.runtime_data), DHWTarget(entry.runtime_data),
                        DesiredRoomTarget(entry.runtime_data, entry)])


class DesiredRoomTarget(DominusEntity, NumberEntity):
    """User's true target, distinct from the compensated on-wire target."""
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_step = 0.5
    _attr_native_min_value = ROOM_MIN
    _attr_native_max_value = ROOM_MAX
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, "desired_room_target")
        self.entry = entry

    @property
    def available(self):
        # A local requested target is editable even when boiler data is unavailable.
        return True

    @property
    def native_value(self):
        return self.entry.options.get(CONF_ROOM_DESIRED, DEFAULT_ROOM_DESIRED)

    async def async_set_native_value(self, value):
        if not ROOM_MIN <= value <= ROOM_MAX:
            raise ValueError("Room target outside integration limits")
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_ROOM_DESIRED: float(value)})
        self.coordinator.update_room_preview()
        self.async_write_ha_state()


class DHWTarget(DominusEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator):
        super().__init__(coordinator, "dhw_target")
        self._attr_unique_id += "_control"
        self._attr_translation_key = "dhw_target_control"

    @property
    def available(self):
        client = self.coordinator.client
        return (super().available and client.allow_controls and client.allow_gas_dhw
                and client.owns_control and self.coordinator.data.values.get("mode") in {"off", "summer", "winter"}
                and {"dhw_min", "dhw_max"} <= self.coordinator.data.values.keys())

    @property
    def native_value(self):
        pending = self.coordinator.pending_dhw_target
        return pending if pending is not None else self.value

    @property
    def extra_state_attributes(self):
        pending = self.coordinator.pending_dhw_target
        return {"pending_value": pending, "reported_value": self.value,
                "application_status": "saved_for_next_active_mode" if pending is not None else "reported"}

    @property
    def native_min_value(self):
        return max(10, self.coordinator.data.values.get("dhw_min", 10))

    @property
    def native_max_value(self):
        return min(60, self.coordinator.data.values.get("dhw_max", 60))

    async def async_set_native_value(self, value):
        if not float(value).is_integer():
            raise ValueError("Whole degrees are required")
        await self.coordinator.set_dhw_target(int(value))
        self.async_write_ha_state()


class FlowLimit(DominusEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator):
        super().__init__(coordinator, "max_flow")
        self._attr_unique_id += "_control"

    @property
    def available(self):
        return (super().available and self.coordinator.client.allow_controls
                and self.coordinator.client.owns_control
                and self.coordinator.data.values.get("mode") in {"off", "summer", "winter"}
                and {"ch_min", "ch_max"} <= self.coordinator.data.values.keys())

    @property
    def native_value(self):
        return self.value

    @property
    def native_min_value(self):
        return max(20, self.coordinator.data.values.get("ch_min", 20))

    @property
    def native_max_value(self):
        return min(85, self.coordinator.data.values.get("ch_max", 85))

    async def async_set_native_value(self, value):
        if not float(value).is_integer():
            raise ValueError("Whole degrees are required")
        await self.coordinator.command("max_flow", int(value))
