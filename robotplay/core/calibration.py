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

from .models import euler_to_quat, quat_to_matrix, quat_from_matrix, quat_to_euler


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
                 axis_flip_orientation: tuple = (1.0, 1.0, 1.0),
                 axis_flip_position: tuple = (1.0, 1.0, 1.0),
                 orientation_invert_euler: tuple = (1.0, 1.0, 1.0)):
        self.C = self._BASIS.get(world_conversion, np.eye(3))
        self.model_R = rotation_from_euler_deg(*model_offset_euler)
        self._model_euler = tuple(model_offset_euler)
        # Separate ±1 sign flips for facing (orientation) and movement (position),
        # since a setup can need one without the other. Diagonal matrices;
        # Fo·R·Fo keeps orientation a proper rotation.
        self.Fo = np.diag([float(s) for s in axis_flip_orientation])
        self.Fp = np.diag([float(s) for s in axis_flip_position])
        # Per-rotation-axis sign (roll, pitch, yaw): negate one angle to un-invert
        # just that rotation without disturbing the others.
        self._inv_euler = tuple(float(s) for s in orientation_invert_euler)

        # Locked reference (raw OpenVR pose captured at Calibrate).
        self._ref_R0 = np.eye(3)
        self._ref_p0 = np.zeros(3)
        self._has_ref = False

    # ── pose transform (raw OpenVR → scene) ─────────────────────
    def to_scene(self, pos_vr: np.ndarray, R_vr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pos_vr = np.asarray(pos_vr, dtype=float)
        R_vr = np.asarray(R_vr, dtype=float)
        if self._has_ref:
            # Locked. Both POSITION and ORIENTATION are handled in room/world
            # space and mapped through the SAME Y-up→Z-up basis C, so the model
            # mirrors the physical tracker consistently (spin about the room's
            # vertical → model spins about the scene's vertical, etc.).
            #   position:    p_scene = C·(p − p₀)             (origin at lock)
            #   orientation: ΔR_world = R·R₀ᵀ  (room-frame rotation since lock)
            #                R_scene  = C·ΔR_world·Cᵀ         (identity at lock)
            pos = self.C @ (pos_vr - self._ref_p0)
            R = self.C @ (R_vr @ self._ref_R0.T) @ self.C.T
        else:
            # No lock yet — show a gravity-up default (Y-up → Z-up).
            pos = self.C @ pos_vr
            R = self.C @ R_vr @ self.C.T
        # Optional per-axis flips, applied last — separately for movement and
        # facing so fixing one never inverts the other.
        pos = self.Fp @ pos
        R = self.Fo @ R @ self.Fo
        # Optional per-rotation-axis invert (e.g. un-flip pitch only): decompose
        # to roll/pitch/yaw, negate the requested angle(s), recompose.
        if self._inv_euler != (1.0, 1.0, 1.0):
            roll, pitch, yaw = quat_to_euler(quat_from_matrix(R))
            sr, sp, sy = self._inv_euler
            R = rotation_from_euler_deg(sr * roll, sp * pitch, sy * yaw)
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
