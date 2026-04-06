"""
tests/test_sphere_pipeline.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the full sphere + tectonic + climate + institution pipeline.
All tests are deterministic (fixed seeds) and pure Python — no Godot required.
"""
import sys, os, json, asyncio, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Sphere geometry
# ─────────────────────────────────────────────────────────────────────────────

class TestFibonacciSphere:
    def test_point_count(self):
        from palimpsest.python.procgen.sphere import fibonacci_sphere
        pts = fibonacci_sphere(500)
        assert pts.shape == (500, 3)

    def test_all_on_unit_sphere(self):
        import numpy as np
        from palimpsest.python.procgen.sphere import fibonacci_sphere
        pts = fibonacci_sphere(300)
        norms = np.linalg.norm(pts, axis=1)
        assert (abs(norms - 1.0) < 1e-6).all()

    def test_deterministic(self):
        from palimpsest.python.procgen.sphere import fibonacci_sphere
        a = fibonacci_sphere(200)
        b = fibonacci_sphere(200)
        assert (a == b).all()

    def test_pole_coverage(self):
        """Fibonacci sphere should have points near both poles."""
        from palimpsest.python.procgen.sphere import fibonacci_sphere
        pts = fibonacci_sphere(500)
        z = pts[:, 2]
        assert z.max() > 0.95, "No point near north pole"
        assert z.min() < -0.95, "No point near south pole"


class TestSphereBuild:
    @pytest.fixture(scope="class")
    def sphere(self):
        from palimpsest.python.procgen.sphere import build_sphere
        return build_sphere(300, seed=0)

    def test_cell_count(self, sphere):
        assert sphere.num_cells == 300

    def test_radius_scales(self):
        from palimpsest.python.procgen.sphere import build_sphere, BASE_RADIUS, BASE_N
        s1 = build_sphere(500)
        s2 = build_sphere(1000)
        # R should scale as sqrt(N/BASE_N)
        expected_ratio = math.sqrt(1000 / 500)
        actual_ratio   = s2.sphere_radius / s1.sphere_radius
        assert abs(actual_ratio - expected_ratio) < 0.05

    def test_all_cells_have_adjacency(self, sphere):
        for cid in range(sphere.num_cells):
            assert cid in sphere.adjacency

    def test_average_neighbors_near_six(self, sphere):
        avg = sum(len(v) for v in sphere.adjacency.values()) / sphere.num_cells
        # Euler's formula for planar graphs: avg degree ≈ 6 for large N
        assert 5.5 <= avg <= 6.5, f"avg_neighbors={avg:.2f}"

    def test_adjacency_symmetric(self, sphere):
        for a, neighbors in sphere.adjacency.items():
            for b in neighbors:
                assert a in sphere.adjacency[b], f"{b} does not list {a} as neighbor"

    def test_regions_nonempty(self, sphere):
        assert all(len(r) >= 3 for r in sphere.regions)

    def test_wire_serialisable(self, sphere):
        from palimpsest.python.procgen.sphere import sphere_to_wire
        wire = sphere_to_wire(sphere)
        raw  = json.dumps(wire)   # must not raise
        assert len(raw) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tectonic simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestTectonics:
    @pytest.fixture(scope="class")
    def tectonic(self):
        from palimpsest.python.procgen.sphere    import build_sphere
        from palimpsest.python.procgen.tectonics import TectonicConfig, run_simulation
        sphere = build_sphere(400, seed=1)
        cfg    = TectonicConfig(
            num_plates=10, simulation_steps=30,  # fast for testing
            erosion_passes=5, hydraulic_passes=3,
        )
        return run_simulation(sphere, config=cfg, seed=1)

    def test_height_normalised(self, tectonic):
        import numpy as np
        assert tectonic.heights.min() >= -1.5
        assert tectonic.heights.max() <=  1.5

    def test_ocean_fraction_reasonable(self, tectonic):
        ocean_pct = tectonic.is_oceanic.mean()
        assert 0.20 <= ocean_pct <= 0.65, f"ocean={ocean_pct:.2f}"

    def test_plate_ids_valid(self, tectonic):
        import numpy as np
        n_plates = len(tectonic.plates)
        assert (tectonic.plate_ids >= 0).all()
        assert (tectonic.plate_ids < n_plates).all()

    def test_continental_higher_than_oceanic(self, tectonic):
        import numpy as np
        land_h  = tectonic.heights[~tectonic.is_oceanic]
        ocean_h = tectonic.heights[tectonic.is_oceanic]
        assert land_h.mean() > ocean_h.mean()

    def test_deterministic(self):
        from palimpsest.python.procgen.sphere    import build_sphere
        from palimpsest.python.procgen.tectonics import TectonicConfig, run_simulation
        sphere = build_sphere(200, seed=7)
        cfg    = TectonicConfig(simulation_steps=10, erosion_passes=2, hydraulic_passes=1)
        a = run_simulation(sphere, config=cfg, seed=7)
        b = run_simulation(sphere, config=cfg, seed=7)
        import numpy as np
        assert np.allclose(a.heights, b.heights)


# ─────────────────────────────────────────────────────────────────────────────
# Climate
# ─────────────────────────────────────────────────────────────────────────────

class TestClimate:
    @pytest.fixture(scope="class")
    def result(self):
        from palimpsest.python.procgen.sphere    import build_sphere
        from palimpsest.python.procgen.tectonics import TectonicConfig, run_simulation
        from palimpsest.python.procgen.climate   import apply_climate
        sphere   = build_sphere(500, seed=2)
        tectonic = run_simulation(sphere, TectonicConfig(simulation_steps=20, erosion_passes=3, hydraulic_passes=2), seed=2)
        return sphere, tectonic, apply_climate(sphere, tectonic)

    def test_terrain_codes_valid(self, result):
        _, _, climate = result
        assert ((climate.terrain >= 0) & (climate.terrain <= 18)).all()

    def test_at_least_eight_terrain_types(self, result):
        _, _, climate = result
        import numpy as np
        assert len(set(climate.terrain.tolist())) >= 8

    def test_temperature_range(self, result):
        _, _, climate = result
        assert climate.temperature.min() >= 0.0
        assert climate.temperature.max() <= 1.0

    def test_moisture_range(self, result):
        _, _, climate = result
        assert climate.moisture.min() >= 0.0
        assert climate.moisture.max() <= 1.0

    def test_poles_cold(self, result):
        import numpy as np
        sphere, _, climate = result
        polar_mask = np.abs(sphere.centers[:, 2]) > 0.85
        if polar_mask.sum() > 0:
            assert climate.temperature[polar_mask].mean() < 0.4

    def test_ocean_cells_have_ocean_terrain(self, result):
        sphere, tectonic, climate = result
        ocean_terrains = {0, 1, 2, 3}  # DEEP_OCEAN, OCEAN, COASTAL, POLAR_ICE
        ocean_cells    = tectonic.is_oceanic
        ocean_terrain  = set(climate.terrain[ocean_cells].tolist())
        # Most ocean cells should have ocean terrain (some may be coastal)
        non_ocean = ocean_terrain - ocean_terrains
        assert len(non_ocean) <= 3, f"Unexpected terrains on ocean cells: {non_ocean}"


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline (generate_world)
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateWorld:
    @pytest.fixture(scope="class")
    def world(self):
        from palimpsest.python.procgen import generate_world
        from palimpsest.python.procgen.tectonics import TectonicConfig
        cfg = TectonicConfig(simulation_steps=20, erosion_passes=3, hydraulic_passes=2)
        return generate_world(num_cells=400, num_civs=4, seed=42, tectonic_config=cfg)

    def test_cell_count(self, world):
        assert len(world["cells"]) == 400

    def test_all_cells_have_required_fields(self, world):
        required = {"id","center","vertices","neighbors","terrain","height",
                    "plate_id","is_oceanic","temperature","moisture",
                    "resource_natural","resource_strategic","resource_luxury"}
        for cell in world["cells"]:
            missing = required - cell.keys()
            assert not missing, f"Cell {cell['id']} missing: {missing}"

    def test_center_on_unit_sphere(self, world):
        import math
        for cell in world["cells"][:20]:
            c = cell["center"]
            norm = math.sqrt(sum(x*x for x in c))
            assert abs(norm - 1.0) < 0.01, f"Cell {cell['id']} center not on unit sphere"

    def test_vertices_on_unit_sphere(self, world):
        import math
        for cell in world["cells"][:10]:
            for v in cell["vertices"]:
                norm = math.sqrt(sum(x*x for x in v))
                assert abs(norm - 1.0) < 0.02

    def test_adjacency_ids_valid(self, world):
        max_id = max(c["id"] for c in world["cells"])
        for cell in world["cells"]:
            for n in cell["neighbors"]:
                assert 0 <= n <= max_id

    def test_civ_count(self, world):
        assert len(world["civs"]) == 4

    def test_start_cells_on_land(self, world):
        cell_lookup = {c["id"]: c for c in world["cells"]}
        for civ in world["civs"]:
            sc = civ.get("start_cell_id", -1)
            assert sc >= 0
            cell = cell_lookup.get(sc, {})
            assert not cell.get("is_oceanic", True), \
                f"Civ {civ['id']} starts in ocean at cell {sc}"

    def test_starts_spread_apart(self, world):
        import math
        cell_lookup = {c["id"]: c for c in world["cells"]}
        starts = [cell_lookup[c["start_cell_id"]]["center"] for c in world["civs"]
                  if c.get("start_cell_id", -1) in cell_lookup]
        for i, ca in enumerate(starts):
            for cb in starts[i+1:]:
                dot  = max(-1.0, min(1.0, sum(x*y for x,y in zip(ca, cb))))
                dist = math.acos(dot)
                assert dist > 0.3, f"Two civs start less than 17° apart"

    def test_deterministic(self):
        from palimpsest.python.procgen import generate_world
        from palimpsest.python.procgen.tectonics import TectonicConfig
        cfg = TectonicConfig(simulation_steps=10, erosion_passes=2, hydraulic_passes=1)
        a = generate_world(400, 4, seed=99, tectonic_config=cfg)
        b = generate_world(400, 4, seed=99, tectonic_config=cfg)
        assert [c["terrain"] for c in a["cells"]] == [c["terrain"] for c in b["cells"]]

    def test_resources_placed(self, world):
        has_any = any(
            c["resource_natural"] or c["resource_strategic"]
            for c in world["cells"]
        )
        assert has_any


# ─────────────────────────────────────────────────────────────────────────────
# Sphere utils (CellIndex, lenses)
# ─────────────────────────────────────────────────────────────────────────────

class TestCellIndex:
    @pytest.fixture(scope="class")
    def idx_and_world(self):
        from palimpsest.python.procgen import generate_world
        from palimpsest.python.procgen.tectonics import TectonicConfig
        from palimpsest.python.agents.sphere_utils import CellIndex
        cfg   = TectonicConfig(simulation_steps=10, erosion_passes=2, hydraulic_passes=1)
        world = generate_world(300, 3, seed=5, tectonic_config=cfg)
        return CellIndex(world), world

    def test_bfs_distance_self(self, idx_and_world):
        idx, _ = idx_and_world
        assert idx.bfs_distance(0, 0) == 0

    def test_bfs_distance_neighbor(self, idx_and_world):
        idx, world = idx_and_world
        cell0 = world["cells"][0]
        if cell0["neighbors"]:
            n = cell0["neighbors"][0]
            assert idx.bfs_distance(0, n) == 1

    def test_bfs_distance_symmetric(self, idx_and_world):
        idx, _ = idx_and_world
        assert idx.bfs_distance(0, 5) == idx.bfs_distance(5, 0)

    def test_cells_within_hops(self, idx_and_world):
        idx, _ = idx_and_world
        within1 = idx.cells_within_hops(0, 1)
        within2 = idx.cells_within_hops(0, 2)
        # 2-hop reachable should be superset of 1-hop
        assert set(within1).issubset(set(within2))
        assert len(within2) >= len(within1)

    def test_step_toward(self, idx_and_world):
        idx, world = idx_and_world
        cell0 = world["cells"][0]
        if len(cell0["neighbors"]) >= 2:
            n = cell0["neighbors"][1]
            step = idx.step_toward(0, n)
            # Step from 0 toward n should be n itself (1 hop)
            assert step == n

    def test_angular_dist_range(self, idx_and_world):
        import math
        idx, _ = idx_and_world
        d = idx.angular_dist(0, 1)
        assert 0.0 < d <= math.pi


# ─────────────────────────────────────────────────────────────────────────────
# AI agents on sphere world
# ─────────────────────────────────────────────────────────────────────────────

def _make_sphere_state(num_cells=300, num_civs=2):
    """Build a minimal state dict using real sphere data."""
    from palimpsest.python.procgen import generate_world
    from palimpsest.python.procgen.tectonics import TectonicConfig
    cfg   = TectonicConfig(simulation_steps=10, erosion_passes=2, hydraulic_passes=1)
    world = generate_world(num_cells, num_civs, seed=13, tectonic_config=cfg)

    # Build army dicts for each civ at their start cell
    armies = []
    for civ in world["civs"]:
        sc = civ.get("start_cell_id", 0)
        armies.append({
            "id": f"army_{civ['id']}", "civ_id": civ["id"],
            "type_tags": ["military", "mobile"], "scale": "regional",
            "organization": 0.85,
            "legitimacy_sources": {k: 0.5 for k in ["tradition","performance","belief","law","charisma","fear"]},
            "territory": [sc], "action_budget": 3,
            "goals": [], "automation_level": 1.0,
            "delegation_contract": {
                "units": [
                    {"unit_id": f"settler_{civ['id']}", "type": "settler"},
                    {"unit_id": f"warrior_{civ['id']}", "type": "warrior"},
                ]
            },
            "key_person_ids": [],
        })

    return {
        "civs":      {str(c["id"]): c for c in world["civs"]},
        "cells":     world["cells"],
        "armies":    armies,
        "cities":    [],
        "dynasties": [],
        "beliefs":   {},
        "human_civ": 0,
    }


class FakeSession:
    pass


class TestSphereLenses:
    @pytest.fixture(scope="class")
    def sphere_state(self):
        return _make_sphere_state()

    @pytest.mark.asyncio
    async def test_council_returns_planning_done(self, sphere_state):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        msg = {"topic": Topics.PLANNING_START, "payload": sphere_state, "tick": 1}
        responses = await handle_ai(msg, FakeSession())
        topics = [json.loads(r)["topic"] for r in responses]
        assert Topics.AI_PLANNING_DONE in topics

    @pytest.mark.asyncio
    async def test_expansion_found_city_for_ai_civ(self, sphere_state):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        msg = {"topic": Topics.PLANNING_START, "payload": sphere_state, "tick": 1}
        responses = await handle_ai(msg, FakeSession())
        orders = [json.loads(r) for r in responses if json.loads(r)["topic"] == Topics.AI_INSTITUTION_ORDER]
        # Civ 1 (AI) should want to found a city — no cities exist yet
        found_orders = [o for o in orders if o["payload"].get("order_type") == "found_city"]
        assert len(found_orders) >= 1, f"No found_city order. All orders: {[o['payload']['order_type'] for o in orders]}"

    @pytest.mark.asyncio
    async def test_move_order_uses_cell_id(self, sphere_state):
        """All move orders should specify cell_id, not q/r."""
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        # Add a city so expansion switches to scouting mode
        state = dict(sphere_state)
        first_cell = sphere_state["cells"][0]["id"]
        state["cities"] = [{
            "id": "city_1_0", "civ_id": 1, "type_tags": ["civic","anchored"],
            "scale": "regional", "organization": 1.0,
            "legitimacy_sources": {k: 0.5 for k in ["tradition","performance","belief","law","charisma","fear"]},
            "territory": [first_cell], "action_budget": 3,
            "goals": [], "automation_level": 1.0, "key_person_ids": [],
            "delegation_contract": {"civic_identity": {}, "buildings": [], "population": 1},
        }]
        msg = {"topic": Topics.PLANNING_START, "payload": state, "tick": 2}
        responses = await handle_ai(msg, FakeSession())
        orders = [json.loads(r) for r in responses if json.loads(r)["topic"] == Topics.AI_INSTITUTION_ORDER]
        move_orders = [o for o in orders if o["payload"].get("order_type") == "move"]
        for mo in move_orders:
            assert "cell_id" in mo["payload"], f"Move order missing cell_id: {mo['payload']}"
            assert "q" not in mo["payload"], f"Move order still has q: {mo['payload']}"

    @pytest.mark.asyncio
    async def test_low_org_army_retreats(self, sphere_state):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        state = dict(sphere_state)
        # Damage AI army (civ 1)
        armies = [dict(a) for a in state["armies"]]
        for a in armies:
            if a["civ_id"] == 1:
                a["organization"] = 0.05
        state["armies"] = armies
        # Give civ 1 a city to retreat to
        sc = sphere_state["civs"]["1"].get("start_cell_id", 0)
        state["cities"] = [{
            "id": "city_1_0", "civ_id": 1, "type_tags": ["civic","anchored"],
            "scale": "regional", "organization": 1.0,
            "legitimacy_sources": {k: 0.5 for k in ["tradition","performance","belief","law","charisma","fear"]},
            "territory": [sc], "action_budget": 3,
            "goals": [], "automation_level": 1.0, "key_person_ids": [],
            "delegation_contract": {"civic_identity": {}, "buildings": [], "population": 1},
        }]
        msg = {"topic": Topics.PLANNING_START, "payload": state, "tick": 3}
        responses = await handle_ai(msg, FakeSession())
        orders = [json.loads(r) for r in responses if json.loads(r)["topic"] == Topics.AI_INSTITUTION_ORDER]
        stances = [o["payload"].get("stance") for o in orders if o["payload"].get("order_type") == "set_stance"]
        RETREATING, GARRISON = 3, 4
        assert any(s in (RETREATING, GARRISON) for s in stances), \
            f"Expected retreat/garrison stance. Got stances: {stances}"
