"""
RobotInterface — the abstraction that decouples the app from any specific robot.

The teaching workflow produces a list of Cartesian `Waypoint`s. A robot backend's
job is to (a) connect over whatever transport it uses and (b) execute those
waypoints as a motion program. Two backends ship today:

    • SerialGCodeRobot  — streams G1 moves over a COM port (GRBL/Marlin-style
      controllers). Works right now with any serial robot/CNC.
    • FairinoRobot      — drives a FAIRINO arm (e.g. FAIRINO_SimMachine_v3.8.7)
      over TCP/IP with MoveL/MoveJ via the `fairino` Python SDK.

New transports (ROS2, MoveIt, a proprietary TCP protocol) only need to implement
this interface — nothing in the UI changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from ..core.models import Waypoint


class RobotBackend(Enum):
    SERIAL_GCODE = "Serial / G-code (COM)"
    FAIRINO_TCP = "FAIRINO (TCP/IP)"


@dataclass
class ConnectionParams:
    """Everything a backend might need to connect. Unused fields are ignored."""
    port: str = ""                 # COM port (serial)
    baud: int = 115200             # serial baud
    host: str = "192.168.58.2"     # IP (FAIRINO / network)
    tcp_port: int = 8080           # TCP port
    speed: int = 30                # velocity: mm/min (serial) or % (FAIRINO)
    tool: int = 0
    workpiece: int = 0


# Progress callback: (line_index, total_lines, message)
ProgressCb = Optional[Callable[[int, int, str], None]]


class RobotInterface(ABC):
    """Common interface for every robot backend."""

    #: Which backend this class implements (for the UI selector).
    backend: RobotBackend

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Is this backend usable on this machine? (deps installed, etc.)
        Returns (available, reason)."""

    def list_ports(self) -> list[str]:
        """Serial ports for backends that use them; empty otherwise."""
        return []

    @abstractmethod
    def connect(self, params: ConnectionParams) -> tuple[bool, str]:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def send_program(self, waypoints: list[Waypoint],
                     params: ConnectionParams,
                     progress: ProgressCb = None) -> tuple[bool, str]:
        """Execute the taught waypoints on the robot. Blocking — call from a
        worker thread. Reports progress via the callback."""

    def preview_program(self, waypoints: list[Waypoint],
                        params: ConnectionParams) -> str:
        """Human-readable program text (G-code / SDK calls) for the preview tab."""
        return ""
