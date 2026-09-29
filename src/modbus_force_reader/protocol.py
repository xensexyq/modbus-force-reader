"""Small, strict Modbus RTU helpers used by the reader."""

from __future__ import annotations

import struct
from collections.abc import Sequence


READ_HOLDING_REGISTERS = 0x03


class ModbusError(Exception):
    """Base class for Modbus communication and protocol errors."""


class ModbusTimeoutError(ModbusError):
    """Raised when a complete response is not received before the timeout."""


class ModbusCRCError(ModbusError):
    """Raised when a response has an invalid CRC."""


class ModbusResponseError(ModbusError):
    """Raised when a response is malformed or does not match the request."""


class ModbusExceptionResponse(ModbusError):
    """Raised when the sensor returns a Modbus exception response."""

    _MESSAGES = {
        0x01: "illegal function",
        0x02: "illegal data address",
        0x03: "illegal data value",
        0x04: "server device failure",
        0x06: "server device busy",
    }

    def __init__(self, code: int) -> None:
        self.code = code
        message = self._MESSAGES.get(code, "unknown exception")
        super().__init__(f"Modbus exception 0x{code:02X}: {message}")


def crc16(data: bytes) -> int:
    """Return the Modbus CRC-16 value for *data*."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(payload: bytes) -> bytes:
    """Append a little-endian Modbus CRC to a frame payload."""
    return payload + crc16(payload).to_bytes(2, "little")


def build_read_holding_registers_request(
    unit_id: int, start_address: int, quantity: int
) -> bytes:
    """Build a function 0x03 request frame."""
    if not 1 <= unit_id <= 247:
        raise ValueError("unit_id must be in the range 1..247")
    if not 0 <= start_address <= 0xFFFF:
        raise ValueError("start_address must be in the range 0..65535")
    if not 1 <= quantity <= 125:
        raise ValueError("quantity must be in the range 1..125")
    if start_address + quantity > 0x10000:
        raise ValueError("requested register range exceeds 65535")

    payload = struct.pack(">BBHH", unit_id, READ_HOLDING_REGISTERS, start_address, quantity)
    return append_crc(payload)


def parse_read_holding_registers_response(
    frame: bytes, expected_unit_id: int, expected_quantity: int
) -> list[int]:
    """Validate a function 0x03 response and return its 16-bit registers."""
    if len(frame) < 5:
        raise ModbusResponseError(f"response is too short: {len(frame)} bytes")

    received_crc = int.from_bytes(frame[-2:], "little")
    calculated_crc = crc16(frame[:-2])
    if received_crc != calculated_crc:
        raise ModbusCRCError(
            f"CRC mismatch: received 0x{received_crc:04X}, "
            f"calculated 0x{calculated_crc:04X}"
        )

    if frame[0] != expected_unit_id:
        raise ModbusResponseError(
            f"unexpected unit id {frame[0]}, expected {expected_unit_id}"
        )

    function = frame[1]
    if function == (READ_HOLDING_REGISTERS | 0x80):
        if len(frame) != 5:
            raise ModbusResponseError("malformed Modbus exception response")
        raise ModbusExceptionResponse(frame[2])
    if function != READ_HOLDING_REGISTERS:
        raise ModbusResponseError(
            f"unexpected function 0x{function:02X}, expected 0x03"
        )

    byte_count = frame[2]
    expected_byte_count = expected_quantity * 2
    if byte_count != expected_byte_count:
        raise ModbusResponseError(
            f"unexpected byte count {byte_count}, expected {expected_byte_count}"
        )
    if len(frame) != byte_count + 5:
        raise ModbusResponseError(
            f"unexpected frame length {len(frame)}, expected {byte_count + 5}"
        )

    register_data = frame[3:-2]
    return list(struct.unpack(f">{expected_quantity}H", register_data))


def decode_signed_int32(
    registers: Sequence[int], word_order: str = "high-low"
) -> int:
    """Decode two Modbus registers as a signed, two's-complement 32-bit value."""
    if len(registers) != 2:
        raise ValueError("exactly two registers are required for a 32-bit value")
    if any(not 0 <= register <= 0xFFFF for register in registers):
        raise ValueError("register values must be in the range 0..65535")

    if word_order == "high-low":
        high_word, low_word = registers
    elif word_order == "low-high":
        low_word, high_word = registers
    else:
        raise ValueError("word_order must be 'high-low' or 'low-high'")

    unsigned_value = (high_word << 16) | low_word
    if unsigned_value & 0x80000000:
        return unsigned_value - 0x100000000
    return unsigned_value
