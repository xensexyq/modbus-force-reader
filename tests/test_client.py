import unittest

from modbus_force_reader.client import ModbusRTUClient
from modbus_force_reader.protocol import ModbusTimeoutError


class FakeSerial:
    def __init__(self, response: bytes, max_chunk: int | None = None) -> None:
        self.response = bytearray(response)
        self.max_chunk = max_chunk
        self.writes: list[bytes] = []
        self.reset_count = 0
        self.flush_count = 0

    def reset_input_buffer(self) -> None:
        self.reset_count += 1

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        self.flush_count += 1

    def read(self, size: int) -> bytes:
        if not self.response:
            return b""
        if self.max_chunk is not None:
            size = min(size, self.max_chunk)
        chunk = self.response[:size]
        del self.response[:size]
        return bytes(chunk)


class ClientTests(unittest.TestCase):
    def test_read_handles_partial_serial_chunks(self) -> None:
        serial_port = FakeSerial(
            bytes.fromhex("01 03 04 00 00 00 84 FA 50"), max_chunk=1
        )
        client = ModbusRTUClient("fake", serial_port=serial_port)

        reading = client.read_holding_registers(80, 2)

        self.assertEqual(reading.registers, (0, 132))
        self.assertEqual(
            serial_port.writes, [bytes.fromhex("01 03 00 50 00 02 C4 1A")]
        )
        self.assertEqual(serial_port.reset_count, 1)
        self.assertEqual(serial_port.flush_count, 1)

    def test_timeout_is_reported(self) -> None:
        client = ModbusRTUClient("fake", serial_port=FakeSerial(b""))
        with self.assertRaises(ModbusTimeoutError):
            client.read_holding_registers(80, 2)


if __name__ == "__main__":
    unittest.main()
