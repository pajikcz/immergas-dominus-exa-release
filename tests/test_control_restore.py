"""Saved-intent recovery using HA stubs; no device or HA runtime contacted."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import test_compensation_coordinator as fixtures
from test_compensation_coordinator import FakeClient, module, c, stub_exception, setup_module


class RestoreClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.values.update(dominus_active=False, control_timer=0, max_flow=45, dhw_target=40)

    async def read_snapshot(self):
        values = {**self.values, "dominus_active": self.values["dominus_active"] or self.owns_control}
        return c.Snapshot(values, dict.fromkeys(values, datetime.now(timezone.utc)))

    async def command(self, action, value=None):
        if action == "take":
            if self.values["mode"] != "off" or self.values["dominus_active"]:
                raise c.ControlError("Fixture: unsafe takeover")
        if action in {"dhw_target", "max_flow"}:
            self.commands.append((action, value))
            self.values[action] = value
            return await self.read_snapshot()
        result = await super().command(action, value)
        self.values["dominus_active"] = self.owns_control
        return result

    async def set_panel_mode(self, mode):
        if mode == "local":
            await self.command("off")
            return await self.command("release")
        if not self.owns_control:
            await self.command("take")
        return await self.command(mode)

    def disconnect(self):
        self.owns_control = False
        self.values.update(dominus_active=False, mode="off")
        self.on_connection_lost()


class ControlRestoreTests(unittest.IsolatedAsyncioTestCase):
    def make(self, saved=None, live=False):
        old, _ = fixtures.CoordinatorTests().setup_coordinator(live=live)
        if saved is not None:
            old.entry.options["restore_control"] = saved
        old.entry.options["room_temperature_source_mode"] = "car"
        client = RestoreClient()
        return module.DominusCoordinator(old.hass, old.entry, client), client

    async def settle(self, coordinator):
        if coordinator._command_refresh_task:
            await coordinator._command_refresh_task

    async def test_absent_intent_never_takes_over(self):
        coordinator, client = self.make()
        await coordinator._async_update_data()
        client.disconnect()
        await coordinator._async_update_data()
        self.assertEqual(client.commands, [])

    async def test_user_selection_survives_loss_restores_once_and_preserves_targets(self):
        coordinator, client = self.make(live=True)
        coordinator.data = await coordinator._async_update_data()
        await coordinator.command("panel_mode", "winter")
        await self.settle(coordinator)
        self.assertEqual(coordinator.restore_choice["mode"], "winter")
        client.disconnect()
        client.values.update(max_flow=30, dhw_target=10, room_target=5)
        client.commands.clear()
        snapshot = await coordinator._async_update_data()
        self.assertEqual(client.commands, [("take", None), ("max_flow", 45),
                                         ("winter", None), ("dhw_target", 40), ("room_target", 21)])
        self.assertEqual(snapshot.values["mode"], "winter")
        self.assertEqual(snapshot.values["room_target"], 21)
        self.assertTrue(coordinator._writes_armed)
        self.assertEqual(coordinator.restore_status, "restored")
        before = list(client.commands)
        await coordinator._async_update_data()
        self.assertEqual(client.commands, before)

    async def test_saved_modes_restore_after_new_coordinator_including_off(self):
        for mode in ("off", "summer", "winter"):
            coordinator, client = self.make({"owner": "dominus", "mode": mode})
            result = await coordinator._async_update_data()
            self.assertEqual(client.commands, [("take", None)] + ([] if mode == "off" else [(mode, None)]))
            self.assertEqual(result.values["mode"], mode)
            self.assertEqual(coordinator.restore_status, "restored")

    async def test_read_failure_delays_recovery_then_successful_poll_restores(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        original = client.read_snapshot
        client.read_snapshot = AsyncMock(side_effect=c.DominusError("Fixture timeout"))
        with self.assertRaises(module.UpdateFailed):
            await coordinator._async_update_data()
        self.assertEqual(client.commands, [])
        client.read_snapshot = original
        await coordinator._async_update_data()
        self.assertEqual(client.commands, [("take", None), ("winter", None)])

    async def test_manual_car_cancels_even_when_release_fails_and_after_restart(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        client.set_panel_mode = AsyncMock(side_effect=c.DominusError("Fixture offline"))
        with self.assertRaises(stub_exception.HomeAssistantError):
            await coordinator.command("panel_mode", "local")
        await self.settle(coordinator)
        self.assertEqual(coordinator.restore_choice, {"owner": "local"})
        await coordinator._async_update_data()
        self.assertEqual(client.commands, [])
        restarted = module.DominusCoordinator(coordinator.hass, coordinator.entry, client)
        await restarted._async_update_data()
        self.assertEqual(client.commands, [])

    async def test_fresh_guards_block_without_changing_saved_request(self):
        for change, expected in (({"dominus_active": True}, "foreign_or_unknown_owner"),
                                 ({"control_timer": 1}, "timer_active_or_unknown"),
                                 ({"mode": "winter"}, "local_active_mode")):
            saved = {"owner": "dominus", "mode": "winter"}
            coordinator, client = self.make(saved)
            client.values.update(change)
            await coordinator._async_update_data()
            self.assertEqual(client.commands, [])
            self.assertEqual(coordinator.restore_choice, saved)
            self.assertEqual(coordinator.restore_status, expected)

    async def test_permissions_invalid_source_and_parallel_action_delay_restore(self):
        for reason in ("controls", "gas", "source", "parallel"):
            coordinator, client = self.make({"owner": "dominus", "mode": "winter"}, live=True)
            if reason == "controls":
                client.allow_controls = False
            elif reason == "gas":
                client.allow_gas_dhw = False
            elif reason == "source":
                client.values["room_temperature"] = float("nan")
            else:
                coordinator.command_in_progress = "local"
            await coordinator._async_update_data()
            self.assertEqual(client.commands, [], reason)

    async def test_uncertain_recovery_is_latched_across_polls_and_restart(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        original = client.command
        async def uncertain_mode(action, value=None):
            if action == "winter":
                raise c.WriteUncertain("Fixture uncertain mode")
            return await original(action, value)
        client.command = AsyncMock(side_effect=uncertain_mode)
        with self.assertRaises(module.UpdateFailed):
            await coordinator._async_update_data()
        self.assertTrue(coordinator.restore_choice["blocked"])
        count = client.command.await_count
        await coordinator._async_update_data()
        restarted = module.DominusCoordinator(coordinator.hass, coordinator.entry, client)
        await restarted._async_update_data()
        self.assertEqual(client.command.await_count, count)
        self.assertEqual(restarted.restore_status, "blocked_uncertain_write")

    async def test_recovery_does_not_apply_pending_off_dhw(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "summer", "dhw_target": 40})
        coordinator.entry.options["pending_dhw_target"] = 55
        await coordinator._async_update_data()
        self.assertEqual(coordinator.pending_dhw_target, 55)
        self.assertNotIn(("dhw_target", 55), client.commands)

    async def test_local_or_failed_first_take_does_not_create_ha_intent(self):
        coordinator, client = self.make()
        client.command = AsyncMock(side_effect=c.DominusError("Fixture failed take"))
        with self.assertRaises(stub_exception.HomeAssistantError):
            await coordinator.command("take")
        await self.settle(coordinator)
        self.assertEqual(coordinator.restore_choice, {})

    async def test_runtime_intent_does_not_reload_entry(self):
        coordinator, client = self.make()
        coordinator.entry.runtime_data = coordinator
        coordinator.entry.entry_id = "fixture"
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_reload=AsyncMock()))
        await coordinator.command("take")
        await self.settle(coordinator)
        await setup_module._reload(hass, coordinator.entry)
        hass.config_entries.async_reload.assert_not_awaited()

    async def test_manual_off_supersedes_winter_for_next_recovery(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        await coordinator._async_update_data()
        await coordinator.command("off")
        await self.settle(coordinator)
        self.assertEqual(coordinator.restore_choice["mode"], "off")
        client.disconnect()
        client.commands.clear()
        result = await coordinator._async_update_data()
        self.assertEqual(client.commands, [("take", None)])
        self.assertEqual(result.values["mode"], "off")

    async def test_confirmed_water_edits_are_saved_but_off_pending_is_not(self):
        coordinator, client = self.make()
        coordinator.data = await coordinator._async_update_data()
        await coordinator.command("panel_mode", "summer")
        await self.settle(coordinator)
        await coordinator.command("max_flow", 50)
        await coordinator.command("dhw_target", 42)
        await self.settle(coordinator)
        self.assertEqual(coordinator.restore_choice["max_flow"], 50)
        self.assertEqual(coordinator.restore_choice["dhw_target"], 42)
        await coordinator.command("off")
        await self.settle(coordinator)
        coordinator.data.values.update(dhw_min=10, dhw_max=60)
        await coordinator.set_dhw_target(55)
        self.assertEqual(coordinator.pending_dhw_target, 55)
        self.assertEqual(coordinator.restore_choice["dhw_target"], 42)

    async def test_final_readback_mismatch_is_not_reported_as_restored(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        original = client.command
        async def ack_without_mode_change(action, value=None):
            if action == "winter":
                return await client.read_snapshot()
            return await original(action, value)
        client.command = ack_without_mode_change
        with self.assertRaises(module.UpdateFailed):
            await coordinator._async_update_data()
        self.assertFalse(coordinator._writes_armed)
        self.assertTrue(coordinator._restore_pending)
        self.assertNotEqual(coordinator.restore_status, "restored")

    async def test_invalid_saved_targets_do_not_trigger_takeover(self):
        for target in (-1, float("nan"), True, "45"):
            coordinator, client = self.make({"owner": "dominus", "mode": "winter", "max_flow": target})
            await coordinator._async_update_data()
            self.assertEqual(client.commands, [])
            self.assertEqual(coordinator.restore_status, "invalid_saved_target")

    async def test_restore_cancellation_is_latched_and_clears_busy_state(self):
        coordinator, client = self.make({"owner": "dominus", "mode": "winter"})
        gate = asyncio.Event()
        async def wait(*args):
            await gate.wait()
        client.command = AsyncMock(side_effect=wait)
        task = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(coordinator.command_in_progress)
        self.assertTrue(coordinator.restore_choice["blocked"])


if __name__ == "__main__":
    unittest.main()
