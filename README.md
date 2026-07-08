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
- **The real VIVE Tracker CAD in the 3D scene** — the official HTC VIVE Tracker
  3.0 model (bundled, tessellated from its STEP file) **translates and rotates in
  real time with the physical device**, lit by a custom high-ambient shader so
  it's clearly visible against the dark workspace. Playback reuses the same model
  as a magenta "ghost" gliding along the path. Swap in any `.stl` — or regenerate
  from a STEP — via the *CAD model* section.
- **Two distinct visualisations**, exactly as an operator needs:
  - **Motion trail** (cyan) — how the hand *actually* moved (freehand, curvy).
  - **Waypoint path** (white) — straight Cartesian segments between captured
    waypoints: the *intended robot trajectory*.
- **Playback engine** — animates a virtual tracker along the waypoint path
  (position lerp + orientation slerp) with Play / Pause / Stop / Replay and an
  adjustable speed.
- **Professional waypoint table** — number, timestamp, X/Y/Z, roll/pitch/yaw,
  with rename, delete, reorder and CSV/JSON export.
- **Hardware-driven teaching** — Pin 3 captures, Pin 4 plays. No manual
  capture/play buttons and no robot-connection panel clutter the UI; the window
  is a big 3D visualisation console. (The robot abstraction — G-code/serial and
  FAIRINO TCP/IP — stays in the codebase, ready to be triggered from hardware
  when the tracker rig and `FAIRINO_SimMachine_v3.8.7` merge.)
- **Loadable CAD** — drop a **workspace CAD** into the scene (a robot cell,
  table, fixture) and **swap the tracker CAD** for any model, via the *Scene*
  menu. STL and STEP (`.stp`) are both supported.
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
3. Move the tracker in space — the live pose and the 3D VIVE Tracker model
   (with its orientation triad) follow it in real time.
4. Press **Pin 3 / Grip** (the physical Point & Play button) to capture a
   waypoint. Each capture adds a gold sphere + label and a table row; a white
   straight-segment path connects the waypoints.
5. Press **Pin 4 / Trigger** to play the taught path (the tracker model animates
   along it). Space / Enter on the keyboard do the same, for convenience.
6. Review the taught path with the **Playback** transport, and manage waypoints
   in the table (rename / reorder / delete) or export via the **Session** menu.

> No tracker handy? You can still explore the UI and playback by loading demo
> data with **Session ▸ Load** on `examples/sample_session.json` — but live
> capture stays disabled until a real tracker is tracking.

### Calibration — lock the tracker's frame as the UI frame

The app does **not** impose its own X/Y/Z on you. Instead you define the frame:

- **Calibrate · Lock Pose** — hold the tracker in the orientation/position you
  want as *home*, then click. From that instant the tracker's current pose
  **becomes the UI's reference frame**: it snaps to the origin at the identity
  orientation, and everything after moves *relative* to that locked frame, so the
  on-screen model rotates and translates exactly like the real tracker in your
  hand. This is a full 6-DoF lock (`pₛ = R₀ᵀ·(p−p₀)`, `Rₛ = R₀ᵀ·R`). **Unlock**
  returns to the default gravity-up view. Captured waypoints are stored in the
  locked frame, which is ideal for teaching relative to a fixture or robot base.

  > Before locking, a default view is shown (SteamVR's Y-up mapped to the Z-up
  > scene). Lock replaces it with *your* frame — this is the intended workflow.

- **Model alignment (Roll / Pitch / Yaw + "+90 X/Y/Z")** — display-only rotation
  of the CAD mesh, in case its rest orientation doesn't look the way you hold the
  tracker at home. It never changes waypoint data. Once it looks right, copy the
  values into `model_offset_euler` in `robotplay/config.py` to make them default.

### Hardware buttons

| Pin | Button | Action | OpenVR bitmask |
|-----|--------|--------|----------------|
| Pin 3 | Grip | Capture waypoint (Point & Play) | `1 << 2` |
| Pin 4 | Trigger | Play path | `1 << 33` |

Button presses are edge-detected and debounced (one click = one action).

---

## Loading CAD into the scene

Use the **Scene** menu:

- **Load Workspace CAD…** — place a static environment model (robot cell, table,
  fixture) in the 3D scene. It is auto-scaled (millimetre CAD → metres), centred
  on the grid and rested on the ground. **Clear Workspace CAD** removes it.
- **Load Tracker CAD…** — replace the on-screen tracker with any model. **Reset
  Tracker CAD (VIVE 3.0)** restores the bundled default.

Both accept **STL** and **STEP** (`.stp` / `.step`). STEP is tessellated on load
with `gmsh` (install it with `pip install gmsh`); STL needs no extra dependency.

## Robot execution (hardware-driven)

Teaching and playback are driven entirely by the tracker's hardware buttons
(Pin 3 = capture, Pin 4 = play), so the UI has **no manual robot-connection
panel**. The robot abstraction still lives in the codebase — `SerialGCodeRobot`
(one `G1` linear move per waypoint over a COM port) and `FairinoRobot`
(`MoveL([x,y,z,rx,ry,rz], tool, user, vel)` over TCP/IP) — ready to be triggered
from the hardware path when the VIVE rig and `FAIRINO_SimMachine_v3.8.7` are
merged onto one machine. Waypoints can still be exported (Session ▸ Export) for
offline use.

---

## CAD model

The on-screen tracker is the **real HTC VIVE Tracker 3.0 CAD**, bundled at
`robotplay/assets/vive_tracker.stl` and loaded automatically — it translates and
rotates with the live pose and is reused as the magenta playback ghost. It is
rendered with a custom high-ambient shader so the model stays clearly lit from
every angle against the dark workspace.

- **Regenerate it from the official STEP** (e.g. after downloading a newer CAD):

  ```bash
  pip install gmsh
  python tools/convert_step_to_stl.py "VIVE_Tracker_3.0_3D.stp"
  ```

  This tessellates the STEP into a light binary STL (~22k triangles). `gmsh` is
  dev-only — it is **not** needed to run the app.

- **Use a different model**: point `tracker_stl_path` in `robotplay/config.py` at
  any `.stl` (binary or ASCII); it is auto-recentred and scaled to
  `tracker_model_size` (metres). If the STL is missing/unreadable, a procedural
  puck is drawn as a fallback.

The same mechanism will host a **robot arm model** later: convert its CAD to STL,
add a `GLMeshItem` to the viewport and drive it from a `RobotInterface` — the
seams are already there. When packaging with PyInstaller, include the asset:
`--add-data "robotplay/assets;robotplay/assets"`.

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
│   ├── calibration.py       Y-up→Z-up basis, zero reference, model offset
│   └── session_manager.py   save/load JSON, export CSV/JSON
├── tracker/
│   ├── base.py              TrackerInterface (abstraction) + status types
│   └── vive.py              ViveTracker (SteamVR/OpenVR, buttons, reconnect)
├── robot/                   retained for the FAIRINO merge (no UI panel now)
│   ├── base.py              RobotInterface (abstraction) + ConnectionParams
│   ├── serial_gcode.py      SerialGCodeRobot (G-code over COM)
│   └── fairino.py           FairinoRobot (MoveL over TCP/IP)
├── ui/
│   ├── style.py             dark industrial QSS
│   ├── viewport.py          Viewport3D (grid, axes, tracker, trail, path, CAD)
│   ├── tracker_model.py     tracker CAD model (bright shader, procedural fallback)
│   ├── mesh_loader.py       STL + STEP(.stp) → mesh loader (STEP via gmsh)
│   ├── panels.py            ConnectionStatus / LivePose / EventLog panels
│   ├── waypoint_table.py    editable waypoint grid
│   ├── playback_controls.py transport bar + progress + read-out
│   └── main_window.py       wires all modules, owns the timers
└── assets/
    └── vive_tracker.stl     bundled real VIVE Tracker 3.0 mesh (from STEP)
tools/
└── convert_step_to_stl.py  regenerate the mesh from the official STEP (dev-only)
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
