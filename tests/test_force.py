import unittest
from modbus_force_reader.cli import force_scale, main


class ForceTests(unittest.TestCase):
    def test_device_newton_decimal_position(self):
        self.assertAlmostEqual(146 * force_scale(129, 4), 14.6)
        self.assertAlmostEqual(-2 * force_scale(129, 4), -0.2)

    def test_status_flags_do_not_change_decimal_position(self):
        self.assertAlmostEqual(force_scale(0xFE82, 4), 0.01)

    def test_mass_to_equivalent_force(self):
        self.assertAlmostEqual(1000 * force_scale(0, 1), 9.80665)
        self.assertAlmostEqual(force_scale(0, 2), 9.80665)
        self.assertAlmostEqual(force_scale(3, 3), 9.80665)

    def test_unknown_unit_is_not_presented_as_force(self):
        for code in (0, 5, 65535):
            with self.assertRaises(RuntimeError):
                force_scale(1, code)

    def test_manual_conversion_requires_both_arguments(self):
        with self.assertRaises(SystemExit) as error:
            main(["--port", "unused", "--unit", "N"])
        self.assertEqual(error.exception.code, 2)
