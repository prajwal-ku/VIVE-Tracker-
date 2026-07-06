"""
Calibration — adopt the tracker's own frame as the UI coordinate frame.

The important idea (per the operator's requirement): the app must NOT impose a
fixed X/Y/Z on the tracker. Instead you hold the tracker in the orientation you
want as "home", press **Calibrate / Lock**, and from that instant the tracker's
current pose *becomes* the UI's reference frame:

    • its position at lock  → the workspace origin
    • its orientation at lock → the identity orientation (model sits at rest)
    • every later pose is reported **relative to that locked frame**, so moving/
      rotating the real tracker moves/rotates the on-screen model the same way.

This is a full 6-DoF frame lock:  pₛ = R₀ᵀ·(p − p₀),  Rₛ = R₀ᵀ·R.
At the lock instant R = R₀ and p = p₀, so pₛ = 0 and Rₛ = I.

Before any lock (or after Clear) there is no reference to adopt, so a sensible
default view is shown instead: OpenVR's Y-up frame mapped to the Z-up scene so
"up" is up. Press Calibrate to replace it with your frame.

The model mount offset (roll/pitch/yaw) is a separate, display-only rotation of
the CAD mesh — handy if the mesh's rest orientation doesn't look the way you hold
the tracker at home. It never affects captured waypoint data.
"""

from __future__ import annotations

import numpy as np

from .models import euler_to_quat, quat_to_matrix


def rotation_from_euler_deg(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """(roll, pitch, yaw) degrees → 3x3 rotation matrix (reuses the model maths)."""
    return quat_to_matrix(euler_to_quat(roll, pitch, yaw))


class Calibration:
    #: Default (pre-lock) world-basis conversions: OpenVR frame → scene frame.
    _BASIS = {
        # Rx(+90°): (x, y, z)_vr → (x, −z, y)_scene   [Y-up → Z-up]
        "y_up_to_z_up": np.array([[1.0, 0.0, 0.0],
                                  [0.0, 0.0, -1.0],
                                  [0.0, 1.0, 0.0]]),
        "none": np.eye(3),
    }

    def __init__(self, world_conversion: str = "y_up_to_z_up",
                 model_offset_euler: tuple = (0.0, 0.0, 0.0),
                 axis_flip: tuple = (1.0, 1.0, 1.0)):
        self.C = self._BASIS.get(world_conversion, np.eye(3))
        self.model_R = rotation_from_euler_deg(*model_offset_euler)
        self._model_euler = tuple(model_offset_euler)
        # Per-axis sign flip applied to every scene pose (position + orientation).
        # A diagonal ±1 matrix; F·R·F keeps orientation a proper rotation.
        self.F = np.diag([float(s) for s in axis_flip])

        # Locked reference (raw OpenVR pose captured at Calibrate).
        self._ref_R0 = np.eye(3)
        self._ref_p0 = np.zeros(3)
        self._has_ref = False

    # ── pose transform (raw OpenVR → scene) ─────────────────────
    def to_scene(self, pos_vr: np.ndarray, R_vr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pos_vr = np.asarray(pos_vr, dtype=float)
        R_vr = np.asarray(R_vr, dtype=float)
        if self._has_ref:
            # Locked. POSITION moves in room/world space (only the origin is
            # taken from the lock) so lifting the tracker always moves the model
            # up, regardless of how it was oriented at calibration. ORIENTATION
            # is locked to the tracker's frame (identity at the lock pose).
            pos = self.C @ (pos_vr - self._ref_p0)
            R = self._ref_R0.T @ R_vr
        else:
            # No lock yet — show a gravity-up default (Y-up → Z-up).
            pos = self.C @ pos_vr
            R = self.C @ R_vr @ self.C.T
        # Optional per-axis flip (e.g. swap Z+ / Z-), applied last so it affects
        # both the locked and default views consistently.
        pos = self.F @ pos
        R = self.F @ R @ self.F
        return pos, R

    # ── frame lock ──────────────────────────────────────────────
    def set_reference(self, pos_vr: np.ndarray, R_vr: np.ndarray) -> None:
        """Adopt the current raw tracker pose as the UI coordinate frame."""
        self._ref_p0 = np.asarray(pos_vr, dtype=float).copy()
        self._ref_R0 = np.asarray(R_vr, dtype=float).copy()
        self._has_ref = True

    def clear_reference(self) -> None:
        self._has_ref = False
        self._ref_R0 = np.eye(3)
        self._ref_p0 = np.zeros(3)

    @property
    def has_reference(self) -> bool:
        return self._has_ref

    # ── model mount offset (display only) ───────────────────────
    def set_model_offset_euler(self, roll: float, pitch: float, yaw: float) -> None:
        self._model_euler = (roll, pitch, yaw)
        self.model_R = rotation_from_euler_deg(roll, pitch, yaw)

    @property
    def model_offset_euler(self) -> tuple:
        return self._model_euler

    def model_rotation(self, R_scene: np.ndarray) -> np.ndarray:
        """The drawn-model orientation: tracker orientation · mount offset."""
        return np.asarray(R_scene, dtype=float) @ self.model_R
