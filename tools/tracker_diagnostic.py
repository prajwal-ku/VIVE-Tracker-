"""
Live VIVE Tracker / SteamVR diagnostic.

Run this while you power on the base station and hold the tracker in view — it
polls OpenVR twice a second and prints exactly what SteamVR reports for every
device, so you can see the precise moment the tracker starts tracking.

    python tools/tracker_diagnostic.py

What to look for:
  * BaseStation  connected=1                → the base station is seen by SteamVR
  * Tracker      connected=1  valid=1       → the tracker is TRACKING (ready!)
  * result=Running_OK                       → full 6-DoF lock

If the Tracker line never shows valid=1 / Running_OK, the base station isn't
tracking it (power / line-of-sight / pairing). The main app can only show a pose
once this script shows valid=1 — there is no pose to read before then.

Press Ctrl+C to stop.
"""

import sys
import time

# Windows consoles default to cp1252 and choke on non-ASCII; force UTF-8 and
# never crash on an un-encodable glyph.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import openvr
except Exception as e:
    print("openvr not installed:", e)
    sys.exit(1)

CLASS = {0: "-", 1: "HMD", 2: "Controller", 3: "Tracker", 4: "BaseStation"}
RESULT = {
    0: "Uninitialized", 1: "Uninitialized",
    100: "Calibrating_InProgress", 101: "Calibrating_OutOfRange",
    200: "Running_OK", 201: "Running_OutOfRange",
    300: "Fallback_RotationOnly",
}


def main() -> int:
    print("Connecting to SteamVR/OpenVR…")
    try:
        vr = openvr.init(openvr.VRApplication_Other)
    except Exception as e:
        print(f"Could not connect to SteamVR: {e}")
        print("→ Start SteamVR first, then run this again.")
        return 1

    print("Connected. Polling every 0.5 s — power the base station and hold the "
          "tracker in view. Ctrl+C to stop.\n")
    try:
        while True:
            poses = vr.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0,
                openvr.k_unMaxTrackedDeviceCount)
            lines = []
            tracking = False
            for i in range(openvr.k_unMaxTrackedDeviceCount):
                cls = vr.getTrackedDeviceClass(i)
                if cls == 0:
                    continue
                p = poses[i]
                m = p.mDeviceToAbsoluteTracking
                if p.bPoseIsValid:
                    pos = f"({m[0][3]:+.2f}, {m[1][3]:+.2f}, {m[2][3]:+.2f})"
                else:
                    pos = "-"
                if cls == openvr.TrackedDeviceClass_GenericTracker and \
                        p.bPoseIsValid and p.eTrackingResult == 200:
                    tracking = True
                lines.append(
                    f"  dev {i:2d}  {CLASS.get(cls, cls):11s} "
                    f"connected={int(p.bDeviceIsConnected)} "
                    f"valid={int(p.bPoseIsValid)} "
                    f"result={RESULT.get(p.eTrackingResult, p.eTrackingResult):16s} "
                    f"pos={pos}")
            stamp = time.strftime("%H:%M:%S")
            head = "TRACKING - ready to capture" if tracking else "waiting..."
            print(f"[{stamp}] {head}")
            print("\n".join(lines) if lines else "  (no devices reported)")
            print("-" * 78)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        openvr.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
