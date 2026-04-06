# The Palimpsest — Implementation Plan
## From bare Debian 12 to running prototype

---

## Prerequisites assumed

- Debian 12 (Bookworm) with a desktop environment (X11 or Wayland)
- Python 3.11+ installed (`python3 --version` to confirm; 3.11 is in Bookworm's repos)
- `sudo` access
- Internet connection for the initial downloads
- A directory where you want the project to live, referred to below as `~/projects/`

---

## Phase 0 — System packages

These are one-time installs that won't need to change.

```bash
sudo apt update && sudo apt install -y \
    git \
    unzip \
    wget \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential
```

Verify:

```bash
python3 --version    # must be 3.11 or higher
git --version
```

---

## Phase 1 — Get Godot 4

Godot 4 is not in Debian's apt repos. Download the official Linux AppImage directly.

```bash
mkdir -p ~/tools && cd ~/tools

wget https://github.com/godotengine/godot/releases/download/4.2.2-stable/Godot_v4.2.2-stable_linux.x86_64.zip

unzip Godot_v4.2.2-stable_linux.x86_64.zip

chmod +x Godot_v4.2.2-stable_linux.x86_64

sudo mv Godot_v4.2.2-stable_linux.x86_64 /usr/local/bin/godot4
```

Verify:

```bash
godot4 --version
# Expected: 4.2.2.stable.official
```

If your Debian system is running without a GPU driver or in a headless VM, append
`--rendering-driver opengl3_es` when launching Godot to force the compatibility renderer.

---

## Phase 2 — Project layout

Create the project root and clone or copy the scripts into it. If you are working
from the files produced in this session, the target layout is:

```
~/projects/palimpsest/
├── docs/
│   └── ARCHITECTURE.md
├── godot/
│   ├── project.godot               ← you will create this in Phase 4
│   ├── scenes/
│   │   └── Main.tscn               ← you will create this in Phase 4
│   ├── scripts/
│   │   ├── core/
│   │   │   ├── Institution.gd
│   │   │   ├── TurnManager.gd
│   │   │   └── PythonBridge.gd
│   │   ├── entities/
│   │   │   ├── City.gd
│   │   │   ├── Army.gd
│   │   │   ├── Dynasty.gd
│   │   │   └── BeliefSystem.gd
│   │   └── world/
│   │       ├── GameWorld.gd
│   │       └── WorldMap.gd
│   └── assets/
│       └── tiles/                  ← placeholder art goes here
└── python/
    ├── __init__.py
    ├── pyproject.toml
    ├── bridge/
    │   ├── __init__.py
    │   ├── protocol.py
    │   └── server.py
    ├── institutions/
    │   ├── __init__.py
    │   ├── model.py
    │   └── legitimacy.py
    ├── beliefs/
    │   ├── __init__.py
    │   ├── karma.py
    │   └── memory.py
    ├── agents/
    │   ├── __init__.py
    │   ├── council.py
    │   └── lenses/
    │       ├── __init__.py
    │       ├── expansion.py
    │       ├── military.py
    │       ├── diplomatic.py
    │       └── economic.py
    ├── analytics/
    │   ├── __init__.py
    │   └── pipeline.py
    ├── procgen/
    │   ├── __init__.py
    │   ├── terrain.py
    │   ├── resources.py
    │   └── institutions.py
    └── tests/
        ├── __init__.py
        └── test_palimpsest.py
```

Create the skeleton:

```bash
mkdir -p ~/projects/palimpsest/{docs,godot/{scenes,scripts/{core,entities,world},assets/tiles},python/{bridge,institutions,beliefs,agents/lenses,analytics,procgen,tests}}

# Touch all __init__.py files
touch ~/projects/palimpsest/python/__init__.py
touch ~/projects/palimpsest/python/{bridge,institutions,beliefs,agents,agents/lenses,analytics,procgen,tests}/__init__.py
```

---

## Phase 3 — Python environment

Set up a virtual environment rooted at the project level so the package is
importable as `palimpsest.python.*` — matching how the scripts reference each other.

```bash
cd ~/projects/palimpsest

python3 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with dev tools
pip install -e "python/.[dev]"
```

Verify the install:

```bash
python3 -c "from palimpsest.python.bridge.protocol import Topics; print(Topics.PLANNING_START)"
# Expected: phase.planning_start
```

---

## Phase 4 — Place the scripts

Copy each file from this session into the correct location. The table below maps
every file to its destination path relative to `~/projects/palimpsest/`.

### Godot scripts

| Source file (from this session) | Destination |
|---|---|
| `Institution.gd` | `godot/scripts/core/Institution.gd` |
| `TurnManager.gd` | `godot/scripts/core/TurnManager.gd` |
| `PythonBridge.gd` | `godot/scripts/core/PythonBridge.gd` |
| `City.gd` | `godot/scripts/entities/City.gd` |
| `Army.gd` | `godot/scripts/entities/Army.gd` |
| `Dynasty.gd` | `godot/scripts/entities/Dynasty.gd` |
| `BeliefSystem.gd` | `godot/scripts/entities/BeliefSystem.gd` |
| `WorldMap.gd` | `godot/scripts/world/WorldMap.gd` |
| `GameWorld.gd` | `godot/scripts/world/GameWorld.gd` |

### Python scripts

| Source file (from this session) | Destination |
|---|---|
| `bridge/protocol.py` | `python/bridge/protocol.py` |
| `bridge/server.py` | `python/bridge/server.py` |
| `institutions/model.py` | `python/institutions/model.py` |
| `institutions/legitimacy.py` | `python/institutions/legitimacy.py` |
| `beliefs/karma.py` | `python/beliefs/karma.py` |
| `beliefs/memory.py` | `python/beliefs/memory.py` |
| `agents/council.py` | `python/agents/council.py` |
| `agents/lenses/expansion.py` | `python/agents/lenses/expansion.py` |
| `agents/lenses/military.py` | `python/agents/lenses/military.py` |
| `agents/lenses/diplomatic.py` | `python/agents/lenses/diplomatic.py` |
| `agents/lenses/economic.py` | `python/agents/lenses/economic.py` |
| `analytics/pipeline.py` | `python/analytics/pipeline.py` |
| `procgen/terrain.py` | `python/procgen/terrain.py` |
| `procgen/resources.py` | `python/procgen/resources.py` |
| `procgen/institutions.py` | `python/procgen/institutions.py` |
| `tests/test_palimpsest.py` | `python/tests/test_palimpsest.py` |
| `pyproject.toml` | `python/pyproject.toml` |

### Docs

| Source file | Destination |
|---|---|
| `ARCHITECTURE.md` | `docs/ARCHITECTURE.md` |

---

## Phase 5 — Verify Python: run the test suite

Before touching Godot, confirm the Python layer is clean.

```bash
cd ~/projects/palimpsest
source .venv/bin/activate
pytest python/tests/test_palimpsest.py -v
```

Expected output: all tests pass. The suite covers protocol round-trips,
institution phase logic, legitimacy math, procgen determinism and schema,
memory encoding, karma, and all four AI lenses.

If `pytest` is not found, the editable install didn't complete. Re-run:

```bash
pip install -e "python/.[dev]"
```

---

## Phase 6 — Create the Godot project

Godot needs a `project.godot` config file and a Main scene. These cannot be
generated by the Python side — they must be created through Godot's UI or
written by hand. The minimal hand-written versions are below.

### 6a. project.godot

Create `godot/project.godot`:

```ini
; Engine configuration file.
; Generated for Godot 4.2

[application]

config/name="The Palimpsest"
config/description="Turn-based strategy with institution simulation"
run/main_scene="res://scenes/Main.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")

[display]

window/size/viewport_width=1280
window/size/viewport_height=800
window/stretch/mode="canvas_items"

[rendering]

renderer/rendering_method="gl_compatibility"
textures/canvas_textures/default_texture_filter=0
```

### 6b. Main.tscn (minimal scene tree)

Create `godot/scenes/Main.tscn`. This wires the scene tree that `GameWorld.gd`
expects via `@onready`:

```
[gd_scene format=3]

[node name="Main" type="Node"]

[node name="GameWorld" type="Node" parent="."]
script = ExtResource("res://scripts/world/GameWorld.gd")

[node name="PythonBridge" type="Node" parent="GameWorld"]
script = ExtResource("res://scripts/core/PythonBridge.gd")

[node name="TurnManager" type="Node" parent="GameWorld"]
script = ExtResource("res://scripts/core/TurnManager.gd")

[node name="WorldMap" type="TileMap" parent="GameWorld"]
script = ExtResource("res://scripts/world/WorldMap.gd")
```

In practice, it is easier to create this scene in the Godot editor:

1. Launch Godot: `godot4 --path ~/projects/palimpsest/godot/`
2. Create a new scene with a plain `Node` as root; name it `Main`
3. Add child nodes as described above and attach the scripts manually
4. Save as `scenes/Main.tscn`

### 6c. TileSet placeholder

`WorldMap.gd` calls `set_cell(LAYER_TERRAIN, offset, 0, ...)` — source ID 0 must
exist in the TileMap's TileSet. For the prototype:

1. Select the `WorldMap` node in the editor
2. In the Inspector, create a new TileSet resource
3. Add one TileSetAtlasSource (source ID 0) pointing to any placeholder PNG
   (a flat colour grid works fine)
4. The atlas just needs tiles at coordinates `(0,0)` through `(7,2)` to cover
   terrain IDs 0–18; they can all be identical colour blocks for now

---

## Phase 7 — Verify Godot loads

Launch Godot with the project open and no Python bridge yet:

```bash
godot4 --path ~/projects/palimpsest/godot/
```

Expected behaviour:
- The scene opens; the WorldMap renders a fallback hex grid (seeded terrain,
  no Python data)
- `GameWorld._ready()` runs; the bridge starts its background thread and
  attempts to connect to `/tmp/palimpsest.sock`
- Because Python is not running, the bridge logs a warning every 2 seconds:
  `PythonBridge: could not connect to /tmp/palimpsest.sock`
- Everything else works: the fallback map is visible, TurnManager is in
  PLANNING phase

This confirms the Godot side is functional independently.

---

## Phase 8 — Run the full stack

Always start Python first. Godot reconnects automatically.

```bash
# Terminal 1 — Python bridge
cd ~/projects/palimpsest
source .venv/bin/activate
python3 -m palimpsest.python.bridge.server
```

Wait for: `Palimpsest bridge listening on /tmp/palimpsest.sock`

```bash
# Terminal 2 — Godot
godot4 --path ~/projects/palimpsest/godot/
```

### Expected startup sequence

```
[Python]  Palimpsest bridge listening on /tmp/palimpsest.sock
[Python]  Godot connected
[Python]  Handshake: version=0.2 caps=['ai', 'analytics', 'procgen', 'beliefs']
[Python]  Sent map: 589 tiles (seed=...)
[Python]  Sent starting institutions: 6 civs
[Godot]   PythonBridge: bridge_ready signal emitted
[Godot]   GameWorld: applying procgen map
[Godot]   GameWorld: applying starting institutions
[Godot]   TurnManager: entering PLANNING phase tick=0
```

### Startup failure checklist

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: palimpsest` | Package not installed | `pip install -e "python/.[dev]"` from project root |
| Godot: `could not connect` loop | Python not running first | Always start Python before Godot |
| Godot: black screen | TileSet not configured | Add placeholder atlas in editor (Phase 6c) |
| Python: `ImportError` in lenses | `__init__.py` missing | Re-run the touch command from Phase 2 |
| Socket permission error | `/tmp/palimpsest.sock` stale | `rm /tmp/palimpsest.sock` then restart Python |

---

## Phase 9 — Development workflow

After initial setup, the daily loop is:

```bash
# Start Python bridge (watches for code changes with --reload if you add watchdog)
source ~/projects/palimpsest/.venv/bin/activate
python3 -m palimpsest.python.bridge.server

# Run tests after any Python change
pytest python/tests/test_palimpsest.py -v

# Godot auto-reloads GDScript on file save when running in the editor
# No restart needed for GDScript changes while the editor is open
```

For iterating on AI lenses specifically, you can restart the Python process
without restarting Godot — Godot's bridge will reconnect automatically within
2 seconds.

---

## Milestone roadmap

These are the next development steps in priority order, mapping to the GDD
development phases from the design document.

### Milestone 1 — Visual map (Phase 1)

**Goal:** Tiles render with distinct terrain colours; hex grid is navigable.

- Create a real TileSet with 19 colour-coded terrain tiles (flat colours are
  fine — art comes later)
- Implement camera pan and zoom in a `CameraController.gd` script attached
  to a `Camera2D` node
- Add click-to-inspect: clicking a tile shows its terrain, resources, and
  owner in a panel

**Files to create:** `scripts/ui/CameraController.gd`, `scripts/ui/TileInspector.gd`,
`scenes/UI.tscn`

### Milestone 2 — Armies move on the map (Phase 1)

**Goal:** AI settler armies visibly move each turn; the player can click to
select and manually order their own.

- Add `Sprite2D` or `Polygon2D` nodes as unit markers in `GameWorld`
- Wire `army_moved` signal to update marker positions
- Add a selection system: click a unit to highlight it, click a tile to
  order a move
- The Planning Phase "End Turn" button triggers `TurnManager.player_end_turn()`

**Files to create:** `scripts/ui/UnitMarker.gd`, `scripts/ui/SelectionManager.gd`

### Milestone 3 — Cities appear and grow (Phase 2)

**Goal:** AI civs found settlements; they visually appear on the map and
display a name label. Population ticks each turn.

- Wire `city_founded` signal to spawn a city marker sprite + label
- Implement `City.process_turn_growth()` call inside `GameWorld._on_turn_completed()`
- Add a city inspector panel showing tier, population, yields, and civic
  identity vector
- Hook `City.try_tier_up()` and emit a UI notification when a tier transition
  happens

**Files to create:** `scripts/ui/CityMarker.gd`, `scripts/ui/CityInspector.gd`

### Milestone 4 — Turn UI and planning controls (Phase 1–2)

**Goal:** The player has a real HUD: phase label, turn counter, execution
timer bar, and End Turn button.

- Create `scripts/ui/UIController.gd` — subscribes to `TurnManager` signals
- Execution timer bar drains visually during Execution Phase
- Phase label switches between `PLANNING` and `EXECUTION` with a colour change
- Speed selector (Short / Medium / Long / Unlimited) in a settings panel

**Files to create:** `scripts/ui/UIController.gd`, `scenes/HUD.tscn`

### Milestone 5 — Dynasty and courtiers (Phase 3)

**Goal:** Each civ has a named ruler. Hovering a civ's territory shows their
dynasty name and ruler. Faction pressure is displayed in a civ overview panel.

- Wire `Dynasty.gd` into `GameWorld` — one dynasty per civ registered on
  `procgen.apply_institutions`
- Create a `CivOverview` panel: ruler name, dynasty, faction pressure bars,
  karma indicator
- Implement basic succession: when a ruler "ages out" (tick counter), call
  `Dynasty.succeed()` and surface a notification

**Files to create:** `scripts/ui/CivOverview.gd`

### Milestone 6 — Research and tradition stubs (Phase 4)

**Goal:** A minimal tech tree panel. The player can queue one research item;
progress ticks each turn.

- Add `research_progress` and `active_research` fields to each civ's state
- Create a `ResearchPanel.gd` listing the seven affinity branches with
  placeholder nodes
- Wire research progress into the Python analytics pipeline so it appears
  in metrics

### Milestone 7 — Dynamic events (Phase 5)

**Goal:** One event fires per game that asks the player to choose a response.
Karma adjusts based on their choice.

- Add an `EventSystem.gd` that generates a random event on `phase.turn_end`
  if conditions are met
- Bridge sends `player.action` with the chosen response; Python `karma.py`
  scores it
- Surface the karma label (Virtuous / Balanced / Neutral / Strained / Cursed)
  in the HUD

### Milestone 8 — Observation mode (Phase 8)

**Goal:** The player can press a key to toggle into Observer mode — all
institutions are automated and narrative overlays appear.

- All automation levels set to 1.0 on toggle
- Legitimacy heatmap overlay on the map
- Institutional timeline panel (scrollable list of memory entries for a
  selected institution)
- Karma drift graph per civ

---

## Quick reference — key paths

| Thing | Path |
|---|---|
| Python bridge entry point | `python/bridge/server.py` |
| Run the bridge | `python3 -m palimpsest.python.bridge.server` |
| Unix socket | `/tmp/palimpsest.sock` |
| Run tests | `pytest python/tests/test_palimpsest.py -v` |
| Add an AI lens | Create `python/agents/lenses/your_lens.py`, decorate with `@lens` |
| Godot entry point | `godot/scenes/Main.tscn` |
| Launch Godot | `godot4 --path ~/projects/palimpsest/godot/` |
| Architecture doc | `docs/ARCHITECTURE.md` |
| GDD | `The_Palimpsest_GDD.docx` (from previous session) |
