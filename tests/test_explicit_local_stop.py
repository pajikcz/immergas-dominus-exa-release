"""Deliberate OFF from local control; offline protocol and coordinator fixtures."""
import unittest
from unittest.mock import AsyncMock, patch
from test_client import c, MAC, HELLO, packet, transport, guard
import test_control_restore as restore

class LocalOffProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, payload, authorize=lambda: True):
        device = c.DominusClient("192.168.100.2", MAC, allow_controls=True, keepalive_interval=None)
        channel = transport(HELLO + payload)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)):
            try:
                result = await device.command("take_off", authorize)
                return result, channel[1]
            finally:
                await device._drop_connection()

    async def test_local_modes_take_then_off_with_independent_readbacks(self):
        for mode in (0, 2, 3):
            with self.subTest(mode=mode):
                result, writer = await self.execute(guard(0, mode) + packet(1, 89)
                    + packet(4, 89, 1) + packet(1, 0) + packet(4, 0) + packet(4, 0) + packet(4, 89, 1))
                self.assertEqual(result.values["mode"], "off")
                self.assertTrue(result.values["dominus_active"])
                writes = [x for x in writer.frames if len(x) == 6 and (x[0] >> 4) & 7 == 1]
                self.assertEqual(writes, [c._frame(1, 89, 0, 1), c._frame(1, 0, 0, 0)])

    async def test_foreign_timer_unknown_mode_and_stale_authorization_never_write(self):
        cases = [(guard(1, 2), lambda: True), (guard(0, 6), lambda: True),
                 (guard(0, 2), lambda: False), (guard(0, 2), None),
                 (packet(4, 0, 0x200) + packet(4, 89) + packet(4, 89, 0x101), lambda: True)]
        for payload, authorize in cases:
            channel = transport(HELLO + payload)
            device = c.DominusClient("192.168.100.2", MAC, allow_controls=True, keepalive_interval=None)
            with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)):
                with self.assertRaises(c.ControlError):
                    await device.command("take_off", authorize)
            self.assertFalse(any(len(x) == 6 and (x[0] >> 4) & 7 == 1 for x in channel[1].frames))

    async def test_uncertain_ack_or_readback_never_succeeds(self):
        suffixes = [packet(1, 89) + packet(4, 89),
                    packet(1, 89) + packet(4, 89, 1) + packet(1, 0) + packet(4, 0, 0x200),
                    packet(1, 89) + packet(4, 89, 1) + packet(1, 0) + packet(4, 0) + packet(4, 0) + packet(4, 89)]
        for suffix in suffixes:
            with self.assertRaises(c.WriteUncertain):
                await self.execute(guard(0, 2) + suffix)

    async def test_revoked_request_does_not_issue_second_write(self):
        checks = iter([True, True, False])  # Preflight, acquire, revoked before OFF.
        with self.assertRaises(c.WriteUncertain):
            await self.execute(guard(0, 2) + packet(1, 89) + packet(4, 89, 1), lambda: next(checks))

class LocalStopClient(restore.RestoreClient):
    async def command(self, action, value=None):
        if action == "take_off":
            if not value() or self.values["dominus_active"] or self.values["control_timer"]:
                raise c.ControlError("Fixture: rejected local shutdown")
            self.commands.append((action, None))
            self.owns_control = True
            self.values.update(mode="off", dominus_active=True)
            return await self.read_snapshot()
        return await super().command(action, value)

class ExplicitStopTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        old, _ = restore.ControlRestoreTests().make({"owner": "local"})
        client = LocalStopClient()
        client.values.update(mode="summer", dominus_active=False)
        return restore.module.DominusCoordinator(old.hass, old.entry, client), client

    async def test_only_explicit_off_stops_local_summer(self):
        for action, value in [("off", None), ("panel_mode", "off")]:
            co, client = self.make()
            await co.command(action, value)
            await restore.ControlRestoreTests().settle(co)
            self.assertEqual(client.commands, [("take_off", None)])
            self.assertEqual(co.restore_choice["mode"], "off")
            self.assertIsNone(co.command_in_progress)

    async def test_initialization_and_reconnection_never_stop_local_summer(self):
        co, client = self.make()
        await co._async_update_data()
        client.disconnect()
        client.values.update(mode="summer", dominus_active=False)
        await co._async_update_data()
        self.assertEqual(client.commands, [])

    async def test_failed_explicit_stop_still_cancels_old_winter(self):
        co, client = self.make()
        co._save_restore_choice({"owner": "dominus", "mode": "winter"})
        client.command = AsyncMock(side_effect=c.ControlError("Fixture: rejected"))
        with self.assertRaises(restore.stub_exception.HomeAssistantError):
            await co.command("panel_mode", "off")
        await restore.ControlRestoreTests().settle(co)
        self.assertTrue(co.restore_choice["blocked"])
        self.assertTrue(co.restore_choice["stop_requested"])
