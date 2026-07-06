"""Robot abstraction: one interface, swappable backends (G-code serial / FAIRINO)."""

from .base import RobotInterface, RobotBackend, ConnectionParams
from .serial_gcode import SerialGCodeRobot
from .fairino import FairinoRobot

#: Registry the UI uses to build the backend selector.
BACKENDS = {
    RobotBackend.SERIAL_GCODE: SerialGCodeRobot,
    RobotBackend.FAIRINO_TCP: FairinoRobot,
}

__all__ = [
    "RobotInterface", "RobotBackend", "ConnectionParams",
    "SerialGCodeRobot", "FairinoRobot", "BACKENDS",
]
