"""Async EXA protocol client. No writes on connect, polling or disconnect."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import logging
import math
import re

PLAIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 "
ENCODED = "0SFGLcTdjaxZPyeK9QhptB5v7zJH3Mq1VibDfCAN6EgYRwXlo8Wk4mun2rOsUI="
READS = ((0, 0), (89, 0), (89, 1), (25, 0), (28, 0), (26, 0), (56, 0),
         (1, 0), (89, 17), (17, 0), (24, 0), (16, 0), (49, 0), (48, 0), (57, 0))
NATIVE_ROOM_READS = ((89, 7), (89, 9))
_LOGGER = logging.getLogger(__name__)


class DominusError(Exception):
    """Sanitized communication failure."""


class ControlError(DominusError):
    """A command is not permitted in the current state."""


class WriteUncertain(DominusError):
    """A write may have taken effect; never retry it automatically."""


def normalize_mac(value):
    if not re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", value):
        raise ValueError("Use six colon-separated MAC octets")
    return value.replace(":", "").lower()


def crc(data):
    result = 0xFFFF
    for byte in data:
        for _ in range(8):
            result = (result >> 1) ^ (0x1021 if (result ^ byte) & 1 else 0)
            byte >>= 1
    return result


def _frame(write, register, hb=0, lb=0):
    parity = (write + register.bit_count() + hb.bit_count() + lb.bit_count()) % 2
    body = bytes([(write << 4) | (parity << 7), register, hb, lb])
    return body + crc(body).to_bytes(2, "big")


def decode(reply, register, selector=0):
    if len(reply) != 6 or reply[1] != register or reply[0] & 15:
        raise DominusError("Invalid response header")
    if crc(reply[:4]) != int.from_bytes(reply[4:], "big"):
        raise DominusError("Invalid response CRC")
    if sum(b.bit_count() for b in reply[:4]) % 2:
        raise DominusError("Invalid response parity")
    kind = (reply[0] >> 4) & 7
    if kind in (6, 7):
        return {}
    if kind != 4:
        raise DominusError("Expected a read acknowledgement")
    hb, lb = reply[2:4]
    if register == 0:
        return {"mode": {0: "off", 2: "summer", 3: "winter", 6: "cooling"}.get(hb & 7, "unmapped"),
                "heating_enabled": bool(hb & 1), "dhw_enabled": bool(hb & 2),
                "heating_active": bool(lb & 2), "dhw_active": bool(lb & 4), "flame": bool(lb & 8)}
    if register == 89:
        if hb != selector:
            raise DominusError("Parameter selector mismatch")
        if selector == 0:
            return {"dominus_active": bool(lb & 1), "thermostat_input": bool(lb & 64)}
        if selector in (7, 9):
            key = {7: "room_modulation_enabled", 9: "room_sensor_enabled"}[selector]
            return {key: bool(lb)} if lb in (0, 1) else {}
        return {"control_timer": lb * 30} if selector == 1 else {"max_flow": lb}
    if register in (16, 24, 25, 26):
        key = {16: "room_target", 24: "room_temperature", 25: "heating_water", 26: "dhw_water"}[register]
        return {key: int.from_bytes(reply[2:4], "big", signed=True) / 256}
    if register in (48, 49):
        prefix = "dhw" if register == 48 else "ch"
        return {prefix + "_min": lb, prefix + "_max": hb} if lb <= hb else {}
    if register == 17:
        return {"modulation": hb} if hb <= 100 else {}
    return {{1: "ch_setpoint", 28: "return_water", 56: "dhw_target", 57: "otc_setpoint"}[register]: hb}


@dataclass
class Snapshot:
    values: dict
    observed: dict[str, datetime]


class DominusClient:
    # Also cover config-flow probe -> new runtime client on the same endpoint.
    _closed_at = {}

    def __init__(self, host, mac, port=2000, password="", *, allow_controls=False, allow_gas_dhw=False,
                 keepalive_interval=10, require_native_room=False, persistent_readonly=False):
        address = ipaddress.ip_address(host)
        if address.version != 4 or not address.is_private or not 1 <= port <= 65535:
            raise ValueError("A private IPv4 address and valid port are required")
        self.host, self.mac, self.port = str(address), normalize_mac(mac), port
        self.password = password
        self.allow_controls, self.allow_gas_dhw = allow_controls, allow_gas_dhw
        self._lock = asyncio.Lock()
        self._channel = None
        self._owns_lease = False
        self._keepalive_task = None
        self.keepalive_interval = keepalive_interval
        self.on_connection_lost = None
        self.require_native_room = require_native_room
        self.persistent_readonly = persistent_readonly
        self._request_label = None

    @property
    def owns_control(self):
        return self._owns_lease and self._channel is not None

    def _identity(self, hello):
        if not re.fullmatch(rb"#D[A-Za-z0-9=]{25}", hello):
            raise DominusError("Unexpected device identification")
        decoded = "".join(PLAIN[(ENCODED.index(chr(c)) - 2) % 63] for c in hello[2:])
        if not re.fullmatch(r"[0-9a-fA-F]{12} [0-9a-fA-F]{12}", decoded) or decoded[:12].lower() != self.mac:
            raise DominusError("Device identity mismatch")
        if self.password and not hmac.compare_digest(decoded[13:], hashlib.md5(self.password.encode()).hexdigest()[:12]):
            raise DominusError("Device identification does not match password")

    async def _drop_connection(self):
        channel, self._channel = self._channel, None
        self._owns_lease = False
        task, self._keepalive_task = self._keepalive_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if channel is not None:
            channel[1].close()
            try:
                await asyncio.wait_for(channel[1].wait_closed(), 1)
            except (OSError, TimeoutError):
                pass
            finally:
                self._closed_at[self.host, self.port] = asyncio.get_running_loop().time()

    async def close(self):
        """Close transport only; never issue a hidden operating-mode command."""
        async with self._lock:
            await self._drop_connection()

    async def _heartbeat_once(self):
        async with self._lock:
            if self._channel is None or not (self._owns_lease or self.persistent_readonly):
                return False
            was_owned = self._owns_lease
            try:
                active = await self._read(self._channel, 89, 0)
                if was_owned and active.get("dominus_active") is not True:
                    raise DominusError("Control lease lost")
            except (DominusError, OSError, TimeoutError, asyncio.IncompleteReadError) as error:
                _LOGGER.warning("Read-only heartbeat failed (%s); dropping connection; no automatic takeover", type(error).__name__)
                await self._drop_connection()
                if self.on_connection_lost is not None:
                    self.on_connection_lost()
                return False
            return True

    async def _keepalive(self):
        try:
            while True:
                await asyncio.sleep(self.keepalive_interval)
                if not await self._heartbeat_once():
                    return
        except asyncio.CancelledError:
            return

    @asynccontextmanager
    async def _session(self):
        phase = "protocol exchange"
        try:
            if self._channel is None:
                loop = asyncio.get_running_loop()
                remaining = self._closed_at.get((self.host, self.port), 0) + 1 - loop.time()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                phase = "TCP connect"
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 5)
                self._channel = [reader, writer, 0.0]
                connected = asyncio.get_running_loop().time()
                phase = "device identification"
                self._identity(await asyncio.wait_for(reader.readexactly(27), 5))
                await asyncio.sleep(max(0, connected + .350 - asyncio.get_running_loop().time()))
            phase = "protocol exchange"
            yield self._channel
        except ControlError:
            if not self._owns_lease:
                await self._drop_connection()
            raise
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as error:
            request = f" ({self._request_label})" if phase == "protocol exchange" and self._request_label else ""
            await self._drop_connection()
            raise DominusError(f"Connection failed during {phase}{request}: {type(error).__name__}; control is not reacquired") from None
        except BaseException:
            await self._drop_connection()
            raise
        else:
            if not self._owns_lease and not self.persistent_readonly:
                await self._drop_connection()
            elif self.keepalive_interval is not None and self._keepalive_task is None:
                self._keepalive_task = asyncio.create_task(self._keepalive(), name="dominus_keepalive")

    async def _exchange(self, channel, frame):
        kind = "write" if (frame[0] >> 4) & 7 == 1 else "read"
        self._request_label = f"{kind} ID{frame[1]}/HB{frame[2]}"
        if channel[2]:
            await asyncio.sleep(max(0, channel[2] + .300 - asyncio.get_running_loop().time()))
        channel[1].write(frame)
        await asyncio.wait_for(channel[1].drain(), 5)
        reply = await asyncio.wait_for(channel[0].readexactly(6), 5)
        channel[2] = asyncio.get_running_loop().time()
        return reply

    async def _read(self, channel, register, selector=0):
        if (register, selector) not in READS + NATIVE_ROOM_READS:
            raise ControlError("Read outside the supported EXA selection")
        values = decode(await self._exchange(channel, _frame(0, register, selector)), register, selector)
        if register == 89 and selector == 0 and values.get("dominus_active") is False:
            self._owns_lease = False
        return values

    async def probe(self):
        async with self._lock:
            async with self._session() as channel:
                if "heating_water" not in await self._read(channel, 25):
                    raise DominusError("EXA temperature read not supported")

    async def read_snapshot(self):
        """Retry a failed read-only poll once on a fresh, validated connection.

        Never resume a partial snapshot or retry any control operation. Loss of
        an owned connection disarms the coordinator even if the read recovers.
        """
        for attempt in range(2):
            was_owned = self.owns_control
            try:
                async with asyncio.timeout(30):
                    snapshot = await self._read_snapshot_once()
                if attempt:
                    _LOGGER.info("Read-only poll recovered on fresh connection; control was not reacquired")
                return snapshot
            except (DominusError, TimeoutError) as error:
                async with self._lock:
                    await self._drop_connection()
                if was_owned and self.on_connection_lost is not None:
                    self.on_connection_lost()
                if attempt:
                    raise DominusError("Read-only poll failed after fresh reconnect: " + str(error)) from error
                _LOGGER.warning("Read-only poll failed (%s); retrying once on a fresh connection; no control commands", str(error))

    async def _read_snapshot_once(self):
        async with self._lock:
            async with self._session() as channel:
                values, observed = {}, {}
                for register, selector in READS:
                    fields = await self._read(channel, register, selector)
                    values.update(fields)
                    observed.update(dict.fromkeys(fields, datetime.now(timezone.utc)))
                if not {"mode", "dominus_active", "control_timer", "heating_water"} <= values.keys():
                    raise DominusError("Required EXA state unavailable")
                return Snapshot(values, observed)

    async def set_panel_mode(self, option):
        """One deliberate UI action, never startup/recovery or a blind retry."""
        if option not in {"local", "off", "summer", "winter"}:
            raise ControlError("Unsupported panel mode; Antifreeze has no verified command")
        if not self.allow_controls:
            raise ControlError("Controls are disabled in integration options")
        if option in {"summer", "winter"} and not self.allow_gas_dhw:
            raise ControlError("Summer/Winter enable gas DHW; explicit permission is required")
        if option == "local":
            if self.owns_control:
                await self.command("off")
            return await self.command("release")
        else:
            if not self.owns_control:
                await self.command("take")  # Fresh OFF required; foreign leases are never stolen.
            return await self.command(option)

    async def command(self, action, value=None):
        """Explicit supported operations; no generic, timer or reset writes."""
        if not self.allow_controls:
            raise ControlError("Controls are disabled in integration options")
        if action == "antifreeze":
            raise ControlError("Antifreeze is not commissioned: no verified EXA command; OFF is not a substitute")
        if action not in {"take", "release", "off", "summer", "winter", "max_flow", "room_target", "dhw_target"}:
            raise ControlError("Unsupported control")
        if action in {"summer", "winter", "dhw_target"} and not self.allow_gas_dhw:
            raise ControlError("Summer/Winter enable gas DHW; explicit permission is required")
        if action == "max_flow" and (type(value) is not int or not 20 <= value <= 85):
            raise ControlError("Flow limit must be an integer within 20–85 °C")
        if action == "dhw_target" and (type(value) is not int or not 10 <= value <= 60):
            raise ControlError("DHW target must be an integer within10–60°C")
        if action == "room_target" and (type(value) not in (int, float) or not math.isfinite(value)
                                        or not 5 <= value <= 35):
            raise ControlError("Room target must be finite and within the integration policy5–35°C")
        async with self._lock:
            async with self._session() as channel:
                state, observed = {}, {}
                for register, selector in ((0, 0), (89, 0), (89, 1)):
                    fields = await self._read(channel, register, selector)
                    state.update(fields)
                    observed.update(dict.fromkeys(fields, datetime.now(timezone.utc)))
                if not {"mode", "dominus_active", "control_timer"} <= state.keys() or state["control_timer"]:
                    raise ControlError("Fresh state is missing or timed control is active")
                owned = state["dominus_active"]
                if action in {"take", "release"}:
                    if state["mode"] != "off":
                        raise ControlError("Select OFF before changing control owner")
                    desired = action == "take"
                    if owned and not self._owns_lease:
                        raise ControlError("Dominus is already active outside this client; do not steal its lease")
                    if owned == desired:
                        return Snapshot(state, observed)
                    target, read_id, selector, key, expected = (89, 0, int(desired)), 89, 0, "dominus_active", desired
                else:
                    if not owned or not self._owns_lease:
                        raise ControlError("Explicitly take control first; local controller will not be overridden")
                    if action == "room_target":
                        if state["mode"] != "winter":
                            raise ControlError("Room compensation requires already-selected Winter; no automatic mode change")
                        native = {}
                        for reg, sel in NATIVE_ROOM_READS:
                            native.update(await self._read(channel, reg, sel))
                        if (native.get("room_modulation_enabled") is not True
                                or native.get("room_sensor_enabled") is not True):
                            raise ControlError("Native room sensor and modulation must be enabled; no settings were changed")
                        raw = round(value * 256)
                        target, read_id, selector, key, expected = (16, raw >> 8, raw & 255), 16, 0, "room_target", raw / 256
                    elif action == "dhw_target":
                        if state["mode"] not in {"summer", "winter"}:
                            raise ControlError("Select Summer or Winter first; DHW writes in OFF do not apply")
                        bounds = await self._read(channel, 48)
                        if not {"dhw_min", "dhw_max"} <= bounds.keys() or not bounds["dhw_min"] <= value <= bounds["dhw_max"]:
                            raise ControlError("Requested DHW target is outside fresh device bounds")
                        target, read_id, selector, key, expected = (56, value, 0), 56, 0, "dhw_target", value
                    elif action == "max_flow":
                        bounds = await self._read(channel, 49)
                        if not {"ch_min", "ch_max"} <= bounds.keys() or not bounds["ch_min"] <= value <= bounds["ch_max"]:
                            raise ControlError("Requested limit is outside fresh device bounds")
                        target, read_id, selector, key, expected = (89, 17, value), 89, 17, "max_flow", value
                    else:
                        if action == "winter" and self.require_native_room:
                            native = {}
                            for reg, sel in NATIVE_ROOM_READS:
                                native.update(await self._read(channel, reg, sel))
                            if (native.get("room_modulation_enabled") is not True
                                    or native.get("room_sensor_enabled") is not True):
                                raise ControlError("Compensation requires enabled native room control before Winter; no settings were changed")
                        target, read_id, selector, key, expected = (0, {"off": 0, "summer": 2, "winter": 3}[action], 0), 0, 0, "mode", action
                try:
                    reply = await self._exchange(channel, _frame(1, *target))
                    # Validate checksum/header without accepting an echo as proof.
                    if (len(reply) != 6 or reply[1] != target[0] or reply[0] & 15
                            or crc(reply[:4]) != int.from_bytes(reply[4:], "big")
                            or sum(b.bit_count() for b in reply[:4]) % 2
                            or (reply[0] >> 4) & 7 not in (1, 5)):
                        raise DominusError("Write response invalid")
                    actual = await self._read(channel, read_id, selector)
                    if key not in actual or actual[key] != expected:
                        raise DominusError("Independent write readback did not match")
                    state.update(actual)
                    observed.update(dict.fromkeys(actual, datetime.now(timezone.utc)))
                    if action == "take":
                        actual = await self._read(channel, 0)
                        if actual.get("mode") != "off":
                            raise DominusError("Unexpected mode after takeover")
                        state.update(actual)
                        observed.update(dict.fromkeys(actual, datetime.now(timezone.utc)))
                        self._owns_lease = True
                    # Only independently read values, never the requested state or ACK echo.
                    return Snapshot(state, observed)
                except (DominusError, OSError, TimeoutError, asyncio.IncompleteReadError):
                    raise WriteUncertain("Command result uncertain; inspect fresh state, do not blindly repeat") from None
