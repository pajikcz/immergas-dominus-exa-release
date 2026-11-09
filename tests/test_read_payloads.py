"""Bounded diagnostic payloads from existing reads only; no network."""
import unittest
from unittest.mock import AsyncMock
from loader import client as c
from test_client import packet, MAC


class ReadPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_read_records_full_payload_without_extra_exchange(self):
        client = c.DominusClient("192.168.1.2", MAC)
        client._exchange = AsyncMock(return_value=packet(4, 89, 0x41))
        await client._read(None, 89, 0)
        self.assertEqual(client._exchange.await_count, 1)
        record = client.read_payloads["89:0"]
        self.assertEqual((record["hb"], record["lb"]), (0, 65))
        self.assertIn("observed_at", record)
        record["lb"] = 255
        self.assertEqual(client.read_payloads["89:0"]["lb"], 65)
        client._exchange.return_value = packet(4, 89, 1)
        await client._read(None, 89, 0)
        self.assertEqual(len(client.read_payloads), 1)
        self.assertEqual(client.read_payloads["89:0"]["lb"], 1)

    async def test_invalid_and_negative_responses_are_not_recorded(self):
        client = c.DominusClient("192.168.1.2", MAC)
        client._exchange = AsyncMock(return_value=b"broken")
        with self.assertRaises(c.DominusError):
            await client._read(None, 0)
        self.assertEqual(client.read_payloads, {})
        client._exchange.return_value = packet(6, 0)
        await client._read(None, 0)
        self.assertEqual(client.read_payloads, {})

    async def test_unsupported_read_does_not_exchange_or_record(self):
        client = c.DominusClient("192.168.1.2", MAC)
        client._exchange = AsyncMock()
        with self.assertRaises(c.ControlError):
            await client._read(None, 200)
        client._exchange.assert_not_awaited()
        self.assertEqual(client.read_payloads, {})
