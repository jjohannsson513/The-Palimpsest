# Scene Setup Guide
## The Palimpsest — Godot 4.2  (Spherical Voronoi World)

The sphere world uses 3D nodes throughout. There is no TileMap.
Follow these steps exactly in the Godot editor.

---

## Step 1 — Create the Main scene

1. Open Godot 4.2: `godot4 --path ~/projects/palimpsest/godot/`
2. In the **Scene** panel, click **New Scene**
3. Choose **Node3D** as root type
4. Rename the root node to `Main`
5. Save as `scenes/Main.tscn`

---

## Step 2 — Build the scene tree

Create this exact hierarchy by right-clicking each parent and choosing
"Add Child Node":

```
Main                            [Node3D]        (root)
└── GameWorld                   [Node3D]        scripts/world/GameWorld.gd
    ├── PythonBridge            [Node]          scripts/core/PythonBridge.gd
    ├── TurnManager             [Node]          scripts/core/TurnManager.gd
    ├── WorldSphere             [Node3D]        scripts/world/WorldSphere.gd
    └── CameraOrbit             [Node3D]        scripts/core/CameraOrbit.gd
        └── Camera3D            [Camera3D]      (no script)
UIController                    [CanvasLayer]   scripts/ui/UIController.gd
└── HUD                         [Control]
    ├── PhaseLabel              [Label]
    ├── TurnLabel               [Label]
    ├── TimerBar                [ProgressBar]
    ├── EndTurnButton           [Button]
    └── SpeedSelector           [OptionButton]
    CellInspector               [PanelContainer]
    └── InspectorLabel          [Label]
    AnalyticsOverlay            [PanelContainer]
    └── AnalyticsLabel          [Label]
```

**UIController** is a sibling of GameWorld under Main, not a child.

---

## Step 3 — Attach scripts

For each node that has a script path listed above:
1. Select the node
2. In the Inspector, click the **Script** field → **Load**
3. Navigate to the script file

Scripts are in `res://scripts/` mirroring the directory layout shown above.

---

## Step 4 — Camera3D properties

Select `Camera3D`:

| Property | Value |
|---|---|
| Position Z | 25.0 |
| Rotation X | 0° (CameraOrbit controls this) |
| FOV | 25° (long focal length for quasi-isometric feel) |
| Near | 0.1 |
| Far | 500.0 |
| Projection | Perspective |

The `CameraOrbit.gd` script controls all camera movement automatically.
Do not add any other camera scripts.

---

## Step 5 — WorldSphere properties

Select `WorldSphere`:

| Property | Value |
|---|---|
| Height Extrusion | 0.08 |
| Ocean Depth | 0.04 |

These can be tuned after first run. No mesh or material needed —
both are built at runtime when Python sends `procgen.apply_map`.

---

## Step 6 — Lighting

Right-click `Main` → Add Child Node → `DirectionalLight3D`:

| Property | Value |
|---|---|
| Rotation X | -45° |
| Rotation Y | -30° |
| Color | `#FFF4E0` (warm white) |
| Energy | 1.2 |
| Shadow Enabled | true |

Add a second `DirectionalLight3D` for fill:

| Property | Value |
|---|---|
| Rotation X | 30° |
| Rotation Y | 150° |
| Color | `#C0D0FF` (cool blue fill) |
| Energy | 0.35 |
| Shadow Enabled | false |

---

## Step 7 — Environment

Right-click `Main` → Add Child Node → `WorldEnvironment`:
- In Inspector, create a new **Environment** resource
- **Background Mode**: Sky
- **Sky**: Create a new **ProceduralSkyMaterial**
  - **Sky Top Color**: `#0A0F1C`
  - **Sky Horizon Color**: `#1A2A4A`
  - **Ground Bottom Color**: `#0A0A0A`
- **Ambient Light Source**: Sky
- **Ambient Light Energy**: 0.4

---

## Step 8 — Wire UIController signals

Select `UIController` in the scene tree. In the **Node** panel → **Signals**:

| Signal | Connect to | Method |
|---|---|---|
| `EndTurnButton.pressed` | UIController | `_on_end_turn_pressed` |
| `SpeedSelector.item_selected` | UIController | `_on_speed_changed` |

Then in `GameWorld.gd`'s `_ready()`, add this after the existing wiring:

```gdscript
var ui := get_node("../UIController")
if ui:
    ui.connect_to_systems(turn_mgr, self, world_sphere)
```

---

## Step 9 — Verify the scene loads

Run the project with Python bridge **not** running:

```bash
godot4 --path ~/projects/palimpsest/godot/
```

Expected behaviour:
- Black sky with stars (procedural sky)
- No sphere visible yet (built at runtime)
- Bridge logs warning every 2s: `could not connect to /tmp/palimpsest.sock`
- HUD visible: "PLANNING / Turn 0 / End Turn button"
- No crashes

Now start Python (separate terminal):

```bash
cd ~/projects/palimpsest
source .venv/bin/activate
python3 -m palimpsest.python.bridge.server --cells 1000 --civs 6
```

Expected bridge log:
```
INFO  Building sphere: 1000 cells …
INFO  Sphere built: 1000 cells, avg 5.99 neighbors, radius=10.00
INFO  === Tectonic simulation start ===
INFO  Generated 14 plates …
INFO  Simulating 150 timesteps …
INFO  Thermal erosion (40 passes) …
INFO  Hydraulic erosion (20 passes) …
INFO  === Tectonic done: 38% ocean ===
INFO  Computing climate …
INFO  World ready: 1000 cells, 38% ocean, 6 civs
INFO  Sent map payload (~3200 KB)
INFO  Sent institutions: 6 civs
```

Godot then builds the sphere mesh and the globe appears.

---

## Configuring world size

The bridge accepts CLI flags:

```bash
# Small world — fast, good for testing
python3 -m palimpsest.python.bridge.server --cells 500

# Standard — recommended default
python3 -m palimpsest.python.bridge.server --cells 1000

# Rich geography — more demanding
python3 -m palimpsest.python.bridge.server --cells 1500

# Fixed seed — deterministic world for development
python3 -m palimpsest.python.bridge.server --cells 1000 --seed 42
```

---

## Directory layout (complete)

```
palimpsest/
├── godot/
│   ├── project.godot
│   ├── scenes/
│   │   └── Main.tscn
│   ├── scripts/
│   │   ├── core/
│   │   │   ├── Institution.gd
│   │   │   ├── TurnManager.gd
│   │   │   ├── PythonBridge.gd
│   │   │   └── CameraOrbit.gd
│   │   ├── entities/
│   │   │   ├── City.gd
│   │   │   ├── Army.gd
│   │   │   ├── Dynasty.gd
│   │   │   └── BeliefSystem.gd
│   │   ├── world/
│   │   │   ├── WorldSphere.gd
│   │   │   └── GameWorld.gd
│   │   └── ui/
│   │       └── UIController.gd
│   └── assets/
│       ├── icons/
│       └── environment/
└── python/
    ├── pyproject.toml
    ├── __init__.py
    ├── bridge/
    │   ├── protocol.py
    │   └── server.py
    ├── institutions/
    │   ├── model.py
    │   └── legitimacy.py
    ├── beliefs/
    │   ├── karma.py
    │   └── memory.py
    ├── agents/
    │   ├── council.py
    │   ├── sphere_utils.py
    │   └── lenses/
    │       ├── expansion.py
    │       ├── military.py
    │       ├── diplomatic.py
    │       └── economic.py
    ├── analytics/
    │   └── pipeline.py
    ├── procgen/
    │   ├── __init__.py       ← generate_world() entry point
    │   ├── sphere.py         ← Fibonacci + SphericalVoronoi
    │   ├── tectonics.py      ← full plate simulation
    │   ├── climate.py        ← temperature/moisture/terrain
    │   ├── resources.py      ← terrain-affinity resource placement
    │   └── institutions.py   ← starting civs/dynasties/beliefs
    └── tests/
        ├── test_palimpsest.py
        └── test_sphere_pipeline.py
```
