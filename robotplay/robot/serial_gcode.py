"""
SerialGCodeRobot — stream a taught path to a G-code controller over a COM port.

The waypoint path is emitted as one `G1` linear move per waypoint (straight
Cartesian segments — the "ideal" robot path; the controller's planner decides how
the joints get there). Coordinates are converted from metres to millimetres.

Works with GRBL-based CNC/robot controllers, Marlin-based printer arms, and any
device that accepts G-code over serial.
"""

from __future__ import annotations

import time
from datetime import datetime

from ..core.models import Waypoint
from .base import (RobotInterface, RobotBackend, ConnectionParams, ProgressCb)


class SerialGCodeRobot(RobotInterface):
    backend = RobotBackend.SERIAL_GCODE

    def __init__(self):
        self._ser = None
        self._connected = False

    # ── availability ────────────────────────────────────────────
    def is_available(self) -> tuple[bool, str]:
        try:
            import serial  # noqa: F401
            return True, "pyserial available"
        except Exception:
            return False, "pyserial not installed (pip install pyserial)"

    def list_ports(self) -> list[str]:
        try:
            import serial.tools.list_ports
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    # ── connection ──────────────────────────────────────────────
    def connect(self, params: ConnectionParams) -> tuple[bool, str]:
        try:
            import serial
            if not params.port:
                return False, "No COM port selected"
            self._ser = serial.Serial(params.port, params.baud, timeout=2)
            time.sleep(2.0)               # let the controller reset/boot
            self._connected = True
            return True, f"Connected to {params.port} @ {params.baud} baud"
        except Exception as e:
            self._connected = False
            return False, f"Serial error: {e}"

    def disconnect(self) -> None:
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── program generation ──────────────────────────────────────
    def build_gcode(self, waypoints: list[Waypoint],
                    params: ConnectionParams) -> str:
        feed = params.speed or 1000
        lines = [
            "; Robot Point & Play — G-code (straight-segment waypoint path)",
            f"; Generated: {datetime.now().isoformat(timespec='seconds')}",
            f"; Waypoints: {len(waypoints)}   Feed: {feed} mm/min",
            "; Units: mm  |  absolute positioning",
            "G21 ; millimetres",
            "G90 ; absolute",
            "G28 ; home all axes",
            "",
        ]
        for wp in waypoints:
            p = wp.pose
            lines.append(
                f"G1 X{p.x*1000:.2f} Y{p.y*1000:.2f} Z{p.z*1000:.2f} "
                f"F{feed}  ; {wp.name}"
            )
        lines += ["", "G28 ; return home", "M84 ; disable motors"]
        return "\n".join(lines)

    def preview_program(self, waypoints: list[Waypoint],
                        params: ConnectionParams) -> str:
        if not waypoints:
            return "; No waypoints — capture at least one point first."
        return self.build_gcode(waypoints, params)

    # ── execution ───────────────────────────────────────────────
    def send_program(self, waypoints: list[Waypoint],
                     params: ConnectionParams,
                     progress: ProgressCb = None) -> tuple[bool, str]:
        if not self._connected or self._ser is None:
            return False, "Robot not connected"
        if not waypoints:
            return False, "No waypoints to send"

        gcode = self.build_gcode(waypoints, params)
        cmds = [ln.strip() for ln in gcode.splitlines()
                if ln.strip() and not ln.strip().startswith(";")]
        total = len(cmds)
        for i, line in enumerate(cmds, 1):
            try:
                self._ser.write((line + "\n").encode())
                time.sleep(0.05)
                if progress:
                    progress(i, total, f"Sending {i}/{total}: {line}")
            except Exception as e:
                return False, f"Send failed at line {i}: {e}"
        return True, f"G-code sent — {total} commands"
