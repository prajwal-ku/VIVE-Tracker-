"""Tracker abstraction: the VIVE Tracker (SteamVR/OpenVR) behind one interface.

The `TrackerInterface` abstraction is retained so a future pose source (OpenXR,
network) can be added without touching the UI — but this application runs on a
real VIVE Tracker only; there is no simulated fallback.
"""

from .base import TrackerInterface, TrackerStatus, DeviceState, ButtonEvents
from .vive import ViveTracker

__all__ = [
    "TrackerInterface", "TrackerStatus", "DeviceState", "ButtonEvents",
    "ViveTracker",
]
