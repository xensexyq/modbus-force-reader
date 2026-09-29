import unittest

from modbus_force_reader.cli import CHANNEL_REGISTER_STRIDE, auto_int, build_parser, validate_args


class CLITests(unittest.TestCase):
    def test_hex_register_argument(self) -> None:
        self.assertEqual(auto_int("0x50"), 80)

    def test_channel_address_formula(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--port", "/dev/ttyUSB0", "--channel", "6"])
        self.assertEqual(validate_args(parser, args), 80 + 5 * CHANNEL_REGISTER_STRIDE)


if __name__ == "__main__":
    unittest.main()
