"""
ViveTracker — real 6DoF pose + physical buttons from an HTC VIVE Tracker via
SteamVR/OpenVR.

This is the concrete `TrackerInterface` that talks to real hardware. It is
designed to be robust for unattended, real-time operation:

    • Thread-safe pose caching (the pose is read on the render timer and could be
      read from other threads).
    • Physical pogo-pin buttons decoded by direct bitmask (works even when
      SteamVR has no input binding for a generic tracker):
          Pin 3 / Grip    → 1 << 2   → capture waypoint ("Point & Play")
          Pin 4 / Trigger → 1 << 33  → start playback
      Rising-edge detection + a debounce cooldown → one physical click == one
      action.
    • Auto-recovery: re-finds the tracker index if the device drops and returns.
    • Base-station (lighthouse) detection for the connection-status panel.

The `openvr` import is done lazily inside methods so the rest of the app can be
imported (and the simulator used) on a machine without SteamVR installed.
"""

from __future__ import annotations

import math
import threading
import time

import numpy as np

from ..config import CONFIG
from ..core.models import TrackerData
from .base import TrackerInterface, TrackerStatus, DeviceState, ButtonEvents


class ViveTracker(TrackerInterface):
    name = "VIVE Tracker"
    is_simulated = False

    def __init__(self):
        self._vr = None
        self._tracker_index: int | None = None
        self._connected = False

        self._pose = TrackerData(0.0, 0.0, 0.5)
        self._pose_lock = threading.Lock()

        # Calibration: raw OpenVR pose → accurate scene pose. Shared with the UI
        # so "Set Zero" and model-alignment controls act on the live pipeline.
        from ..core.calibration import Calibration
        self.calibration = Calibration(
            world_conversion=CONFIG.calibration.world_conversion,
            model_offset_euler=CONFIG.calibration.model_offset_euler,
            axis_flip_orientation=CONFIG.calibration.axis_flip_orientation,
            axis_flip_position=CONFIG.calibration.axis_flip_position,
            orientation_invert_euler=CONFIG.calibration.orientation_invert_euler)
        self._raw_pos = np.zeros(3)
        self._raw_R = np.eye(3)

        cfg = CONFIG.buttons
        self._record_mask = cfg.record_bitmask
        self._play_mask = cfg.play_bitmask
        self._debounce = CONFIG.capture.button_debounce

        self._prev_record = False
        self._prev_play = False
        self._last_record_t = 0.0
        self._last_play_t = 0.0

    # ── connection ───────────────────────────────────────────────
    def connect(self) -> tuple[bool, str]:
        try:
            import openvr
            self._vr = openvr.init(openvr.VRApplication_Other)
            self._connected = True
            self._find_tracker()
            if self._tracker_index is None:
                # SteamVR session is open; keep it and let the status poll pick up
                # the tracker as soon as it is powered on (real-world workflow).
                return True, "SteamVR connected — waiting for tracker (power it on)"
            return True, f"VIVE Tracker connected (device {self._tracker_index})"
        except Exception as e:
            self._connected = False
            self._vr = None
            return False, f"SteamVR/OpenVR error: {e}"

    def disconnect(self) -> None:
        try:
            import openvr
            openvr.shutdown()
        except Exception:
            pass
        self._connected = False
        self._vr = None
        self._tracker_index = None

    def is_connected(self) -> bool:
        return self._connected

    def try_reconnect(self) -> bool:
        """Re-find the tracker device index after a signal drop."""
        if self._vr is None:
            ok, _ = self.connect()
            return ok
        try:
            self._find_tracker()
            return self._tracker_index is not None
        except Exception:
            return False

    def _find_tracker(self) -> None:
        import openvr
        poses = self._vr.getDeviceToAbsoluteTrackingPose(
            openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)
        classes = (openvr.TrackedDeviceClass_GenericTracker,
                   openvr.TrackedDeviceClass_Controller)
        # First pass: prefer a device that is actually CONNECTED (avoids latching
        # onto a stale/phantom tracker slot SteamVR still lists). Second pass:
        # accept any matching device so we at least have an index to poll.
        for require_connected in (True, False):
            for cls in classes:
                for i in range(openvr.k_unMaxTrackedDeviceCount):
                    if self._vr.getTrackedDeviceClass(i) != cls:
                        continue
                    if require_connected and not poses[i].bDeviceIsConnected:
                        continue
                    self._tracker_index = i
                    return
        self._tracker_index = None

    # ── pose ─────────────────────────────────────────────────────
    def get_pose(self) -> TrackerData:
        if not self._connected or self._vr is None:
            with self._pose_lock:
                return self._pose.copy()
        try:
            import openvr
            poses = self._vr.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0,
                openvr.k_unMaxTrackedDeviceCount)

            if self._tracker_index is None:
                self._find_tracker()
            if self._tracker_index is not None:
                p = poses[self._tracker_index]
                if p.bPoseIsValid:
                    m = p.mDeviceToAbsoluteTracking
                    # OpenVR row-major 3x4: position is the 4th column.
                    pos_vr = np.array([m[0][3], m[1][3], m[2][3]])
                    R_vr = np.array([[m[0][0], m[0][1], m[0][2]],
                                     [m[1][0], m[1][1], m[1][2]],
                                     [m[2][0], m[2][1], m[2][2]]])
                    # Keep the raw pose for "Set Zero"; report the calibrated one.
                    self._raw_pos, self._raw_R = pos_vr, R_vr
                    pos, R = self.calibration.to_scene(pos_vr, R_vr)
                    pose = TrackerData.from_matrix(pos[0], pos[1], pos[2], R)
                    with self._pose_lock:
                        self._pose = pose
        except Exception:
            pass  # keep last good pose; status polling will flag the drop
        with self._pose_lock:
            return self._pose.copy()

    # ── calibration control ─────────────────────────────────────
    def calibrate_zero(self) -> None:
        """Capture the current raw pose as the workspace origin/orientation."""
        self.calibration.set_reference(self._raw_pos, self._raw_R)

    def clear_calibration(self) -> None:
        self.calibration.clear_reference()

    # ── physical buttons ────────────────────────────────────────
    def poll_buttons(self) -> ButtonEvents:
        if not self._connected or self._vr is None or self._tracker_index is None:
            return ButtonEvents()
        try:
            result, state = self._vr.getControllerState(self._tracker_index)
            if not result:
                return ButtonEvents()

            now = time.monotonic()
            raw_rec = bool(state.ulButtonPressed & self._record_mask)
            raw_play = bool(state.ulButtonPressed & self._play_mask)

            rec_edge = raw_rec and not self._prev_record
            play_edge = raw_play and not self._prev_play
            self._prev_record, self._prev_play = raw_rec, raw_play

            ev = ButtonEvents()
            if rec_edge and (now - self._last_record_t) >= self._debounce:
                self._last_record_t = now
                ev.record = True
            if play_edge and (now - self._last_play_t) >= self._debounce:
                self._last_play_t = now
                ev.play = True
            return ev
        except Exception:
            return ButtonEvents()

    # ── status ───────────────────────────────────────────────────
    def get_status(self) -> TrackerStatus:
        if not self._connected or self._vr is None:
            return TrackerStatus(detail="SteamVR not connected")
        try:
            import openvr
            poses = self._vr.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0,
                openvr.k_unMaxTrackedDeviceCount)

            # Base stations (lighthouses)
            base_states = []
            for i in range(openvr.k_unMaxTrackedDeviceCount):
                if self._vr.getTrackedDeviceClass(i) == \
                        openvr.TrackedDeviceClass_TrackingReference:
                    ok = poses[i].bDeviceIsConnected and poses[i].bPoseIsValid
                    base_states.append(DeviceState.OK if ok else DeviceState.WARN)
            bs1 = base_states[0] if len(base_states) > 0 else DeviceState.OFFLINE
            bs2 = base_states[1] if len(base_states) > 1 else DeviceState.OFFLINE

            # Tracker
            if self._tracker_index is None:
                self._find_tracker()
            tr_state, detail, battery = DeviceState.ERROR, "Tracker not found", None
            if self._tracker_index is not None:
                p = poses[self._tracker_index]
                if not p.bDeviceIsConnected:
                    tr_state, detail = DeviceState.ERROR, "Tracker disconnected"
                elif not p.bPoseIsValid:
                    tr_state, detail = DeviceState.WARN, "Tracking lost"
                else:
                    tr_state, detail = DeviceState.OK, "Tracking OK"
                    try:
                        battery = self._vr.getFloatTrackedDeviceProperty(
                            self._tracker_index,
                            openvr.Prop_DeviceBatteryPercentage_Float)
                    except Exception:
                        battery = None

            return TrackerStatus(
                steamvr=DeviceState.OK,
                tracker=tr_state,
                base_station_1=bs1,
                base_station_2=bs2,
                battery=battery,
                detail=detail,
            )
        except Exception as e:
            return TrackerStatus(steamvr=DeviceState.WARN,
                                 detail=f"Status error: {e}")
