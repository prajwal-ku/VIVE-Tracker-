"""
TrackerInterface — the abstraction that decouples the UI from SteamVR.

Any pose source (the SteamVR/OpenVR VIVE Tracker, the built-in simulator, or a
future OpenXR / network source) implements this interface. The UI only ever
talks to `TrackerInterface`, so nothing above this layer knows or cares which
concrete tracker is active.

A tracker supplies:
    • a 6DoF pose            → get_pose()  -> TrackerData
    • physical button edges  → poll_buttons() -> ButtonEvents
    • a connection status    → get_status() -> TrackerStatus
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from ..core.models import TrackerData


class DeviceState(Enum):
    """Green/red style states for the connection-status panel."""
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class TrackerStatus:
    """Snapshot of the tracking system health for the status panel."""
    steamvr:      DeviceState = DeviceState.OFFLINE
    tracker:      DeviceState = DeviceState.OFFLINE
    base_station_1: DeviceState = DeviceState.OFFLINE
    base_station_2: DeviceState = DeviceState.OFFLINE
    battery:      float | None = None   # 0..1, or None if unknown
    detail:       str = "Offline"


@dataclass
class ButtonEvents:
    """Rising-edge, debounced hardware button events for a single poll."""
    record: bool = False   # "Point & Play" — capture a waypoint
    play:   bool = False   # start playback


class TrackerInterface(ABC):
    """Common interface for every pose source."""

    #: Human-readable name for the UI ("Simulation", "VIVE Tracker", …)
    name: str = "Tracker"
    #: True for sources that support the on-screen click-to-move workflow.
    is_simulated: bool = False

    @abstractmethod
    def connect(self) -> tuple[bool, str]:
        """Attempt to start the source. Returns (ok, message)."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release the source."""

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def get_pose(self) -> TrackerData:
        """Return the most recent 6DoF pose (thread-safe)."""

    def poll_buttons(self) -> ButtonEvents:
        """Return debounced rising-edge button events. Default: none."""
        return ButtonEvents()

    @abstractmethod
    def get_status(self) -> TrackerStatus:
        """Return a health snapshot for the connection-status panel."""
