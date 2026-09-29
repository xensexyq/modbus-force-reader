"""Serial transport for the small Modbus RTU reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .protocol import (
    ModbusResponseError,
    ModbusTimeoutError,
    build_read_holding_registers_request,
    parse_read_holding_registers_response,
)


@dataclass(frozen=True)
class RegisterRead:
    """A validated register read and its raw request/response frames."""

    registers: tuple[int, ...]
    request: bytes
    response: bytes


class ModbusRTUClient:
    """Minimal read-only Modbus RTU client for a serial port."""

    def __init__(
        self,
        port: str,
        *,
        unit_id: int = 1,
        baudrate: int = 9600,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 0.5,
        serial_port: Any | None = None,
    ) -> None:
        if not 1 <= unit_id <= 247:
            raise ValueError("unit_id must be in the range 1..247")
        if baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if parity not in {"N", "E", "O"}:
            raise ValueError("parity must be N, E, or O")
        if stopbits not in {1, 2}:
            raise ValueError("stopbits must be 1 or 2")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.port = port
        self.unit_id = unit_id
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._serial = serial_port
        self._owns_serial = serial_port is None

    def open(self) -> None:
        """Open the configured serial port if it is not already open."""
        if self._serial is not None:
            return
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - depends on installation
            raise RuntimeError(
                "pyserial is not installed; run: python3 -m pip install -e ."
            ) from exc

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=self.parity,
            stopbits=self.stopbits,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )

    def close(self) -> None:
        """Close a serial port opened by this client."""
        if self._serial is not None and self._owns_serial:
            self._serial.close()
            self._serial = None

    def __enter__(self) -> "ModbusRTUClient":
        self.open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def _read_exactly(self, length: int) -> bytes:
        assert self._serial is not None
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self._serial.read(length - len(chunks))
            if not chunk:
                raise ModbusTimeoutError(
                    f"serial timeout after {len(chunks)}/{length} response bytes"
                )
            chunks.extend(chunk)
        return bytes(chunks)

    def read_holding_registers(self, start_address: int, quantity: int) -> RegisterRead:
        """Read and validate holding registers with Modbus function 0x03."""
        self.open()
        assert self._serial is not None

        request = build_read_holding_registers_request(
            self.unit_id, start_address, quantity
        )
        self._serial.reset_input_buffer()
        written = self._serial.write(request)
        if written != len(request):
            raise ModbusResponseError(
                f"incomplete serial write: {written}/{len(request)} bytes"
            )
        self._serial.flush()

        header = self._read_exactly(3)
        if header[1] & 0x80:
            response = header + self._read_exactly(2)
        else:
            response = header + self._read_exactly(header[2] + 2)

        registers = parse_read_holding_registers_response(
            response, self.unit_id, quantity
        )
        return RegisterRead(tuple(registers), request, response)
