"""Command-line entry point for the force sensor reader."""

from __future__ import annotations

import argparse
import math
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
        default=None,
        help="explicit display multiplier; otherwise read device decimal position",
    )
    parser.add_argument(
        "--unit", default=None, help="explicit display unit; otherwise convert device unit to N"
    )
    parser.add_argument("--raw", action="store_true", help="show raw counts without unit conversion")
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
    if args.scale is not None and not math.isfinite(args.scale):
        parser.error("--scale must be finite")
    if not args.raw and (args.scale is None) != (args.unit is None):
        parser.error("specify both --scale and --unit for a manual conversion")
    if args.raw and (args.scale is not None or args.unit is not None):
        parser.error("--raw cannot be combined with --scale or --unit")

    address = args.register + CHANNEL_REGISTER_STRIDE * (args.channel - 1)
    if not 0 <= address <= 0xFFFE:
        parser.error("the effective two-register address is outside 0..65535")
    return address


def format_frame(frame: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in frame)


def force_scale(status: int, unit_code: int) -> float:
    """Convert device counts to newtons using its decimal position and unit.

    Mass units use standard gravity (9.80665 m/s²) for equivalent force.
    """
    factors = {1: 0.00980665, 2: 9.80665, 3: 9806.65, 4: 1.0}
    if unit_code not in factors:
        raise RuntimeError(
            f"设备单位未设置或不支持（{unit_code}）；请核实标定后指定 "
            "--scale 和 --unit，或使用 --raw 查看原始值"
        )
    return factors[unit_code] * 10 ** -(status & 7)


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
            scale, unit = args.scale, args.unit
            if args.raw:
                scale, unit = 1.0, "counts"
            elif scale is None:
                if args.register != DEFAULT_GROSS_WEIGHT_REGISTER:
                    raise RuntimeError("自定义寄存器请明确指定 --scale 和 --unit，或使用 --raw")
                offset = CHANNEL_REGISTER_STRIDE * (args.channel - 1)
                status = client.read_holding_registers(offset + 8, 1).registers[0]
                time.sleep(0.01)
                unit_code = client.read_holding_registers(offset + 104, 1).registers[0]
                scale, unit = force_scale(status, unit_code), "N"
                print(f"自动换算：设备单位代码={unit_code}，小数位={status & 7}，每计数={scale:g} N", flush=True)
                if unit_code != 4:
                    print("质量单位按标准重力 9.80665 m/s² 换算为等效力。", flush=True)
                time.sleep(0.01)
            peak = 0.0
            live = sys.stdout.isatty() and not args.once and not args.show_frames
            while True:
                reading = client.read_holding_registers(address, 2)
                raw_value = decode_signed_int32(reading.registers, args.word_order)
                force_value = raw_value * scale
                peak = max(peak, abs(force_value))
                timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
                measurement = f"当前力: {force_value:+.4f} {unit}  |  峰值(绝对值): {peak:.4f} {unit}"
                if args.raw:
                    measurement = f"原始值: {raw_value} counts"
                if args.show_frames:
                    measurement += f" raw={raw_value} registers={reading.registers}"
                print(
                    ("\r\033[2K" if live else f"{timestamp} ") + measurement,
                    end="" if live else "\n",
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
