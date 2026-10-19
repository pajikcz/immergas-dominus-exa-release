"""Small offline checks for source selection and invalid sensor states."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/immergas_dominus_exa"))
from temperature_input import preview_compensated_target, preview_measurement


class TemperatureInputTests(unittest.TestCase):
    def test_selects_one_measured_source_without_averaging_or_transmission(self):
        sources = {"sensor.simulated_upstairs": "21.4", "sensor.simulated_downstairs": "20.2"}
        for source, expected in (("sensor.simulated_upstairs", 21.4), ("sensor.simulated_downstairs", 20.2)):
            result = preview_measurement(sources, source)
            self.assertEqual(result["candidate_celsius"], expected)
            self.assertEqual(result["status"], "simulation_ready")
            self.assertTrue(result["simulation_only"])
            self.assertFalse(result["transmitted_to_boiler"])

    def test_unavailable_or_invalid_is_not_a_zero_degree_measurement(self):
        for value in (None, "unavailable", "unknown", "", "NaN", "inf", True):
            result = preview_measurement({"sensor.simulated_room": value}, "sensor.simulated_room")
            self.assertIsNone(result["candidate_celsius"])
            self.assertEqual(result["status"], "unavailable")
            self.assertFalse(result["transmitted_to_boiler"])

    def test_compensation_preserves_only_the_simple_error_equation(self):
        for measured, expected in ((20, 23), (21, 22), (22, 21)):
            result = preview_compensated_target(requested_celsius=21, car_celsius=22,
                                                ha_celsius=measured, target_min=5, target_max=35)
            self.assertEqual(result["candidate_target_celsius"], expected)
            self.assertEqual(result["controller_error_celsius"], result["requested_error_celsius"])
            self.assertFalse(result["transmitted_to_boiler"])
            self.assertFalse(result["native_behavior_verified"])

    def test_compensation_blocks_missing_inputs_and_out_of_range_targets(self):
        for measured, low, high, status in (("unavailable", 5, 35, "unavailable"),
                                           (float("nan"), 5, 35, "unavailable"),
                                           (-20, 5, 35, "outside_simulated_limits"),
                                           (20, 35, 5, "invalid_limits")):
            result = preview_compensated_target(requested_celsius=21, car_celsius=22,
                                                ha_celsius=measured, target_min=low, target_max=high)
            self.assertIsNone(result["candidate_target_celsius"])
            self.assertEqual(result["status"], status)
            self.assertFalse(result["transmitted_to_boiler"])


if __name__ == "__main__":
    unittest.main()
