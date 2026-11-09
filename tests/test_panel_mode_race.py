"""Panel actions must decide ownership after any pending read-only poll."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from loader import client as c
from test_client import HELLO, MAC, Writer, guard, packet, transport


class PanelModeRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_poll_loss_precedes_takeover_decision(self):
        device = c.DominusClient("192.168.100.2", MAC, allow_controls=True,
                                allow_gas_dhw=True, keepalive_interval=None)
        device._channel = [asyncio.StreamReader(), Writer(), 0.0]
        device._owns_lease = True
        channel = transport(HELLO + guard(0) + packet(5, 89, 1)
                            + packet(4, 89, 1) + packet(4, 0)
                            + guard() + packet(5, 0, 0x0300)
                            + packet(4, 0, 0x0300))
        # Hold exactly the lock a polling read holds while its timeout fires.
        await device._lock.acquire()
        task = asyncio.create_task(device.set_panel_mode("winter"))
        try:
            await asyncio.sleep(0)
            await device._drop_connection()
            with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
                 patch.object(c.asyncio, "sleep", AsyncMock()):
                device._lock.release()
                result = await task
                self.assertEqual(result.values["mode"], "winter")
                await device.close()
        finally:
            if device._lock.locked():
                device._lock.release()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual([f for f in channel[1].frames if f[0] & 0x10],
                         [c._frame(1, 89, 0, 1), c._frame(1, 0, 3)])

    async def test_foreign_lease_after_poll_loss_is_not_stolen(self):
        device = c.DominusClient("192.168.100.2", MAC, allow_controls=True,
                                allow_gas_dhw=True, keepalive_interval=None)
        channel = transport(HELLO + guard(1))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaises(c.ControlError):
                await device.set_panel_mode("winter")
            await device.close()
        self.assertTrue(all(not f[0] & 0x10 for f in channel[1].frames))
