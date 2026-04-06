# The Palimpsest — Architecture & Integration Spec
## Version 0.2  (post-GDD revision)

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GODOT 4 PROCESS                             │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ TurnManager │  │  GameWorld   │  │  WorldMap    │               │
│  │ PLANNING /  │  │  Institution │  │  Voronoi-hex │               │
│  │ EXECUTION   │  │  Registry    │  │  tiles       │               │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                │                  │                       │
│  ┌──────▼────────────────▼──────────────────▼──────┐                │
│  │              PythonBridge (GDScript)             │                │
│  │   Thread-safe UDS client · NDJSON protocol       │                │
│  └──────────────────────┬──────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
                          │ /tmp/palimpsest.sock  (Unix Domain Socket)
┌─────────────────────────▼──────────────────────────────────────────┐
│                       PYTHON PROCESS                                │
│                                                                     │
│  bridge/server.py  ──►  router  ──────────────────────────────┐    │
│                                                                │    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐ │    │
│  │ institutions/   │  │ agents/          │  │ beliefs/      │ │    │
│  │ model.py        │  │ council.py       │  │ karma.py      │◄┘    │
│  │ legitimacy.py   │  │ lenses/          │  │ memory.py     │      │
│  └─────────────────┘  │   expansion.py   │  └───────────────┘      │
│                       │   military.py    │                         │
│  ┌─────────────────┐  │   diplomatic.py  │  ┌───────────────┐      │
│  │ analytics/      │  │   economic.py    │  │ procgen/      │      │
│  │ pipeline.py     │  └──────────────────┘  │ terrain.py    │      │
│  └─────────────────┘                        │ institutions  │      │
│                                             │ resources.py  │      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles (from GDD)

**Everything is an Institution.**  
Armies, cities, dynasties, religions, factions — all share the same schema.
They differ in scale, permissions, and narrative framing. No hard-coded entity types.

**Four fundamental fields on every institution:**
- `organization`  — internal coherence, doctrine, logistics
- `legitimacy`    — relational recognition (multi-sourced vector)
- `memory`        — distorted, institution-specific event history
- `belief_set`    — interpretive models that bias decisions

**Automation is delegation, not convenience.**  
When the player hands off a domain, a `DelegationContract` is formed.
Delegated institutions drift; drift is history, not a bug.

**Planning Phase / Execution Phase loop.**  
All strategic decisions happen in Planning. Real-time execution plays them out.
The Python bridge drives AI decisions during Planning Phase resolution.

---

## Protocol

**Socket:** `/tmp/palimpsest.sock`  
**Format:** Newline-delimited JSON (NDJSON)

### Message Envelope
```json
{
  "id":      "uuid-v4",
  "type":    "event | command | response | error",
  "domain":  "ai | analytics | procgen | beliefs | system",
  "topic":   "domain.verb_noun",
  "payload": { ... },
  "phase":   "planning | execution | observe",
  "tick":    42
}
```

### Topic Registry

**Godot → Python (Events)**
```
system.handshake          { version, capabilities }
phase.planning_start      { tick, institutions[], map_state }
phase.execution_start     { tick, orders[] }
phase.turn_end            { tick, scores, events_fired[] }
institution.created       { institution }
institution.changed       { id, delta }
institution.destroyed     { id, cause }
map.tile_selected         { q, r, tile_data }
player.action             { action_type, subject_id, payload }
```

**Python → Godot (Commands)**
```
system.ready              { }
ai.institution_order      { institution_id, order_type, payload }
ai.planning_done          { tick, orders[] }
procgen.apply_map         { tiles[] }
procgen.apply_institutions { institutions[], dynasties[] }
beliefs.karma_update      { institution_id, delta, reason }
beliefs.event_interpretation { event_id, interpretations{} }
analytics.report          { metric, value, breakdown }
```

---

## File Map

### Godot (GDScript)

| File | Role |
|------|------|
| `core/PythonBridge.gd` | Thread-safe UDS client; signal dispatch |
| `core/TurnManager.gd` | Planning/Execution state machine; phase signals |
| `core/Institution.gd` | Base Institution resource class |
| `world/WorldMap.gd` | Hex-based tile grid (Voronoi-visual target); terrain; resources |
| `world/GameWorld.gd` | Institution registry; wires all subsystems |
| `entities/Dynasty.gd` | Ruler + courtier management; faction pressure |
| `entities/BeliefSystem.gd` | Belief set, karma, tenet tracking per institution |
| `entities/Army.gd` | Military institution; stance; organization combat |
| `entities/City.gd` | Civic institution; yields; civic identity |
| `ui/UIController.gd` | Phase UI, turn button, overlays |

### Python

| Module | Role |
|--------|------|
| `bridge/server.py` | Async UDS server; topic router |
| `bridge/protocol.py` | Envelope schema, Topics constants |
| `institutions/model.py` | `Institution` dataclass; full GDD schema |
| `institutions/legitimacy.py` | Legitimacy vector math, decay, threshold logic |
| `beliefs/karma.py` | Karma accumulation and event weighting |
| `beliefs/memory.py` | Event encoding, distortion, institution-specific recall |
| `agents/council.py` | Meta-interpreter; merges lens proposals |
| `agents/lenses/expansion.py` | Expansion/settlement lens |
| `agents/lenses/military.py` | Military / threat-response lens |
| `agents/lenses/diplomatic.py` | Diplomatic relationship lens |
| `agents/lenses/economic.py` | Trade and yield optimization lens |
| `analytics/pipeline.py` | Passive event accumulator; turn-end metrics |
| `procgen/terrain.py` | Fractal map generation; full GDD terrain set |
| `procgen/institutions.py` | Starting civs, dynasties, belief sets |
| `procgen/resources.py` | Resource placement by terrain affinity |

---

## Debian 12 Setup

```bash
# Godot 4.2 AppImage
wget https://github.com/godotengine/godot/releases/download/4.2.2-stable/Godot_v4.2.2-stable_linux.x86_64.zip
unzip Godot_v4.2.2-stable_linux.x86_64.zip
sudo mv Godot_v4.2.2-stable_linux.x86_64 /usr/local/bin/godot4

# Python
cd palimpsest/python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run
python -m bridge.server         # Terminal 1
godot4 --path ../godot/         # Terminal 2
```
