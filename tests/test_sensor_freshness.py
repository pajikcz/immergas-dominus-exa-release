"""Per-field CAR observation timestamp; no HA runtime or hardware required."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class SensorFreshnessTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1] / "custom_components/immergas_dominus_exa"
        package = ModuleType("sensor_freshness_under_test")
        package.__path__ = [str(root)]
        entity = ModuleType(package.__name__ + ".entity")
        entity.DominusEntity = type("DominusEntity", (), {})
        sensor = ModuleType("homeassistant.components.sensor")
        sensor.SensorEntity = type("SensorEntity", (), {})
        sensor.SensorDeviceClass = SimpleNamespace(TEMPERATURE="temperature")
        sensor.SensorStateClass = SimpleNamespace(MEASUREMENT="measurement")
        const = ModuleType("homeassistant.const")
        const.UnitOfTemperature = SimpleNamespace(CELSIUS="°C")
        const.UnitOfTime = SimpleNamespace(MINUTES="min")
        helper = ModuleType("homeassistant.helpers.entity")
        helper.EntityCategory = SimpleNamespace(DIAGNOSTIC="diagnostic")
        with patch.dict(sys.modules, {package.__name__: package,
                                     entity.__name__: entity,
                                     sensor.__name__: sensor,
                                     const.__name__: const,
                                     helper.__name__: helper}):
            spec = importlib.util.spec_from_file_location(package.__name__ + ".sensor", root / "sensor.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.sensor = object.__new__(module.ValueSensor)
        self.sensor.key = "room_temperature"
        self.sensor.coordinator = SimpleNamespace(data=None)

    def test_missing_observation_is_not_replaced_by_current_time(self):
        self.assertEqual(self.sensor.extra_state_attributes, {"observed_at": None})
        self.sensor.coordinator.data = SimpleNamespace(observed={})
        self.assertEqual(self.sensor.extra_state_attributes, {"observed_at": None})

    def test_same_temperature_new_read_updates_timestamp_only(self):
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = SimpleNamespace(values={"room_temperature": 23.0},
                                   observed={"room_temperature": first})
        self.sensor.coordinator.data = snapshot
        self.assertEqual(self.sensor.extra_state_attributes["observed_at"], first.isoformat())
        second = first + timedelta(seconds=70)
        snapshot.observed["room_temperature"] = second
        self.assertEqual(self.sensor.extra_state_attributes["observed_at"], second.isoformat())
        self.assertEqual(snapshot.values["room_temperature"], 23.0)
        # A failed read or an unrelated local preview cannot freshen CAR.
        snapshot.observed["desired_room_target"] = second + timedelta(minutes=5)
        self.assertEqual(self.sensor.extra_state_attributes["observed_at"], second.isoformat())

    def test_other_sensors_unchanged(self):
        self.sensor.key = "heating_water"
        self.assertIsNone(self.sensor.extra_state_attributes)


if __name__ == "__main__":
    unittest.main()
