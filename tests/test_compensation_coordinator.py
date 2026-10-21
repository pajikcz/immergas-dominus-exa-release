"""Coordinator policy under a small HA stub; not an HA runtime/platform test."""
from datetime import datetime, timedelta, timezone
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from loader import client as c

ROOT = Path(__file__).parents[1] / "custom_components/immergas_dominus_exa"
PACKAGE = "dominus_coordinator_under_test"


class StubCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self.data = None
        self.last_update_success = True

    async def async_request_refresh(self):
        self.data = await self._async_update_data()

    def async_set_update_error(self, error):
        self.last_update_success = False

    def async_update_listeners(self):
        pass


package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
sys.modules[PACKAGE + ".client"] = c
stub_exception = ModuleType("homeassistant.exceptions")
stub_exception.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
stub_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
stub_coordinator.DataUpdateCoordinator = StubCoordinator
stub_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})
stub_const = ModuleType("homeassistant.const")
stub_const.CONF_HOST, stub_const.CONF_PASSWORD, stub_const.CONF_PORT = "host", "password", "port"
stub_const.UnitOfTemperature = SimpleNamespace(CELSIUS="°C")
stub_number = ModuleType("homeassistant.components.number")
stub_number.NumberEntity = type("NumberEntity", (), {})
stub_number.NumberDeviceClass = SimpleNamespace(TEMPERATURE="temperature")
stub_number.NumberMode = SimpleNamespace(BOX="box", SLIDER="slider")
stub_entity = ModuleType(PACKAGE + ".entity")


class StubDominusEntity:
    def __init__(self, coordinator, key):
        self.coordinator, self._attr_unique_id = coordinator, key

    @property
    def available(self):
        return True  # Test mode/authority policy; real HA handles freshness separately.


stub_entity.DominusEntity = StubDominusEntity
with patch.dict(sys.modules, {"homeassistant": ModuleType("homeassistant"),
                             "homeassistant.helpers": ModuleType("homeassistant.helpers"),
                             "homeassistant.exceptions": stub_exception,
                             "homeassistant.const": stub_const,
                             "homeassistant.helpers.update_coordinator": stub_coordinator,
                             "homeassistant.components": ModuleType("homeassistant.components"),
                             "homeassistant.components.number": stub_number,
                             PACKAGE + ".entity": stub_entity}):
    spec = importlib.util.spec_from_file_location(PACKAGE + ".coordinator", ROOT / "coordinator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    setup_spec = importlib.util.spec_from_file_location(PACKAGE + ".setup", ROOT / "__init__.py")
    setup_module = importlib.util.module_from_spec(setup_spec)
    setup_module.__package__ = PACKAGE
    setup_spec.loader.exec_module(setup_module)
    number_spec = importlib.util.spec_from_file_location(PACKAGE + ".number", ROOT / "number.py")
    number_module = importlib.util.module_from_spec(number_spec)
    number_spec.loader.exec_module(number_module)


class FakeClient:
    def __init__(self):
        self.owns_control = False
        self.allow_controls = self.allow_gas_dhw = True
        self.values = {"mode": "off", "room_temperature": 22, "room_target": 5}
        self.commands = []
        self.uncertain = False

    async def read_snapshot(self):
        return c.Snapshot(dict(self.values), dict.fromkeys(self.values, datetime.now(timezone.utc)))

    async def command(self, action, value=None):
        self.commands.append((action, value))
        if action == "take":
            self.owns_control = True
        elif action == "release":
            self.owns_control = False
        elif action in {"winter", "off", "summer"}:
            self.values["mode"] = action
        elif action == "room_target":
            if self.uncertain:
                raise c.WriteUncertain("Fixture: outcome uncertain")
            self.values["room_target"] = value
        values = {"mode": self.values["mode"], "dominus_active": self.owns_control, "control_timer": 0}
        if action == "room_target":
            values["room_target"] = value
        return c.Snapshot(values, dict.fromkeys(values, datetime.now(timezone.utc)))


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setup_coordinator(self, live=False, value="20", age=0, unit="°C"):
        source = SimpleNamespace(state=value, attributes={"unit_of_measurement": unit},
                                 last_reported=datetime.now(timezone.utc) - timedelta(seconds=age))
        hass = SimpleNamespace(states={"sensor.fixture_room": source})
        options = {"room_temperature_source": "sensor.fixture_room", "desired_room_target": 21,
                   "allow_controls": True, "allow_compensation_write": live, "room_source_max_age": 150}
        entry = SimpleNamespace(options=options)
        # HA background tasks eagerly start, but do not block services on I/O.
        entry.async_create_background_task = lambda hass, coro, name: asyncio.Task(
            coro, loop=asyncio.get_running_loop(), name=name, eager_start=True)
        client = FakeClient()
        hass.config_entries = SimpleNamespace(async_update_entry=lambda item, options: setattr(item, "options", options))
        return module.DominusCoordinator(hass, entry, client), client

    async def test_desired_target_updates_immediately_without_network_or_rearm(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.data = await coordinator._async_update_data()
        entity = number_module.DesiredRoomTarget(coordinator, coordinator.entry)
        entity.hass = coordinator.hass
        entity.async_write_ha_state = Mock()
        client.read_snapshot = AsyncMock(side_effect=AssertionError("Target edit must not poll"))
        client.command = AsyncMock(side_effect=AssertionError("Target edit must not write"))
        for value in (21.5, 22, 21.5, 5, 35):
            await asyncio.wait_for(entity.async_set_native_value(value), .5)
            self.assertEqual(entity.native_value, value)
            self.assertEqual(coordinator.data.values["desired_room_target"], value)
            self.assertFalse(coordinator._writes_armed)
        self.assertEqual(entity.async_write_ha_state.call_count, 5)
        client.read_snapshot.assert_not_awaited()
        client.command.assert_not_awaited()

    async def test_desired_target_remains_editable_without_snapshot_or_valid_input(self):
        coordinator, client = self.setup_coordinator(live=True, value="unavailable", age=9999)
        coordinator.last_update_success = False
        entity = number_module.DesiredRoomTarget(coordinator, coordinator.entry)
        entity.hass = coordinator.hass
        entity.async_write_ha_state = Mock()
        self.assertTrue(entity.available)
        await entity.async_set_native_value(24)
        self.assertEqual(entity.native_value, 24)
        self.assertIsNone(coordinator.data)
        self.assertFalse(coordinator.last_update_success)
        coordinator.data = c.Snapshot({"room_temperature": 22, "mode": "off"},
                                      {"room_temperature": datetime.now(timezone.utc)})
        await entity.async_set_native_value(24.5)
        self.assertEqual(entity.native_value, 24.5)
        self.assertNotIn("compensated_room_target", coordinator.data.values)
        for bad in (4.5, 35.5, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                await entity.async_set_native_value(bad)
        self.assertEqual(entity.native_value, 24.5)
        self.assertFalse(coordinator.last_update_success)
        self.assertFalse(coordinator._writes_armed)
        self.assertEqual(client.commands, [])

    async def test_verified_state_returns_before_diagnostics_and_keeps_other_timestamps(self):
        coordinator, client = self.setup_coordinator()
        coordinator.data = await coordinator._async_update_data()
        old_stamp = coordinator.data.observed["room_temperature"]
        ack, diagnostic = asyncio.Event(), asyncio.Event()
        original_command = client.command
        async def delayed_command(action, value=None):
            await ack.wait()
            return await original_command(action, value)
        async def delayed_snapshot():
            await diagnostic.wait()
            return c.Snapshot(dict(client.values), dict.fromkeys(client.values, datetime.now(timezone.utc)))
        client.command = AsyncMock(side_effect=delayed_command)
        client.read_snapshot = AsyncMock(side_effect=delayed_snapshot)
        task = asyncio.create_task(coordinator.command("winter"))
        await asyncio.sleep(0)
        self.assertEqual(coordinator.command_in_progress, "winter")
        self.assertEqual(coordinator.data.values["mode"], "off")  # Not optimistic.
        ack.set()
        await asyncio.wait_for(task, .5)
        self.assertFalse(diagnostic.is_set())
        self.assertEqual(coordinator.data.values["mode"], "winter")
        self.assertEqual(coordinator.data.observed["room_temperature"], old_stamp)
        self.assertIsNone(coordinator.command_in_progress)
        diagnostic.set()
        await coordinator._command_refresh_task

    async def test_uncertain_command_fails_without_waiting_or_claiming_target_mode(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.data = await coordinator._async_update_data()
        coordinator._writes_armed = True
        gate = asyncio.Event()
        original_read = client.read_snapshot
        async def delayed_snapshot():
            await gate.wait()
            return await original_read()
        client.read_snapshot = AsyncMock(side_effect=delayed_snapshot)
        client.command = AsyncMock(side_effect=c.WriteUncertain("Fixture uncertain"))
        with self.assertRaises(stub_exception.HomeAssistantError):
            await asyncio.wait_for(coordinator.command("winter"), .5)
        self.assertEqual(coordinator.data.values["mode"], "off")
        self.assertFalse(coordinator._writes_armed)
        self.assertIsNone(coordinator.command_in_progress)
        self.assertIn("uncertain", coordinator.last_command_error)
        gate.set()
        await coordinator._command_refresh_task

    async def test_followup_refreshes_coalesce_and_cancel_without_control_commands(self):
        coordinator, client = self.setup_coordinator()
        coordinator.data = await coordinator._async_update_data()
        gate = asyncio.Event()
        original_read = client.read_snapshot
        async def delayed_snapshot():
            await gate.wait()
            return await original_read()
        client.read_snapshot = AsyncMock(side_effect=delayed_snapshot)
        await coordinator.command("winter")
        first_task = coordinator._command_refresh_task
        await coordinator.command("off")
        await coordinator.command("off")
        self.assertIs(coordinator._command_refresh_task, first_task)
        gate.set()
        await first_task
        self.assertEqual(client.read_snapshot.await_count, 2)  # In-flight + one follow-up.
        gate.clear()
        await coordinator.command("off")
        before = list(client.commands)
        coordinator._command_refresh_task.cancel()  # Config-entry unload lifecycle.
        with self.assertRaises(asyncio.CancelledError):
            await coordinator._command_refresh_task
        self.assertEqual(client.commands, before)

    async def test_older_poll_cannot_overwrite_confirmed_state_but_newer_poll_can(self):
        coordinator, _ = self.setup_coordinator()
        now = datetime.now(timezone.utc)
        coordinator._confirmed = c.Snapshot({"mode": "winter"}, {"mode": now})
        old = c.Snapshot({"mode": "off"}, {"mode": now-timedelta(seconds=1)})
        coordinator._overlay_confirmed(old)
        self.assertEqual(old.values["mode"], "winter")
        newer = c.Snapshot({"mode": "off"}, {"mode": now+timedelta(seconds=1)})
        coordinator._overlay_confirmed(newer)
        self.assertEqual(newer.values["mode"], "off")

    async def test_parallel_click_rejected_and_cancellation_clears_pending_without_rearming(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.data = await coordinator._async_update_data()
        coordinator._writes_armed = True
        gate = asyncio.Event()
        async def blocked(*args):
            await gate.wait()
        client.command = AsyncMock(side_effect=blocked)
        task = asyncio.create_task(coordinator.command("winter"))
        await asyncio.sleep(0)
        with self.assertRaises(stub_exception.HomeAssistantError):
            await coordinator.command("off")
        self.assertEqual(client.command.await_count, 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(coordinator.command_in_progress)
        self.assertFalse(coordinator._writes_armed)
        self.assertIsNone(coordinator._command_refresh_task)

    async def test_upstairs_is_selected_without_averaging(self):
        coordinator, client = self.setup_coordinator()
        coordinator.hass.states["sensor.fixture_upstairs"] = SimpleNamespace(
            state="19", attributes={"unit_of_measurement": "°C"}, last_reported=datetime.now(timezone.utc))
        coordinator.entry.options.update(upstairs_temperature_source="sensor.fixture_upstairs", room_temperature_source_mode="upstairs")
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["ha_room_temperature"], 19)
        self.assertEqual(result.values["compensated_room_target"], 24)
        self.assertEqual(client.commands, [])

    async def test_car_uses_current_device_snapshot_and_zero_correction(self):
        coordinator, client = self.setup_coordinator(value="unavailable", age=9999)
        coordinator.entry.options["room_temperature_source_mode"] = "car"
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["ha_room_temperature"], 22)
        self.assertEqual(result.values["compensated_room_target"], 21)
        self.assertEqual(result.values["compensation_status"], "simulation_ready")
        client.values["room_temperature"] = float("nan")
        self.assertEqual((await coordinator._async_update_data()).values["compensation_status"], "source_unavailable")
        self.assertEqual(client.commands, [])

    async def test_live_source_switch_keeps_authority_and_never_sends_modes(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.hass.states["sensor.fixture_upstairs"] = SimpleNamespace(
            state="19", attributes={"unit_of_measurement": "°C"}, last_reported=datetime.now(timezone.utc))
        coordinator.entry.options["upstairs_temperature_source"] = "sensor.fixture_upstairs"
        await coordinator.command("take")
        await coordinator.command("winter")
        previous = list(client.commands)
        await coordinator.select_room_source("upstairs")
        self.assertEqual(client.commands, previous)  # Immediate selection never writes.
        self.assertEqual(coordinator.data.values["compensation_status"], "source_change_pending")
        coordinator.data = await coordinator._async_update_data()
        self.assertEqual(coordinator.data.values["room_target"], 24)
        previous = list(client.commands)
        await coordinator.select_room_source("car")
        self.assertEqual(client.commands, previous)
        coordinator.data = await coordinator._async_update_data()
        self.assertEqual(coordinator.data.values["room_target"], 21)
        self.assertTrue(client.owns_control)
        self.assertTrue(coordinator._writes_armed)
        self.assertEqual([a for a, _ in client.commands if a != "room_target"], ["take", "winter"])

    async def test_deliberate_source_choice_applies_small_offset_after_off(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.hass.states["sensor.fixture_upstairs"] = SimpleNamespace(
            state="20.2", attributes={"unit_of_measurement": "°C"}, last_reported=datetime.now(timezone.utc))
        coordinator.entry.options["upstairs_temperature_source"] = "sensor.fixture_upstairs"
        client.values["room_target"] = 23
        await coordinator.command("take")
        await coordinator.select_room_source("upstairs")
        self.assertTrue(coordinator._source_write_pending)
        self.assertFalse(any(a == "room_target" for a, _ in client.commands))
        await coordinator.command("winter")
        self.assertEqual(client.commands[-1], ("room_target", 22.8))
        self.assertFalse(coordinator._source_write_pending)

    async def test_unconfigured_source_choice_is_rejected_without_persisting(self):
        coordinator, client = self.setup_coordinator()
        coordinator.data = await coordinator._async_update_data()
        original = dict(coordinator.entry.options)
        with self.assertRaises(stub_exception.HomeAssistantError):
            await coordinator.select_room_source("upstairs")
        self.assertEqual(coordinator.entry.options, original)
        self.assertEqual(client.commands, [])

    async def test_stale_missing_and_wrong_unit_sources_are_selectable_without_io(self):
        for state, age, unit, expected in (("19", 9999, "°C", "source_stale"),
                                           ("unavailable", 0, "°C", "source_unavailable"),
                                           ("68", 0, "°F", "source_requires_celsius")):
            coordinator, client = self.setup_coordinator(live=True)
            await coordinator.command("take")
            await coordinator.command("winter")
            coordinator.hass.states["sensor.fixture_upstairs"] = SimpleNamespace(
                state=state, attributes={"unit_of_measurement": unit},
                last_reported=datetime.now(timezone.utc)-timedelta(seconds=age))
            coordinator.entry.options["upstairs_temperature_source"] = "sensor.fixture_upstairs"
            before = list(client.commands)
            client.read_snapshot = AsyncMock(side_effect=AssertionError("Selection must not read TCP"))
            await coordinator.select_room_source("upstairs")
            self.assertEqual(coordinator.entry.options["room_temperature_source_mode"], "upstairs")
            self.assertEqual(coordinator.data.values["room_source_mode"], "upstairs")
            self.assertEqual(coordinator.data.values["compensation_status"], expected)
            self.assertNotIn("ha_room_temperature", coordinator.data.values)
            self.assertNotIn("compensated_room_target", coordinator.data.values)
            self.assertFalse(coordinator._writes_armed)
            self.assertEqual(client.commands, before)
            client.read_snapshot.assert_not_awaited()

    async def test_source_selection_works_without_snapshot_and_during_transport_failure(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator.last_update_success = False
        client.read_snapshot = AsyncMock(side_effect=AssertionError("No network"))
        await coordinator.select_room_source("car")
        self.assertEqual(coordinator.entry.options["room_temperature_source_mode"], "car")
        self.assertIsNone(coordinator.data)
        self.assertFalse(coordinator.last_update_success)
        coordinator.data = c.Snapshot({"mode": "off", "room_temperature": 22},
                                      {"room_temperature": datetime.now(timezone.utc)})
        await coordinator.select_room_source("downstairs")
        self.assertEqual(coordinator.data.values["room_source_mode"], "downstairs")
        self.assertFalse(coordinator.last_update_success)
        self.assertFalse(coordinator._writes_armed)
        self.assertEqual(client.commands, [])
        client.read_snapshot.assert_not_awaited()

    async def test_source_choice_does_not_rearm_after_sensor_loss(self):
        coordinator, client = self.setup_coordinator(live=True)
        await coordinator.command("take")
        await coordinator.command("winter")
        coordinator.hass.states["sensor.fixture_room"].state = "unavailable"
        coordinator.data = await coordinator._async_update_data()
        before = list(client.commands)
        await coordinator.select_room_source("car")
        self.assertFalse(coordinator._writes_armed)
        self.assertEqual(coordinator.data.values["compensation_status"], "explicit_takeover_required")
        self.assertEqual(client.commands, before)

    async def test_water_controls_allow_all_known_modes_but_require_own_control(self):
        coordinator, client = self.setup_coordinator()
        coordinator.data = c.Snapshot({"mode": "off", "ch_min": 20, "ch_max": 85,
                                       "dhw_min": 10, "dhw_max": 60}, {})
        controls = [number_module.FlowLimit(coordinator), number_module.DHWTarget(coordinator)]
        for owned in (False, True):
            client.owns_control = owned
            for mode in ("off", "summer", "winter", "unmapped", "cooling"):
                coordinator.data.values["mode"] = mode
                self.assertEqual([entity.available for entity in controls],
                                 [owned and mode in {"off", "summer", "winter"}] * 2, (owned, mode))
        client.allow_controls = False
        self.assertEqual([entity.available for entity in controls], [False, False])

    async def test_explicit_panel_mode_routes_and_arms_only_owned_session(self):
        coordinator, client = self.setup_coordinator()
        async def panel(option):
            client.owns_control = option != "local"
            client.values["mode"] = "off" if option == "local" else option
            values = {"mode": client.values["mode"], "dominus_active": client.owns_control, "control_timer": 0}
            return c.Snapshot(values, dict.fromkeys(values, datetime.now(timezone.utc)))
        client.set_panel_mode = AsyncMock(side_effect=panel)
        await coordinator.command("panel_mode", "winter")
        self.assertTrue(coordinator._writes_armed)
        client.set_panel_mode.assert_awaited_with("winter")
        await coordinator.command("panel_mode", "local")
        self.assertFalse(coordinator._writes_armed)
        self.assertEqual(client.commands, [])  # Compensation remains preview-only.

    async def test_default_simulation_calculates_without_writes(self):
        coordinator, client = self.setup_coordinator()
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensated_room_target"], 23)
        self.assertEqual(result.values["ha_room_temperature"], 20)
        self.assertEqual(result.values["compensation_status"], "simulation_ready")
        self.assertEqual(client.commands, [])

    async def test_source_age_is_independent_of_boiler_polling_interval(self):
        coordinator, client = self.setup_coordinator(age=300)
        coordinator.entry.options.pop("room_source_max_age")  # Default1800s, not poll-derived150s.
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensation_status"], "simulation_ready")
        self.assertEqual(result.values["ha_room_temperature"], 20)
        self.assertEqual(client.commands, [])

    async def test_live_requires_explicit_takeover_even_if_adapter_is_active(self):
        coordinator, client = self.setup_coordinator(live=True)
        client.owns_control = True
        client.values["mode"] = "winter"
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensation_status"], "explicit_takeover_required")
        self.assertEqual(client.commands, [])

    async def test_explicit_take_and_winter_apply_once_then_deadband(self):
        coordinator, client = self.setup_coordinator(live=True)
        await coordinator.command("take")
        self.assertEqual(coordinator.data.values["compensation_status"], "winter_required")
        await coordinator.command("winter")
        self.assertEqual(coordinator.data.values["compensation_status"], "applied")
        self.assertEqual(coordinator.data.values["room_target"], 23)
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensation_status"], "unchanged")
        self.assertEqual(client.commands.count(("room_target", 23)), 1)

    async def test_invalid_stale_and_wrong_unit_never_write(self):
        for value, age, unit, expected in (("unavailable", 0, "°C", "source_unavailable"),
                                           ("20", 999, "°C", "source_stale"),
                                           ("68", 0, "°F", "source_requires_celsius")):
            coordinator, client = self.setup_coordinator(True, value, age, unit)
            await coordinator.command("take")
            await coordinator.command("winter")
            result = await coordinator._async_update_data()
            self.assertEqual(result.values["compensation_status"], expected)
            self.assertFalse(any(a == "room_target" for a, _ in client.commands))

    async def test_sensor_recovery_does_not_automatically_resume_writes(self):
        coordinator, client = self.setup_coordinator(live=True)
        await coordinator.command("take")
        await coordinator.command("winter")
        source = coordinator.hass.states["sensor.fixture_room"]
        source.state = "unavailable"
        await coordinator._async_update_data()
        source.state = "19"
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensation_status"], "explicit_takeover_required")
        self.assertEqual(client.commands.count(("room_target", 23)), 1)
        self.assertFalse(any(a == "room_target" and v == 24 for a, v in client.commands))

    async def test_uncertain_write_is_latched_not_retried_next_poll(self):
        coordinator, client = self.setup_coordinator(live=True)
        await coordinator.command("take")
        client.uncertain = True
        await coordinator.command("winter")
        self.assertEqual(coordinator.data.values["compensation_status"], "blocked_after_error")
        await coordinator._async_update_data()
        self.assertEqual(client.commands.count(("room_target", 23)), 1)
        self.assertIsNotNone(coordinator.compensation_error)

    async def test_desired_option_does_not_reload_but_other_options_do(self):
        coordinator, _ = self.setup_coordinator()
        entry = coordinator.entry
        entry.runtime_data, entry.entry_id = coordinator, "fixture"
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_reload=AsyncMock()))
        entry.options["desired_room_target"] = 22
        await setup_module._reload(hass, entry)
        hass.config_entries.async_reload.assert_not_awaited()
        entry.options["room_temperature_source_mode"] = "car"
        await setup_module._reload(hass, entry)
        hass.config_entries.async_reload.assert_not_awaited()
        entry.options["allow_controls"] = False
        await setup_module._reload(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with("fixture")

    async def test_lease_loss_without_saved_intent_disarms_and_does_not_retake(self):
        coordinator, client = self.setup_coordinator(live=True)
        coordinator._writes_armed = True  # Legacy session without persisted intent.
        coordinator._connection_lost()
        client.values["mode"] = "winter"
        result = await coordinator._async_update_data()
        self.assertEqual(result.values["compensation_status"], "explicit_takeover_required")
        self.assertEqual(client.commands, [])


if __name__ == "__main__":
    unittest.main()
