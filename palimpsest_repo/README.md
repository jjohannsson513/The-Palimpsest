# The Palimpsest

A multi-scale civilisation strategy game on a procedurally generated spherical planet.

**Stack:** Godot 4.2 (GDScript, 3D) + Python 3.11 (asyncio, scipy, numpy)  
**Communication:** Newline-delimited JSON over Unix Domain Socket (`/tmp/palimpsest.sock`)  
**GDD:** `docs/` — see `ARCHITECTURE.md` and `SCENE_SETUP.md`

---

## Quick Start

### Dependencies

```bash
# Godot 4.2 AppImage
wget https://github.com/godotengine/godot/releases/download/4.2.2-stable/Godot_v4.2.2-stable_linux.x86_64.zip
unzip Godot_v4.2.2-stable_linux.x86_64.zip
sudo mv Godot_v4.2.2-stable_linux.x86_64 /usr/local/bin/godot4

# Python deps
cd python/
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Run

```bash
# Terminal 1 — Python bridge (generates world on connect)
source python/.venv/bin/activate
python3 -m palimpsest.python.bridge.server --cells 1000 --civs 6

# Terminal 2 — Godot
godot4 --path godot/
```

### Test

```bash
source python/.venv/bin/activate
pytest python/tests/ -v
```

### World size

```bash
python3 -m palimpsest.python.bridge.server --cells 500   # fast prototype
python3 -m palimpsest.python.bridge.server --cells 1000  # default
python3 -m palimpsest.python.bridge.server --cells 1500  # rich geography
python3 -m palimpsest.python.bridge.server --seed 42     # fixed seed
```

---

## Project Layout

```
palimpsest/
├── docs/
│   ├── ARCHITECTURE.md      IPC protocol, system diagram, module map
│   ├── SCENE_SETUP.md       Godot editor setup instructions
│   └── IMPLEMENTATION_PLAN.md  Step-by-step from bare Debian 12
├── godot/
│   ├── project.godot
│   └── scripts/
│       ├── core/            PythonBridge · TurnManager · Institution · CameraOrbit
│       ├── entities/        City · Army · Dynasty · BeliefSystem
│       ├── world/           WorldSphere · GameWorld
│       └── ui/              UIController
└── python/
    ├── pyproject.toml       scipy + numpy as core deps
    ├── bridge/              server.py · protocol.py
    ├── institutions/        model.py · legitimacy.py
    ├── beliefs/             karma.py · memory.py
    ├── agents/              council.py · sphere_utils.py · lenses/
    ├── analytics/           pipeline.py
    ├── procgen/             sphere.py · tectonics.py · climate.py
    │                        resources.py · institutions.py
    └── tests/               61 tests, all passing
```

---

## World Generation Pipeline

```
Fibonacci sphere (scipy SphericalVoronoi)
    → Plate tectonics (Euler-pole motion · erosion · hydraulics)
    → Climate (latitude bands · orographic rain shadow)
    → Resources (terrain-affinity placement)
    → Starting institutions (civs · dynasties · spread positions)
    → Wire payload → Godot (procgen.apply_map + procgen.apply_institutions)
```

---

## Design

Civilizations are networks of temporary institutions stabilized by legitimacy,
narrated by memory, and steered through delegation.

- **Units → institutions** · **Cities → institutional anchors**
- **Families → legitimacy carriers** · **Automation → delegation of cognition**
- **Scale → abstraction lens** · **Storyteller → meaning feedback loop**
