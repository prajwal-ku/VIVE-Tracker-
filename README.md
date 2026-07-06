# Robot Point & Play — VIVE Teaching System

A professional desktop application for **Point & Play robot teaching**. An
operator moves an **HTC VIVE Tracker** (tracked through **SteamVR**) in 3D space.
A physical **Point & Play button** on the hardware captures the current 6DoF pose
as a **waypoint**. The app visualises the motion live, records the taught path,
plays it back, and streams the resulting trajectory to an industrial robot —
either a **FAIRINO arm over TCP/IP** or any **G-code controller over a COM port**.

It is not a VR application; it runs on a standard Windows PC and renders a 3D
workspace that resembles industrial offline-programming software (ABB/FANUC/
KUKA/UR style).

---

> **Hardware required.** This application runs on a real HTC VIVE Tracker only —
> there is no simulated pose source. On start it connects to SteamVR/OpenVR; the
> connection-status board and live-pose panel show the true hardware state and
> nothing reports "OK" until the tracker is actually tracking. Waypoint capture is
> disabled while there is no valid signal.

## Highlights

- **Real hardware, real-time** — live 6DoF pose from SteamVR/OpenVR, physical
  pogo-pin buttons, auto-reconnect on signal loss.
- **Two distinct visualisations**, exactly as an operator needs:
  - **Motion trail** (cyan) — how the hand *actually* moved (freehand, curvy).
  - **Waypoint path** (white) — straight Cartesian segments between captured
    waypoints: the *intended robot trajectory*.
- **Playback engine** — animates a virtual tracker along the waypoint path
  (position lerp + orientation slerp) with Play / Pause / Stop / Replay and an
  adjustable speed.
- **Professional waypoint table** — number, timestamp, X/Y/Z, roll/pitch/yaw,
  with rename, delete, reorder and CSV/JSON export.
- **Robot abstraction with two swappable backends** — G-code/serial (works now)
  and FAIRINO TCP/IP (ready for `FAIRINO_SimMachine_v3.8.7`).
- **Connection-status board, live-pose panel, timestamped event log**, dark
  industrial theme.

---

## Install

```bash
pip install -r requirements.txt
```

`fairino` is **not** on PyPI — install the SDK that ships with your FAIRINO
controller / `FAIRINO_SimMachine` on the robot laptop to enable live FAIRINO
control. Without it the FAIRINO backend still **generates and previews** the exact
program that will be sent; only the live "Send" is disabled.

## Run

```bash
python main.py
```

---

## Quick start

1. Start **SteamVR**, power on the VIVE Tracker and both base stations.
2. Launch the app — it connects automatically. The *VIVE Tracker* panel turns
   green and the **Connection Status** board (SteamVR / Tracker / Hardware /
   Base 1 / Base 2) goes green. If SteamVR isn't up yet, start it and press
   **Connect Tracker**.
3. Move the tracker in space — the live pose and the 3D marker + orientation
   triad follow it in real time.
4. Press **Pin 3 / Grip** (the physical Point & Play button) to capture a
   waypoint. Each capture adds a gold sphere + label and a table row; a white
   straight-segment path connects the waypoints.
5. Press **Pin 4 / Trigger** to play the taught path (a virtual tracker animates
   along it). Space / Enter on the keyboard do the same, for convenience.
6. Pick a robot backend on the right, **Preview** the program, then **Export** or
   (with a real connection) **Send to Robot**.

> No tracker handy? You can still explore the UI and playback by loading demo
> data with **Session ▸ Load** on `examples/sample_session.json` — but live
> capture stays disabled until a real tracker is tracking.

### Hardware buttons

| Pin | Button | Action | OpenVR bitmask |
|-----|--------|--------|----------------|
| Pin 3 | Grip | Capture waypoint (Point & Play) | `1 << 2` |
| Pin 4 | Trigger | Play path | `1 << 33` |

Button presses are edge-detected and debounced (one click = one action).

---

## Connecting to the FAIRINO robot

Your VIVE tracker rig and `FAIRINO_SimMachine_v3.8.7` currently live on separate
laptops; this app is built to merge cleanly with the robot side later:

- Select **Backend ▸ FAIRINO (TCP/IP)** in the *Robot* panel.
- Set the controller/simulator **IP** (default `192.168.58.2`), velocity, tool
  and workpiece.
- Each captured waypoint becomes a `robot.MoveL([x,y,z,rx,ry,rz], tool, user, vel)`
  call via the `fairino` Python SDK. Use **Preview** to see the full program.
- On the robot laptop (where the `fairino` SDK is installed), **Connect** then
  **Send to Robot** executes the path.

The **Serial / G-code (COM)** backend works today with GRBL/Marlin-style
controllers: one `G1` linear move per waypoint over the selected COM port.

---

## Architecture

Everything is a small, loosely-coupled module — the UI never talks to hardware
directly, so new pose sources or robot transports slot in without rewrites.

```
main.py                      thin entry point (boots Qt, shows MainWindow)
robotplay/
├── config.py                all tunables: theme, scene, timers, button masks,
│                            robot defaults  → one shared CONFIG instance
├── core/
│   ├── models.py            TrackerData, Waypoint + quaternion/Euler maths
│   ├── logger.py            EventLogger (Qt-signal event feed)
│   ├── waypoint_manager.py  waypoints + motion trail, numpy accessors
│   ├── playback_engine.py   frame-driven path animation (lerp + slerp)
│   └── session_manager.py   save/load JSON, export CSV/JSON
├── tracker/
│   ├── base.py              TrackerInterface (abstraction) + status types
│   └── vive.py              ViveTracker (SteamVR/OpenVR, buttons, reconnect)
├── robot/
│   ├── base.py              RobotInterface (abstraction) + ConnectionParams
│   ├── serial_gcode.py      SerialGCodeRobot (G-code over COM)
│   └── fairino.py           FairinoRobot (MoveL over TCP/IP)
└── ui/
    ├── style.py             dark industrial QSS
    ├── viewport.py          Viewport3D (grid, axes, tracker, trail, path, …)
    ├── panels.py            ConnectionStatus / LivePose / EventLog panels
    ├── waypoint_table.py    editable waypoint grid
    ├── playback_controls.py transport bar + progress + read-out
    ├── robot_panel.py       backend selector + connection + actions
    └── main_window.py       wires all modules, owns the timers
```

### Extension points (designed-for, not yet implemented)

The abstractions above are the seams for a future digital twin: add a
`TrackerInterface` for OpenXR/network pose, add a `RobotInterface` for **ROS2 /
MoveIt / inverse kinematics / trajectory optimisation**, or add a robot-model
`GLMeshItem` to the viewport — none require touching existing modules.

---

## Controls

| Input | Action |
|-------|--------|
| Pin 3 / Grip | Capture waypoint (Point & Play) |
| Pin 4 / Trigger | Play path |
| Space | Capture waypoint (keyboard convenience) |
| Enter | Play path (keyboard convenience) |
| Ctrl+Z | Undo last waypoint |
| Drag / Scroll / Right-drag | Orbit / zoom / pan camera |
| Ctrl+N / Ctrl+S / Ctrl+O | New / Save / Load session |

## Build a standalone .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "RobotPointPlay" main.py
```

Output is in `dist/`.
