"""Command-line entry point for the force sensor reader."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from .client import ModbusRTUClient
from .protocol import ModbusError, decode_signed_int32


DEFAULT_GROSS_WEIGHT_REGISTER = 80
CHANNEL_REGISTER_STRIDE = 500


def auto_int(value: str) -> int:
    """Parse either decimal or 0x-prefixed integer command-line values."""
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a decimal or 0x-prefixed integer, got {value!r}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read a signed 32-bit force value from a Modbus RTU sensor over "
            "a USB-to-RS485 adapter."
        )
    )
    parser.add_argument("--port", help="serial device, for example /dev/ttyUSB0")
    parser.add_argument(
        "--list-ports", action="store_true", help="list serial devices and exit"
    )
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus unit id (default: 1)")
    parser.add_argument("--baudrate", type=int, default=9600, help="baud rate (default: 9600)")
    parser.add_argument(
        "--parity", choices=("N", "E", "O"), default="N", help="parity (default: N)"
    )
    parser.add_argument(
        "--stopbits", type=int, choices=(1, 2), default=1, help="stop bits (default: 1)"
    )
    parser.add_argument(
        "--register",
        type=auto_int,
        default=DEFAULT_GROSS_WEIGHT_REGISTER,
        help="zero-based first register address (default: 80 / 0x0050 / 40081)",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        help="sensor channel; adds 500 registers per channel after channel 1 (default: 1)",
    )
    parser.add_argument(
        "--word-order",
        choices=("high-low", "low-high"),
        default="high-low",
        help="32-bit register word order (default: high-low)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="multiply the raw signed value by this display scale (default: 1)",
    )
    parser.add_argument(
        "--unit", default="raw", help="display unit label, for example N or kg (default: raw)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.1, help="poll interval in seconds (default: 0.1)"
    )
    parser.add_argument(
        "--timeout", type=float, default=0.5, help="serial timeout in seconds (default: 0.5)"
    )
    parser.add_argument("--once", action="store_true", help="read once and exit")
    parser.add_argument(
        "--show-frames", action="store_true", help="print request and response frames"
    )
    return parser


def list_serial_ports() -> int:
    try:
        from serial.tools import list_ports
    except ImportError:
        print(
            "error: pyserial is not installed; run: python3 -m pip install -e .",
            file=sys.stderr,
        )
        return 2

    ports = sorted(list_ports.comports(), key=lambda item: item.device)
    if not ports:
        print("No serial ports found.")
        return 0
    for item in ports:
        print(f"{item.device}\t{item.description}\t{item.hwid}")
    return 0


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.list_ports:
        return 0
    if not args.port:
        parser.error("--port is required unless --list-ports is used")
    if not 1 <= args.slave_id <= 247:
        parser.error("--slave-id must be in the range 1..247")
    if not 1 <= args.channel <= 8:
        parser.error("--channel must be in the range 1..8")
    if args.interval < 0:
        parser.error("--interval cannot be negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    address = args.register + CHANNEL_REGISTER_STRIDE * (args.channel - 1)
    if not 0 <= address <= 0xFFFE:
        parser.error("the effective two-register address is outside 0..65535")
    return address


def format_frame(frame: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in frame)


def run(args: argparse.Namespace, address: int) -> int:
    client = ModbusRTUClient(
        args.port,
        unit_id=args.slave_id,
        baudrate=args.baudrate,
        parity=args.parity,
        stopbits=args.stopbits,
        timeout=args.timeout,
    )
    print(
        f"Reading {args.port}: slave={args.slave_id}, baud={args.baudrate}, "
        f"format=8{args.parity}{args.stopbits}, channel={args.channel}, "
        f"register={address} (0x{address:04X})",
        flush=True,
    )

    try:
        with client:
            while True:
                reading = client.read_holding_registers(address, 2)
                raw_value = decode_signed_int32(reading.registers, args.word_order)
                force_value = raw_value * args.scale
                timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
                if args.unit == "raw" and args.scale == 1.0:
                    measurement = f"force_raw={raw_value}"
                else:
                    measurement = (
                        f"force={force_value:.10g} {args.unit} raw={raw_value}"
                    )
                print(
                    f"{timestamp} {measurement} "
                    f"registers=[0x{reading.registers[0]:04X}, "
                    f"0x{reading.registers[1]:04X}]",
                    flush=True,
                )
                if args.show_frames:
                    print(f"  TX: {format_frame(reading.request)}", flush=True)
                    print(f"  RX: {format_frame(reading.response)}", flush=True)
                if args.once:
                    return 0
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
    except (ModbusError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_ports:
        return list_serial_ports()
    address = validate_args(parser, args)
    return run(args, address)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
