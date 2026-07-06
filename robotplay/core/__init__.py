"""Core domain logic: data models, logging, waypoint/session management, playback."""

from .models import TrackerData, Waypoint, quat_to_euler, euler_to_quat, quat_slerp
from .logger import EventLogger, LogEntry
from .waypoint_manager import WaypointManager
from .session_manager import SessionManager
from .playback_engine import PlaybackEngine, PlaybackState

__all__ = [
    "TrackerData", "Waypoint",
    "quat_to_euler", "euler_to_quat", "quat_slerp",
    "EventLogger", "LogEntry",
    "WaypointManager", "SessionManager",
    "PlaybackEngine", "PlaybackState",
]
