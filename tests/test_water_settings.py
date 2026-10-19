"""Local OFF settings and deliberate mode application, without device/network I/O."""
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, Mock
import test_compensation_coordinator as fixture

module, number_module, c = fixture.module, fixture.number_module, fixture.c


class WaterSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setup_water(self, mode="off"):
        coordinator, client = fixture.CoordinatorTests().setup_coordinator()
        client.owns_control = True
        client.values.update(mode=mode, dhw_target=10, dhw_min=10, dhw_max=60,
                             max_flow=40, ch_min=20, ch_max=85)
        coordinator.data = c.Snapshot(dict(client.values), dict.fromkeys(client.values, datetime.now(timezone.utc)))
        coordinator._queue_command_refresh = Mock()  # No background fake poll racing test assertions.
        original = client.command

        async def command(action, value=None):
            result = await original(action, value)
            if action in {"dhw_target", "max_flow"}:
                client.values[action] = value
                result.values[action] = value
                result.observed[action] = datetime.now(timezone.utc)
            return result

        client.command = AsyncMock(side_effect=command)

        async def panel(option):
            client.values["mode"] = "off" if option == "local" else option
            client.owns_control = option != "local"
            values = {"mode": client.values["mode"], "dominus_active": client.owns_control}
            return c.Snapshot(values, dict.fromkeys(values, datetime.now(timezone.utc)))

        client.set_panel_mode = AsyncMock(side_effect=panel)
        return coordinator, client

    async def test_off_save_persists_without_network_or_rearm(self):
        co, client = self.setup_water()
        co._writes_armed = False
        for value in [20, 40, 60, 10]:
            await co.set_dhw_target(value)
            self.assertEqual(co.entry.options["pending_dhw_target"], value)
            self.assertEqual(co.data.values["dhw_target"], 10)
            self.assertEqual(co.data.values["mode"], "off")
            self.assertFalse(co._writes_armed)
        client.command.assert_not_awaited()
        client.set_panel_mode.assert_not_awaited()
        co._queue_command_refresh.assert_not_called()
        restored = module.DominusCoordinator(co.hass, co.entry, client)
        self.assertEqual(restored.pending_dhw_target, 10)
        self.assertFalse(restored._writes_armed)

    async def test_saved_value_does_not_reload_entry_or_apply_during_poll(self):
        co, client = self.setup_water()
        before = dict(co.connection_options)
        await co.set_dhw_target(45)
        self.assertEqual({k:v for k,v in co.entry.options.items() if k not in module.RUNTIME_OPTIONS}, before)
        result = await co._async_update_data()
        self.assertEqual(result.values["mode"], "off")
        self.assertEqual(result.values["dhw_target"], 10)
        self.assertEqual(co.pending_dhw_target, 45)
        client.command.assert_not_awaited()

    async def test_only_explicit_active_mode_applies_saved_target_once(self):
        for mode in ["summer", "winter"]:
            with self.subTest(mode=mode):
                co, client = self.setup_water()
                await co.set_dhw_target(45)
                await co.command("panel_mode", mode)
                client.set_panel_mode.assert_awaited_once_with(mode)
                client.command.assert_awaited_once_with("dhw_target", 45)
                self.assertIsNone(co.pending_dhw_target)
                self.assertEqual(co.data.values["mode"], mode)
                self.assertEqual(co.data.values["dhw_target"], 45)
                await co.command("panel_mode", mode)
                self.assertEqual(client.command.await_count, 1)  # No repeat.

    async def test_legacy_explicit_mode_selector_also_applies_saved_target(self):
        co, client = self.setup_water()
        await co.set_dhw_target(45)
        await co.command("summer")
        self.assertEqual(client.commands, [("summer", None), ("dhw_target", 45)])
        self.assertEqual(co.data.values["mode"], "summer")

    async def test_off_local_and_take_do_not_apply_saved_target(self):
        for action, value in [("panel_mode", "off"), ("panel_mode", "local"), ("take", None), ("off", None)]:
            with self.subTest(action=action, value=value):
                co, client = self.setup_water()
                await co.set_dhw_target(45)
                await co.command(action, value)
                self.assertEqual(co.pending_dhw_target, 45)
                self.assertFalse(any(a == "dhw_target" for a, v in client.commands))

    async def test_active_edit_supersedes_saved_value_and_does_not_switch_mode(self):
        for mode in ["summer", "winter"]:
            co, client = self.setup_water(mode)
            co.entry.options["pending_dhw_target"] = 45
            await co.set_dhw_target(35)
            client.command.assert_awaited_once_with("dhw_target", 35)
            client.set_panel_mode.assert_not_awaited()
            self.assertIsNone(co.pending_dhw_target)
            self.assertEqual(co.data.values["mode"], mode)
            self.assertEqual(co.data.values["dhw_target"], 35)

    async def test_guards_block_local_save_as_well_as_live_writes(self):
        for bad in [9, 61, 40.5, float("nan"), float("inf"), True, "40"]:
            co, client = self.setup_water()
            with self.assertRaises(Exception):
                await co.set_dhw_target(bad)
            self.assertIsNone(co.pending_dhw_target)
            client.command.assert_not_awaited()
        for mutation in [lambda co, cl: setattr(cl, "owns_control", False),
                         lambda co, cl: setattr(cl, "allow_controls", False),
                         lambda co, cl: setattr(cl, "allow_gas_dhw", False),
                         lambda co, cl: setattr(co, "last_update_success", False),
                         lambda co, cl: setattr(co, "command_in_progress", "winter"),
                         lambda co, cl: co.data.values.update(mode="cooling"),
                         lambda co, cl: co.data.values.update(dhw_max=30)]:
            co, client = self.setup_water()
            mutation(co, client)
            with self.assertRaises(Exception):
                await co.set_dhw_target(40)
            self.assertIsNone(co.pending_dhw_target)
            client.command.assert_not_awaited()

    async def test_failed_saved_write_keeps_confirmed_mode_and_never_retries(self):
        co, client = self.setup_water()
        await co.set_dhw_target(45)
        client.command.side_effect = c.WriteUncertain("Fixture only")
        with self.assertRaises(Exception):
            await co.command("panel_mode", "summer")
        self.assertEqual(co.data.values["mode"], "summer")
        self.assertEqual(co.data.values["dhw_target"], 10)
        self.assertIsNone(co.pending_dhw_target)
        self.assertFalse(co._writes_armed)
        self.assertIsNone(co.command_in_progress)
        await co.command("panel_mode", "summer")
        self.assertEqual(client.command.await_count, 1)

    async def test_failed_mode_does_not_consume_or_apply_saved_target(self):
        co, client = self.setup_water()
        await co.set_dhw_target(45)
        client.set_panel_mode.side_effect = c.DominusError("Fixture only")
        with self.assertRaises(Exception):
            await co.command("panel_mode", "summer")
        self.assertEqual(co.pending_dhw_target, 45)
        client.command.assert_not_awaited()
        self.assertEqual(co.data.values["mode"], "off")

    async def test_off_number_is_saved_request_with_separate_reported_value(self):
        co, client = self.setup_water()
        entity = number_module.DHWTarget(co)
        entity.value = 10  # Small HA stub has no snapshot value property.
        entity.async_write_ha_state = Mock()
        self.assertTrue(entity.available)
        self.assertEqual(entity.native_value, 10)
        await entity.async_set_native_value(45)
        self.assertEqual(entity.native_value, 45)
        self.assertEqual(entity.extra_state_attributes,
                         {"pending_value":45, "reported_value":10,
                          "application_status":"saved_for_next_active_mode"})
        client.command.assert_not_awaited()

    async def test_flow_number_in_off_only_sends_limit_not_mode(self):
        co, client = self.setup_water()
        entity = number_module.FlowLimit(co)
        self.assertTrue(entity.available)
        await entity.async_set_native_value(45)
        client.command.assert_awaited_once_with("max_flow", 45)
        client.set_panel_mode.assert_not_awaited()
        self.assertEqual(co.data.values["mode"], "off")
