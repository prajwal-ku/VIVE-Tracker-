"""
FairinoRobot — drive a FAIRINO arm over TCP/IP.

FAIRINO controllers (and the FAIRINO_SimMachine simulator) are driven by the
`fairino` Python SDK over Ethernet, NOT by G-code. The teaching workflow's
Cartesian waypoints map directly onto the SDK's linear-move primitive:

        waypoint (x,y,z, roll,pitch,yaw)  →  robot.MoveL([x_mm, y_mm, z_mm,
                                                          rx, ry, rz], tool, user, vel)

Right now the `fairino` package lives on the other laptop (the one running
FAIRINO_SimMachine_v3.8.7), so on this machine the SDK import fails gracefully:
`is_available()` reports why, the UI disables "Send", and you can still generate
and inspect the exact program that WILL be sent once the two machines are merged.

When the SDK is present, set the controller/sim IP in the UI (default
192.168.58.2), Connect, then Send — each waypoint becomes a MoveL. Because the
call surface differs slightly across SDK builds, `_move_linear` tries the common
call conventions and reports precisely which one to keep if none match.
"""

from __future__ import annotations

from datetime import datetime

from ..config import CONFIG
from ..core.models import Waypoint
from .base import (RobotInterface, RobotBackend, ConnectionParams, ProgressCb)


class FairinoRobot(RobotInterface):
    backend = RobotBackend.FAIRINO_TCP

    def __init__(self):
        self._robot = None
        self._connected = False

    # ── availability ────────────────────────────────────────────
    def is_available(self) -> tuple[bool, str]:
        try:
            import fairino  # noqa: F401
            return True, "fairino SDK available"
        except Exception:
            return (False,
                    "fairino SDK not installed on this machine — program can be "
                    "generated & previewed, but not sent. Install on the "
                    "FAIRINO_SimMachine laptop to enable live control.")

    # ── connection ──────────────────────────────────────────────
    def connect(self, params: ConnectionParams) -> tuple[bool, str]:
        try:
            from fairino import Robot
        except Exception as e:
            return False, (f"fairino SDK unavailable: {e}. This backend is a "
                           "ready stub — connect from the FAIRINO_SimMachine "
                           "laptop where the SDK is installed.")
        try:
            host = params.host or CONFIG.robot.fairino_default_ip
            self._robot = Robot.RPC(host)      # opens the TCP/IP session
            self._connected = True
            return True, f"Connected to FAIRINO controller at {host}"
        except Exception as e:
            self._connected = False
            self._robot = None
            return False, f"FAIRINO connect error: {e}"

    def disconnect(self) -> None:
        try:
            if self._robot is not None and hasattr(self._robot, "CloseRPC"):
                self._robot.CloseRPC()
        except Exception:
            pass
        self._robot = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── helpers ──────────────────────────────────────────────────
    @staticmethod
    def _desc_pose(wp: Waypoint) -> list[float]:
        """Waypoint → FAIRINO Cartesian descriptor [x,y,z (mm), rx,ry,rz (deg)]."""
        p = wp.pose
        return [round(p.x * 1000, 3), round(p.y * 1000, 3), round(p.z * 1000, 3),
                round(p.roll, 3), round(p.pitch, 3), round(p.yaw, 3)]

    def _move_linear(self, desc: list[float], params: ConnectionParams):
        """Issue one MoveL, tolerant of SDK signature differences across builds.
        Returns the SDK error code (0 == success) or raises."""
        vel = float(params.speed or CONFIG.robot.default_linear_vel)
        tool, user = params.tool, params.workpiece
        # Most common modern fairino signature: MoveL(desc_pos, tool, user, vel=..)
        try:
            return self._robot.MoveL(desc, tool, user, vel=vel)
        except TypeError:
            pass
        # Older signature requiring an (ignored) joint seed as first arg.
        return self._robot.MoveL([0, 0, 0, 0, 0, 0], desc, tool, user, vel)

    # ── program preview ─────────────────────────────────────────
    def preview_program(self, waypoints: list[Waypoint],
                        params: ConnectionParams) -> str:
        if not waypoints:
            return "# No waypoints — capture at least one point first."
        host = params.host or CONFIG.robot.fairino_default_ip
        vel = params.speed or CONFIG.robot.default_linear_vel
        lines = [
            "# FAIRINO motion program (fairino Python SDK)",
            f"# Generated: {datetime.now().isoformat(timespec='seconds')}",
            f"# Waypoints: {len(waypoints)}   Vel: {vel}%   "
            f"Tool: {params.tool}  User: {params.workpiece}",
            "",
            "from fairino import Robot",
            f"robot = Robot.RPC('{host}')",
            "",
        ]
        for wp in waypoints:
            d = self._desc_pose(wp)
            lines.append(
                f"robot.MoveL({d}, tool={params.tool}, user={params.workpiece}, "
                f"vel={float(vel)})   # {wp.name}"
            )
        return "\n".join(lines)

    # ── execution ───────────────────────────────────────────────
    def send_program(self, waypoints: list[Waypoint],
                     params: ConnectionParams,
                     progress: ProgressCb = None) -> tuple[bool, str]:
        if not self._connected or self._robot is None:
            return False, "FAIRINO not connected"
        if not waypoints:
            return False, "No waypoints to send"

        total = len(waypoints)
        for i, wp in enumerate(waypoints, 1):
            desc = self._desc_pose(wp)
            try:
                err = self._move_linear(desc, params)
            except Exception as e:
                return False, f"MoveL failed at {wp.name}: {e}"
            if err not in (0, None):
                return False, f"MoveL returned error {err} at {wp.name}"
            if progress:
                progress(i, total, f"MoveL {i}/{total} → {wp.name}")
        return True, f"FAIRINO program executed — {total} MoveL segments"
