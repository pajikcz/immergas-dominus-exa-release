"""Actual options-handler persistence logic; no HA runtime, form or device test."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).parents[1] / "custom_components/immergas_dominus_exa"
namespace = {"math": math, "vol": SimpleNamespace(Invalid=ValueError)}
exec(compile((ROOT / "const.py").read_text(), str(ROOT / "const.py"), "exec"), namespace)
tree = ast.parse((ROOT / "config_flow.py").read_text())
validator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_room_target")
flow = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OptionsFlow")
handler = next(n for n in flow.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_step_init")
exec(compile(ast.Module(body=[validator, handler], type_ignores=[]), str(ROOT / "config_flow.py"), "exec"), namespace)


class OptionsPreservationTests(unittest.IsolatedAsyncioTestCase):
    def setup_flow(self, pending=45, include_pending=True, owned=False):
        options = {"scan_interval": 60, "allow_controls": True, "allow_gas_dhw": True,
                   "allow_compensation_write": False, "room_source_max_age": 1800,
                   "desired_room_target": 21, "room_temperature_source_mode": "car"}
        if include_pending:
            options["pending_dhw_target"] = pending
        runtime = SimpleNamespace(client=SimpleNamespace(owns_control=owned),
                                  connection_options={k:v for k,v in options.items()
                                                      if k not in namespace["RUNTIME_OPTIONS"]})
        entry = SimpleNamespace(options=options, runtime_data=runtime)
        create = Mock(side_effect=lambda **kwargs: kwargs)
        self.flow = SimpleNamespace(config_entry=entry, async_create_entry=create)
        return {k:v for k,v in options.items() if k not in {"pending_dhw_target", "room_temperature_source_mode"}}

    async def submit(self, data):
        # Any accidental network or runtime command access would fail: no such
        # methods exist on the stub entry/client. This tests returned options only.
        return (await namespace["async_step_init"](self.flow, data))["data"]

    async def test_pending_saved_target_survives_changed_options(self):
        data = self.setup_flow()
        data["scan_interval"] = 90
        result = await self.submit(data)
        self.assertEqual(result.get("pending_dhw_target"), 45)
        self.assertEqual(result["scan_interval"], 90)
        self.assertEqual(result["room_temperature_source_mode"], "car")

    async def test_saved_control_intent_survives_options_form(self):
        data = self.setup_flow()
        saved = {"owner": "dominus", "mode": "winter", "max_flow": 45,
                 "dhw_target": 40, "blocked": True}
        self.flow.config_entry.options["restore_control"] = saved
        result = await self.submit(data)
        self.assertEqual(result["restore_control"], saved)

    async def test_no_pending_target_is_invented(self):
        data = self.setup_flow(include_pending=False)
        result = await self.submit(data)
        self.assertNotIn("pending_dhw_target", result)

    async def test_changed_room_target_wins_over_previous_local_target(self):
        data = self.setup_flow(owned=True)
        data["desired_room_target"] = 24
        result = await self.submit(data)
        self.assertEqual(result["desired_room_target"], 24)
        self.assertEqual(result.get("pending_dhw_target"), 45)

    async def test_clearing_optional_mapping_does_not_resurrect_old_value(self):
        data = self.setup_flow()
        self.flow.config_entry.options["upstairs_temperature_source"] = "sensor.fixture_temperature"
        result = await self.submit(data)
        self.assertNotIn("upstairs_temperature_source", result)
        self.assertEqual(result.get("pending_dhw_target"), 45)

    async def test_pending_target_remains_across_repeated_option_saves(self):
        data = self.setup_flow()
        for interval in [90, 120, 60]:
            data["scan_interval"] = interval
            result = await self.submit(data)
            self.assertEqual(result.get("pending_dhw_target"), 45)
            self.flow.config_entry.options = result
        self.assertEqual(self.flow.async_create_entry.call_count, 3)

    async def test_saved_boundary_values_are_preserved_without_application(self):
        for value in [10, 60]:
            data = self.setup_flow(pending=value)
            result = await self.submit(data)
            self.assertEqual(result.get("pending_dhw_target"), value)
            self.assertEqual(self.flow.config_entry.options["pending_dhw_target"], value)
