"""Offline protocol/transport/control tests. No real network or HA instance."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from loader import client as c

MAC = "00:11:22:33:44:55"
plain = MAC.replace(":", "") + " " + "0123456789ab"
HELLO = ("#D" + "".join(c.ENCODED[(c.PLAIN.index(v) + 2) % 63] for v in plain)).encode()


def packet(kind, register, value=0):
    hb, lb = (value >> 8) & 255, value & 255
    body = bytes([(kind << 4) | (((kind.bit_count() + register.bit_count() + hb.bit_count() + lb.bit_count()) % 2) << 7), register, hb, lb])
    return body + c.crc(body).to_bytes(2, "big")


class Writer:
    def __init__(self):
        self.frames = []
        self.closed = False

    def write(self, value):
        self.frames.append(value)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def transport(payload):
    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()
    return reader, Writer()


def guard(active=1, mode=0):
    return packet(4, 0, mode << 8) + packet(4, 89, active) + packet(4, 89, 0x0100)


class ProtocolTests(unittest.TestCase):
    def test_known_frame(self):
        self.assertEqual(c._frame(0, 25).hex(), "80190000045b")

    def test_units_and_flags(self):
        self.assertEqual(c.decode(packet(4, 25, 0x1680), 25)["heating_water"], 22.5)
        self.assertEqual(c.decode(packet(4, 28, 0x1680), 28)["return_water"], 22)
        x = c.decode(packet(4, 89, 64), 89)
        self.assertFalse(x["dominus_active"])
        self.assertTrue(x["thermostat_input"])
        x = c.decode(packet(4, 0, 0x0308), 0)
        self.assertTrue(x["flame"])
        self.assertTrue(x["dhw_enabled"])

    def test_invalid_and_unsupported(self):
        self.assertEqual(c.decode(packet(7, 28), 28), {})
        self.assertEqual(c.decode(packet(4, 17, 0xFF00), 17), {})
        for b in (packet(4, 25)[:5], packet(5, 25), packet(4, 24)):
            with self.assertRaises(c.DominusError):
                c.decode(b, 25)
        bad = bytearray(packet(4, 25)); bad[5] ^= 1
        with self.assertRaises(c.DominusError):
            c.decode(bytes(bad), 25)
        with self.assertRaises(c.DominusError):
            c.decode(packet(4, 89, 0x1032), 89, 17)

    def test_identity_not_logged(self):
        device = c.DominusClient("192.168.100.2", MAC)
        device._identity(HELLO)
        with self.assertRaises(c.DominusError) as error:
            c.DominusClient("192.168.100.2", MAC, password="fixture-password")._identity(HELLO)
        self.assertNotIn("fixture-password", str(error.exception))
        self.assertNotIn(HELLO.decode(), str(error.exception))


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    def device(self, *, owned=False, **kwargs):
        device = c.DominusClient("192.168.100.2", MAC, keepalive_interval=None, **kwargs)
        device._owns_lease = owned  # Simulate an already commissioned, open-session owner.
        return device

    async def test_probe_read_only(self):
        channel = transport(HELLO + packet(4, 25, 0x1680))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            await self.device().probe()
        self.assertEqual(channel[1].frames, [c._frame(0, 25)])
        self.assertTrue(channel[1].closed)

    async def test_persistent_readonly_session_and_heartbeat_do_not_take_control(self):
        channel = transport(HELLO + packet(4, 25, 0x1680) + packet(4, 89, 0) + packet(4, 25, 0x1680))
        device = self.device(persistent_readonly=True)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            await device.probe()
            self.assertFalse(channel[1].closed)
            self.assertTrue(await device._heartbeat_once())
            self.assertFalse(device.owns_control)
            await device.probe()
            self.assertEqual(connect.await_count, 1)
            await device.close()
        self.assertTrue(all((frame[0] & 0x70) == 0 for frame in channel[1].frames))
        self.assertTrue(channel[1].closed)

    async def test_cooldown_between_readonly_clients(self):
        channels = [transport(HELLO + packet(4, 25, 0x1680)) for _ in range(2)]
        with patch.object(c.asyncio, "open_connection", AsyncMock(side_effect=channels)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()) as sleep:
            await self.device().probe()
            sleep.reset_mock()
            await self.device().probe()
            self.assertTrue(any(call.args[0] >= .9 for call in sleep.await_args_list))
            self.assertEqual(connect.await_count, 2)
        self.assertTrue(all(channel[1].closed for channel in channels))

    async def test_transport_error_reports_register_and_type_without_retry(self):
        channel = transport(HELLO)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaisesRegex(c.DominusError, "read ID25/HB0.*IncompleteReadError"):
                await self.device().probe()
        self.assertEqual(connect.await_count, 1)
        self.assertEqual(channel[1].frames, [c._frame(0, 25)])
        self.assertTrue(channel[1].closed)

    async def test_snapshot(self):
        values = {(0, 0): 0, (89, 0): 0, (89, 1): 0x0100, (25, 0): 0x1680,
                  (28, 0): 0x1600, (26, 0): 0x2200, (56, 0): 0x0A00, (1, 0): 0,
                  (89, 17): 0x1128, (17, 0): 0, (24, 0): 0x1700, (16, 0): 0x0500,
                  (49, 0): 0x5514, (48, 0): 0x3C0A, (57, 0): 0x2D00}
        channel = transport(HELLO + b''.join(packet(4, reg, values[reg, sel]) for reg, sel in c.READS))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            snapshot = await self.device().read_snapshot()
        self.assertEqual(snapshot.values["max_flow"], 40)
        self.assertEqual(snapshot.values["dhw_target"], 10)
        self.assertEqual(snapshot.values["room_target"], 5)
        self.assertTrue(snapshot.observed["heating_water"].tzinfo)
        self.assertEqual(len(channel[1].frames), 15)
        self.assertTrue(all((b[0] & 0x70) == 0 for b in channel[1].frames))
        self.assertTrue(channel[1].closed)

    async def test_snapshot_reconnects_once_without_writes_or_lease_adoption(self):
        # First connection fails mid-poll; discard its partial data completely.
        failed = transport(HELLO + packet(4, 0, 0x0300))
        values = {(89, 1): 0x0100, (89, 17): 0x1128,
                  (49, 0): 0x5514, (48, 0): 0x3C0A}
        recovered = transport(HELLO + b''.join(
            packet(4, reg, values.get((reg, sel), 0)) for reg, sel in c.READS))
        device = self.device(persistent_readonly=True)
        # Simulate transport loss while we previously owned this connection.
        device._channel = [*failed, 0.0]
        await failed[0].readexactly(27)
        device._owns_lease = True
        lost = []
        device.on_connection_lost = lambda: lost.append(True)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=recovered)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            snapshot = await device.read_snapshot()
            self.assertEqual(connect.await_count, 1)
            self.assertEqual(snapshot.values["mode"], "off")
            self.assertFalse(device.owns_control)
            self.assertEqual(lost, [True])
            await device.close()
        self.assertTrue(failed[1].closed)
        self.assertTrue(all((f[0] & 0x70) == 0 for ch in (failed, recovered) for f in ch[1].frames))

    async def test_snapshot_retries_are_bounded(self):
        channels = [transport(HELLO) for _ in range(2)]
        with patch.object(c.asyncio, "open_connection", AsyncMock(side_effect=channels)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaisesRegex(c.DominusError, "after fresh reconnect"):
                await self.device().read_snapshot()
            self.assertEqual(connect.await_count, 2)
        self.assertTrue(all(ch[1].closed for ch in channels))

    async def test_snapshot_cancel_does_not_retry(self):
        device = self.device()
        with patch.object(device, "_read_snapshot_once", AsyncMock(side_effect=asyncio.CancelledError)) as poll:
            with self.assertRaises(asyncio.CancelledError):
                await device.read_snapshot()
            self.assertEqual(poll.await_count, 1)

    async def test_permissions_before_connect(self):
        with patch.object(c.asyncio, "open_connection", AsyncMock()) as connect:
            with self.assertRaises(c.ControlError):
                await self.device().command("take")
            with self.assertRaises(c.ControlError):
                await self.device(allow_controls=True).command("winter")
            for action in ("summer", "antifreeze", "dhw", "room_target", "reset", "parameter_write"):
                with self.assertRaises(c.ControlError):
                    await self.device(allow_controls=True).command(action)
            for value in (True, 19, 86, 40.5):
                with self.assertRaises(c.ControlError):
                    await self.device(allow_controls=True).command("max_flow", value)
            connect.assert_not_called()

    async def test_antifreeze_blocked_even_with_permissions(self):
        with patch.object(c.asyncio, "open_connection", AsyncMock()) as connect:
            with self.assertRaisesRegex(c.ControlError, "not commissioned"):
                await self.device(allow_controls=True, allow_gas_dhw=True).command("antifreeze")
            connect.assert_not_called()

    async def test_no_implicit_takeover(self):
        channel = transport(HELLO + guard(0))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaises(c.ControlError):
                await self.device(allow_controls=True, allow_gas_dhw=True).command("winter")
        self.assertTrue(all((b[0] & 0x70) == 0 for b in channel[1].frames))

    async def test_modes_and_explicit_ownership(self):
        cases = (("take", 0, (89, 0, 1), packet(4, 89, 1) + packet(4, 0)),
                 ("release", 1, (89, 0, 0), packet(4, 89)),
                 ("off", 1, (0, 0, 0), packet(4, 0)),
                 ("winter", 1, (0, 3, 0), packet(4, 0, 0x0300)),
                 ("summer", 1, (0, 2, 0), packet(4, 0, 0x0200)))
        for action, active, target, readback in cases:
            with self.subTest(action=action):
                register, hb, lb = target
                channel = transport(HELLO + guard(active) + packet(5, register, hb * 256 + lb) + readback)
                with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
                     patch.object(c.asyncio, "sleep", AsyncMock()):
                    device = self.device(owned=bool(active), allow_controls=True, allow_gas_dhw=True)
                    result = await device.command(action)
                    if action == "summer":
                        self.assertFalse(result.values["heating_enabled"])
                        self.assertTrue(result.values["dhw_enabled"])
                    await device.close()
                self.assertEqual([b for b in channel[1].frames if b[0] & 0x10], [c._frame(1, *target)])
                self.assertTrue(channel[1].closed)

    async def test_owned_session_reused_between_operations(self):
        channel = transport(HELLO + guard(0) + packet(5, 89, 1) + packet(4, 89, 1)
                            + packet(4, 0) + packet(4, 25, 0x1680))
        device = self.device(allow_controls=True)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            await device.command("take")
            self.assertFalse(channel[1].closed)
            await device.probe()
            self.assertEqual(connect.await_count, 1)
            await device.close()
        self.assertTrue(channel[1].closed)
        self.assertFalse(device._owns_lease)

    async def test_keepalive_loss_reads_only_and_does_not_retake(self):
        channel = transport(packet(4, 89, 0))
        device = self.device(owned=True, allow_controls=True)
        device._channel = [*channel, 0.0]
        callback = []
        device.on_connection_lost = lambda: callback.append(True)
        with patch.object(c.asyncio, "open_connection", AsyncMock()) as connect:
            self.assertFalse(await device._heartbeat_once())
            connect.assert_not_called()
        self.assertEqual(channel[1].frames, [c._frame(0, 89, 0)])
        self.assertEqual(callback, [True])
        self.assertTrue(channel[1].closed)
        self.assertFalse(device._owns_lease)

    async def test_cannot_steal_an_existing_foreign_lease(self):
        channel = transport(HELLO + guard(1))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaises(c.ControlError):
                await self.device(allow_controls=True).command("take")
        self.assertTrue(all((b[0] & 0x70) == 0 for b in channel[1].frames))
        self.assertTrue(channel[1].closed)

    async def test_flow_write_readback(self):
        channel = transport(HELLO + guard() + packet(4, 49, 0x5514)
                            + packet(5, 89, 0x112D) + packet(4, 89, 0x112D))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            device = self.device(owned=True, allow_controls=True)
            confirmed = await device.command("max_flow", 45)
            self.assertEqual(confirmed.values["max_flow"], 45)
            self.assertTrue(confirmed.values["dominus_active"])
            self.assertNotIn("heating_water", confirmed.observed)
            self.assertTrue(all(t.tzinfo for t in confirmed.observed.values()))
            await device.close()
        writes = [b for b in channel[1].frames if b[0] & 0x10]
        self.assertEqual(writes, [c._frame(1, 89, 17, 45)])
        self.assertEqual(channel[1].frames[-1], c._frame(0, 89, 17))

    async def test_dhw_setter_and_uncertain_readback_without_retry(self):
        for actual in (45, 10):
            channel = transport(HELLO + guard(mode=2) + packet(4, 48, 0x3C0A)
                                + packet(5, 56, 45 << 8) + packet(4, 56, actual << 8))
            with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
                 patch.object(c.asyncio, "sleep", AsyncMock()):
                device = self.device(owned=True, allow_controls=True, allow_gas_dhw=True)
                if actual == 45:
                    await device.command("dhw_target", 45)
                else:
                    with self.assertRaises(c.WriteUncertain):
                        await device.command("dhw_target", 45)
                await device.close()
            self.assertEqual([b for b in channel[1].frames if b[0] & 0x10], [c._frame(1, 56, 45, 0)])

    async def test_dhw_guards_and_panel_permissions_do_not_write(self):
        with patch.object(c.asyncio, "open_connection", AsyncMock()) as connect:
            for value in (True, 9, 61, 40.5, float("nan")):
                with self.assertRaises(c.ControlError):
                    await self.device(allow_controls=True, allow_gas_dhw=True).command("dhw_target", value)
            with self.assertRaises(c.ControlError):
                await self.device(allow_controls=True).set_panel_mode("winter")
            with self.assertRaises(c.ControlError):
                await self.device(allow_controls=True, allow_gas_dhw=True).set_panel_mode("antifreeze")
            connect.assert_not_called()
        for active, mode, bounds in ((0, 2, 0x3C0A), (1, 0, 0x3C0A), (1, 2, 0x2814)):
            channel = transport(HELLO + guard(active, mode) + packet(4, 48, bounds))
            with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
                 patch.object(c.asyncio, "sleep", AsyncMock()):
                device = self.device(owned=bool(active), allow_controls=True, allow_gas_dhw=True)
                with self.assertRaises(c.ControlError):
                    await device.command("dhw_target", 45)
                await device.close()
            self.assertTrue(all((b[0] & 0x70) == 0 for b in channel[1].frames))

    async def test_panel_winter_explicitly_takes_then_car_stops_before_release(self):
        channel = transport(HELLO + guard(0) + packet(5, 89, 1) + packet(4, 89, 1) + packet(4, 0)
                            + guard() + packet(5, 0, 0x0300) + packet(4, 0, 0x0300)
                            + guard(mode=3) + packet(5, 0) + packet(4, 0)
                            + guard() + packet(5, 89) + packet(4, 89))
        device = self.device(allow_controls=True, allow_gas_dhw=True)
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            confirmed = await device.set_panel_mode("winter")
            self.assertEqual(confirmed.values["mode"], "winter")
            self.assertTrue(confirmed.values["dominus_active"])
            self.assertTrue(device.owns_control)
            confirmed = await device.set_panel_mode("local")
            self.assertEqual(confirmed.values["mode"], "off")
            self.assertFalse(confirmed.values["dominus_active"])
            self.assertFalse(device.owns_control)
            self.assertEqual(connect.await_count, 1)
            await device.close()
        self.assertEqual([b for b in channel[1].frames if b[0] & 0x10],
                         [c._frame(1, 89, 0, 1), c._frame(1, 0, 3), c._frame(1, 0), c._frame(1, 89)])

    async def test_room_target_write_requires_native_room_control(self):
        state = packet(4, 0, 0x0300) + packet(4, 89, 1) + packet(4, 89, 0x0100)
        native = packet(4, 89, 0x0701) + packet(4, 89, 0x0901)
        channel = transport(HELLO + state + native + packet(5, 16, 0x1780) + packet(4, 16, 0x1780))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            device = self.device(owned=True, allow_controls=True)
            await device.command("room_target", 23.5)
            await device.close()
        self.assertEqual([b for b in channel[1].frames if b[0] & 0x10], [c._frame(1, 16, 23, 128)])
        self.assertEqual(channel[1].frames[-1], c._frame(0, 16))

    async def test_room_target_blocks_off_and_disabled_native_sensor(self):
        for mode, modulation, probe in ((0, 1, 1), (3, 0, 1), (3, 1, 0)):
            state = packet(4, 0, mode << 8) + packet(4, 89, 1) + packet(4, 89, 0x0100)
            channel = transport(HELLO + state + packet(4, 89, 0x0700 | modulation)
                                + packet(4, 89, 0x0900 | probe))
            with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
                 patch.object(c.asyncio, "sleep", AsyncMock()):
                device = self.device(owned=True, allow_controls=True)
                with self.assertRaises(c.ControlError):
                    await device.command("room_target", 23)
                await device.close()
            self.assertFalse(any(b[0] & 0x10 for b in channel[1].frames))

    async def test_compensation_does_not_enter_winter_with_disabled_native_probe(self):
        channel = transport(HELLO + guard() + packet(4, 89, 0x0701) + packet(4, 89, 0x0900))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            device = self.device(owned=True, allow_controls=True, allow_gas_dhw=True, require_native_room=True)
            with self.assertRaises(c.ControlError):
                await device.command("winter")
            await device.close()
        self.assertFalse(any(b[0] & 0x10 for b in channel[1].frames))

    async def test_invalid_room_target_has_no_network_io(self):
        with patch.object(c.asyncio, "open_connection", AsyncMock()) as connect:
            for value in (True, None, 4, 36, float("nan"), float("inf")):
                with self.assertRaises(c.ControlError):
                    await self.device(allow_controls=True).command("room_target", value)
            connect.assert_not_called()

    async def test_device_bounds_checked(self):
        channel = transport(HELLO + guard() + packet(4, 49, 0x5519))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)), \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            device = self.device(owned=True, allow_controls=True)
            with self.assertRaises(c.ControlError):
                await device.command("max_flow", 20)
            await device.close()
        self.assertTrue(all((b[0] & 0x70) == 0 for b in channel[1].frames))

    async def test_uncertain_write_no_retry(self):
        channel = transport(HELLO + guard() + packet(4, 49, 0x5514) + packet(5, 89, 0x112D))
        with patch.object(c.asyncio, "open_connection", AsyncMock(return_value=channel)) as connect, \
             patch.object(c.asyncio, "sleep", AsyncMock()):
            with self.assertRaises(c.WriteUncertain):
                await self.device(owned=True, allow_controls=True).command("max_flow", 45)
        self.assertEqual(sum(bool(b[0] & 0x10) for b in channel[1].frames), 1)
        self.assertEqual(connect.await_count, 1)
        self.assertTrue(channel[1].closed)


if __name__ == "__main__":
    unittest.main()
