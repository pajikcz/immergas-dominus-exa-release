"""Accepted OFF must cancel old ON recovery before device I/O; no hardware."""
import asyncio
import unittest
from unittest.mock import AsyncMock
import test_control_restore as fixtures

class StopIntentTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        co, client = fixtures.ControlRestoreTests().make({"owner": "dominus", "mode": "winter"})
        client.owns_control = True
        client.values.update(mode="winter", dominus_active=True)
        return co, client

    async def test_off_failure_cancels_winter_even_after_restart(self):
        for action, value in [("off", None), ("panel_mode", "off")]:
            with self.subTest(action=action):
                co, client = self.make()
                co.data = await client.read_snapshot()
                call = "command" if action == "off" else "set_panel_mode"
                setattr(client, call, AsyncMock(side_effect=fixtures.c.DominusError("Offline before write")))
                with self.assertRaises(fixtures.stub_exception.HomeAssistantError):
                    await co.command(action, value)
                await fixtures.ControlRestoreTests().settle(co)
                self.assertTrue(co.restore_choice["blocked"])
                self.assertTrue(co.restore_choice["stop_requested"])
                self.assertEqual(co.restore_choice["mode"], "winter")  # Still not confirmed OFF.
                self.assertEqual(co.data.values["mode"], "winter")
                restarted_client = fixtures.RestoreClient()
                restarted = fixtures.module.DominusCoordinator(co.hass, co.entry, restarted_client)
                await restarted._async_update_data()
                self.assertEqual(restarted_client.commands, [])
                self.assertEqual(restarted.restore_status, "blocked_stop_requested")

    async def test_confirmed_off_clears_latch_and_remembers_off(self):
        for action, value in [("off", None), ("panel_mode", "off")]:
            co, client = self.make()
            await co.command(action, value)
            await fixtures.ControlRestoreTests().settle(co)
            self.assertEqual(co.restore_choice["mode"], "off")
            self.assertNotIn("blocked", co.restore_choice)
            self.assertNotIn("stop_requested", co.restore_choice)

    async def test_interrupted_off_keeps_cancellation(self):
        co, client = self.make()
        client.command = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await co.command("off")
        self.assertTrue(co.restore_choice["blocked"])
        self.assertTrue(co.restore_choice["stop_requested"])
        self.assertIsNone(co.command_in_progress)

    async def test_rejected_busy_request_is_not_accepted(self):
        co, _ = self.make()
        co.command_in_progress = "restore"
        with self.assertRaises(fixtures.stub_exception.HomeAssistantError):
            await co.command("off")
        self.assertNotIn("stop_requested", co.restore_choice)
