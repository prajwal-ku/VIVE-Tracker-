"""
Live pose-check for the VIVE Tracker — verify position & orientation mapping.

It applies the SAME calibration the app uses (from robotplay.config) and prints,
every 0.2 s, both the RAW OpenVR pose and the CALIBRATED (what the app shows):

    RAW  pos(x, y, z)   euler(roll, pitch, yaw)
    CAL  pos(x, y, z)   euler(roll, pitch, yaw)

It locks the reference frame on the first valid frame (like clicking
"Calibrate · Lock Pose"). Press  c  to re-lock at the current pose, or  q  to quit.

HOW TO TEST (do one motion at a time, slowly, keeping the tracker steady):
  1. Move it straight UP        → only CAL Z should rise.
  2. Move it straight RIGHT     → only CAL X should change.
  3. Move it straight FORWARD   → only CAL Y should change.
  4. Roll it (tilt side-to-side)→ only CAL roll should change, same direction.
  5. Pitch it (nose up/down)    → only CAL pitch should change, same direction.
  6. Yaw it (turn left/right)   → only CAL yaw should change, same direction.

Tell me which line moves the wrong way (or which axis moves when it shouldn't)
and I'll fix exactly that — no guessing.
"""

import os
import sys
import time

# Allow running from the tools/ folder: put the project root on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

try:
    import openvr
except Exception as e:
    print("openvr not installed:", e)
    sys.exit(1)

from robotplay.config import CONFIG
from robotplay.core.calibration import Calibration
from robotplay.core.models import quat_from_matrix, quat_to_euler

try:
    import msvcrt  # Windows key detection
except Exception:
    msvcrt = None


def find_tracker(vr, poses):
    for require_connected in (True, False):
        for cls in (openvr.TrackedDeviceClass_GenericTracker,
                    openvr.TrackedDeviceClass_Controller):
            for i in range(openvr.k_unMaxTrackedDeviceCount):
                if vr.getTrackedDeviceClass(i) != cls:
                    continue
                if require_connected and not poses[i].bDeviceIsConnected:
                    continue
                return i
    return None


def read_raw(vr, idx):
    poses = vr.getDeviceToAbsoluteTrackingPose(
        openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)
    p = poses[idx]
    if not p.bPoseIsValid:
        return None
    m = p.mDeviceToAbsoluteTracking
    pos = np.array([m[0][3], m[1][3], m[2][3]])
    R = np.array([[m[0][0], m[0][1], m[0][2]],
                  [m[1][0], m[1][1], m[1][2]],
                  [m[2][0], m[2][1], m[2][2]]])
    return pos, R


def main() -> int:
    try:
        vr = openvr.init(openvr.VRApplication_Other)
    except Exception as e:
        print(f"Could not connect to SteamVR: {e}\nStart SteamVR first.")
        return 1

    cal = Calibration(
        world_conversion=CONFIG.calibration.world_conversion,
        model_offset_euler=CONFIG.calibration.model_offset_euler,
        axis_flip_orientation=CONFIG.calibration.axis_flip_orientation,
        axis_flip_position=CONFIG.calibration.axis_flip_position,
        orientation_invert_euler=CONFIG.calibration.orientation_invert_euler)

    print("Waiting for a tracked VIVE Tracker…  (Ctrl+C to quit)")
    locked = False
    try:
        while True:
            poses = vr.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0,
                openvr.k_unMaxTrackedDeviceCount)
            idx = find_tracker(vr, poses)
            raw = read_raw(vr, idx) if idx is not None else None

            if raw is None:
                print("  no valid tracker pose yet (base station / line of sight)…")
                time.sleep(0.4)
                continue

            pos_vr, R_vr = raw
            if not locked:
                cal.set_reference(pos_vr, R_vr)
                locked = True
                print("\n>>> LOCKED reference at current pose. "
                      "Now move ONE axis at a time.  (c = re-lock, q = quit)\n")

            # RAW euler for reference
            rr, rp, ry = quat_to_euler(quat_from_matrix(R_vr))
            # CALIBRATED (what the app shows)
            cpos, cR = cal.to_scene(pos_vr, R_vr)
            cr, cp, cy = quat_to_euler(quat_from_matrix(cR))

            print(f"RAW  pos({pos_vr[0]:+.3f} {pos_vr[1]:+.3f} {pos_vr[2]:+.3f})  "
                  f"euler(roll {rr:+6.1f}  pitch {rp:+6.1f}  yaw {ry:+6.1f})")
            print(f"CAL  pos({cpos[0]:+.3f} {cpos[1]:+.3f} {cpos[2]:+.3f})  "
                  f"euler(roll {cr:+6.1f}  pitch {cp:+6.1f}  yaw {cy:+6.1f})")
            print("-" * 74)

            if msvcrt and msvcrt.kbhit():
                key = msvcrt.getch().lower()
                if key == b"q":
                    break
                if key == b"c":
                    locked = False
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        openvr.shutdown()
    print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
