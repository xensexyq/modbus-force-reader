import unittest

from modbus_force_reader.protocol import (
    ModbusCRCError,
    ModbusExceptionResponse,
    append_crc,
    build_read_holding_registers_request,
    decode_signed_int32,
    parse_read_holding_registers_response,
)


class ProtocolTests(unittest.TestCase):
    def test_vendor_gross_weight_request_frame(self) -> None:
        request = build_read_holding_registers_request(1, 80, 2)
        self.assertEqual(request.hex(" ").upper(), "01 03 00 50 00 02 C4 1A")

    def test_vendor_positive_response(self) -> None:
        response = bytes.fromhex("01 03 04 00 00 00 84 FA 50")
        registers = parse_read_holding_registers_response(response, 1, 2)
        self.assertEqual(registers, [0x0000, 0x0084])
        self.assertEqual(decode_signed_int32(registers), 132)

    def test_negative_twos_complement_value(self) -> None:
        self.assertEqual(decode_signed_int32([0xFFFF, 0xF0C2]), -3902)

    def test_low_high_word_order(self) -> None:
        self.assertEqual(decode_signed_int32([0x0084, 0x0000], "low-high"), 132)

    def test_crc_error_is_rejected(self) -> None:
        response = bytearray.fromhex("01 03 04 00 00 00 84 FA 50")
        response[-1] ^= 0x01
        with self.assertRaises(ModbusCRCError):
            parse_read_holding_registers_response(bytes(response), 1, 2)

    def test_modbus_exception_is_reported(self) -> None:
        response = append_crc(bytes([1, 0x83, 0x02]))
        with self.assertRaises(ModbusExceptionResponse) as context:
            parse_read_holding_registers_response(response, 1, 2)
        self.assertEqual(context.exception.code, 0x02)


if __name__ == "__main__":
    unittest.main()
