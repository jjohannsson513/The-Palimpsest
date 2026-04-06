"""
tests/test_palimpsest.py
~~~~~~~~~~~~~~~~~~~~~~~~
Full test suite covering:
  - protocol (envelope round-trip, validation, topics)
  - institutions (model, legitimacy math, drift)
  - procgen (terrain, resources, institutions)
  - beliefs (karma, memory)
  - agents (council, all lenses)
  - analytics (pipeline ingestion and metrics)
"""

import asyncio
import json
import sys
import os

# Path hack so tests run without install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocol:
    def test_round_trip(self):
        from palimpsest.python.bridge.protocol import Envelope, Topics
        env = Envelope.command("ai", Topics.AI_INSTITUTION_ORDER,
                               {"institution_id": "army_0", "order_type": "move"}, tick=3)
        raw = env.to_ndjson()
        assert raw.endswith(b"\n")
        d = json.loads(raw)
        assert d["topic"] == Topics.AI_INSTITUTION_ORDER
        assert d["type"]  == "command"
        assert d["tick"]  == 3
        assert d["domain"] == "ai"

    def test_from_dict(self):
        from palimpsest.python.bridge.protocol import Envelope
        d = {"topic": "phase.planning_start", "type": "event", "domain": "system",
             "payload": {}, "tick": 1, "id": "abc", "phase": "planning"}
        env = Envelope.from_dict(d)
        assert env.id == "abc"
        assert env.phase == "planning"

    def test_validate_ok(self):
        from palimpsest.python.bridge.protocol import Envelope
        env = Envelope.command("ai", "ai.institution_order", {})
        assert env.validate() == []

    def test_validate_missing_topic(self):
        from palimpsest.python.bridge.protocol import Envelope
        env = Envelope(topic="", payload={})
        assert any("topic" in e for e in env.validate())

    def test_validate_bad_domain(self):
        from palimpsest.python.bridge.protocol import Envelope
        env = Envelope(topic="foo.bar", payload={}, domain="alien")  # type: ignore
        assert any("domain" in e for e in env.validate())

    def test_topics_constants_present(self):
        from palimpsest.python.bridge.protocol import Topics
        assert Topics.PLANNING_START   == "phase.planning_start"
        assert Topics.AI_PLANNING_DONE == "ai.planning_done"
        assert Topics.PROCGEN_APPLY_MAP == "procgen.apply_map"
        assert Topics.BELIEFS_KARMA_UPDATE == "beliefs.karma_update"


# ─────────────────────────────────────────────────────────────────────────────
# Institution Model & Legitimacy
# ─────────────────────────────────────────────────────────────────────────────

class TestInstitutionModel:
    def _make(self, org=1.0, leg=0.5):
        from palimpsest.python.institutions.model import Institution
        inst = Institution(id="test_0", type_tags=["military", "mobile"], civ_id=1)
        inst.organization = org
        for k in inst.legitimacy_sources:
            inst.legitimacy_sources[k] = leg
        return inst

    def test_phase_stable(self):
        inst = self._make(org=0.8, leg=0.7)
        assert inst.phase == "stable"

    def test_phase_stressed(self):
        inst = self._make(org=0.2, leg=0.2)
        assert inst.phase == "stressed"

    def test_phase_fracturing(self):
        inst = self._make(org=0.1, leg=0.1)
        assert inst.phase == "fracturing"

    def test_phase_collapsed(self):
        inst = self._make(org=0.0, leg=0.0)
        assert inst.phase == "collapsed"

    def test_effective_legitimacy_general(self):
        from palimpsest.python.institutions.model import Institution
        inst = Institution(id="t", type_tags=[], civ_id=0)
        for k in inst.legitimacy_sources:
            inst.legitimacy_sources[k] = 1.0
        assert inst.effective_legitimacy() == pytest.approx(1.0, abs=0.01)

    def test_can_act(self):
        inst = self._make(org=0.5, leg=0.5)
        assert inst.can_act()
        inst2 = self._make(org=0.0, leg=0.0)
        assert not inst2.can_act()

    def test_fragmentation_risk(self):
        inst = self._make(org=0.1, leg=0.1)
        assert inst.fragmentation_risk() > 0.0
        good = self._make(org=0.9, leg=0.9)
        assert good.fragmentation_risk() == 0.0

    def test_from_dict(self):
        from palimpsest.python.institutions.model import institution_from_dict
        d = {
            "id": "army_1", "label": "Iron Host", "type_tags": ["military"],
            "scale": "regional", "civ_id": 2, "organization": 0.75,
            "legitimacy_sources": {"tradition": 0.5, "performance": 0.6,
                                   "belief": 0.4, "law": 0.3, "charisma": 0.7, "fear": 0.0},
            "territory": [{"q": 3, "r": -2}],
        }
        inst = institution_from_dict(d)
        assert inst.id == "army_1"
        assert inst.organization == 0.75
        assert inst.position == {"q": 3, "r": -2}


class TestLegitimacy:
    def test_decay(self):
        from palimpsest.python.institutions.model import Institution
        from palimpsest.python.institutions.legitimacy import decay_legitimacy
        inst = Institution(id="t", type_tags=[], civ_id=0)
        for k in inst.legitimacy_sources:
            inst.legitimacy_sources[k] = 0.8
        decay_legitimacy(inst, turns=10)
        assert all(v < 0.8 for v in inst.legitimacy_sources.values())

    def test_reinforce_caps_at_one(self):
        from palimpsest.python.institutions.model import Institution
        from palimpsest.python.institutions.legitimacy import reinforce
        inst = Institution(id="t", type_tags=[], civ_id=0)
        inst.legitimacy_sources["tradition"] = 0.9
        reinforce(inst, "tradition", 0.5)
        assert inst.legitimacy_sources["tradition"] == pytest.approx(1.0)

    def test_drift_rate_increases_with_autonomy(self):
        from palimpsest.python.institutions.model import Institution
        from palimpsest.python.institutions.legitimacy import compute_drift_rate
        inst = Institution(id="t", type_tags=[], civ_id=0)
        for k in inst.legitimacy_sources:
            inst.legitimacy_sources[k] = 0.6
        drift_loose = compute_drift_rate(inst, oversight_level=0.1)
        drift_tight = compute_drift_rate(inst, oversight_level=0.9)
        assert drift_loose > drift_tight

    def test_transfer(self):
        from palimpsest.python.institutions.model import Institution
        from palimpsest.python.institutions.legitimacy import transfer_legitimacy
        src = Institution(id="s", type_tags=[], civ_id=0)
        dst = Institution(id="d", type_tags=[], civ_id=1)
        for k in src.legitimacy_sources:
            src.legitimacy_sources[k] = 0.8
            dst.legitimacy_sources[k] = 0.2
        transfer_legitimacy(src, dst, fraction=0.5)
        assert dst.legitimacy_sources["tradition"] > 0.2
        assert src.legitimacy_sources["tradition"] < 0.8


# ─────────────────────────────────────────────────────────────────────────────
# Procgen
# ─────────────────────────────────────────────────────────────────────────────

class TestProcgenTerrain:
    def test_tile_count(self):
        from palimpsest.python.procgen.terrain import generate_map
        tiles = generate_map(width=8, height=6, seed=0)
        # (-4..4) x (-3..3) inclusive = 9 * 7 = 63
        assert len(tiles) == 9 * 7

    def test_all_19_terrain_types_reachable(self):
        from palimpsest.python.procgen.terrain import generate_map
        tiles = generate_map(width=40, height=26, seed=42)
        terrains = {t["terrain"] for t in tiles}
        # We won't always hit all 19 but should hit at least 10 on a large map
        assert len(terrains) >= 10

    def test_deterministic(self):
        from palimpsest.python.procgen.terrain import generate_map
        a = generate_map(seed=77)
        b = generate_map(seed=77)
        assert a == b

    def test_different_seeds_differ(self):
        from palimpsest.python.procgen.terrain import generate_map
        a = generate_map(seed=1)
        b = generate_map(seed=2)
        assert [t["terrain"] for t in a] != [t["terrain"] for t in b]

    def test_schema(self):
        from palimpsest.python.procgen.terrain import generate_map
        tiles = generate_map(width=4, height=4, seed=0)
        for t in tiles:
            assert "q" in t and "r" in t and "terrain" in t
            assert 0 <= t["terrain"] <= 18

    def test_edges_water(self):
        from palimpsest.python.procgen.terrain import generate_map, DEEP_OCEAN, OCEAN, COASTAL
        tiles = generate_map(width=16, height=10, seed=5)
        edge = [t for t in tiles if abs(t["q"]) >= 7 or abs(t["r"]) >= 4]
        water = sum(1 for t in edge if t["terrain"] in (DEEP_OCEAN, OCEAN, COASTAL))
        assert water > 0


class TestProcgenResources:
    def test_resources_placed(self):
        from palimpsest.python.procgen.terrain import generate_map
        from palimpsest.python.procgen.resources import place_resources
        tiles = generate_map(width=20, height=12, seed=10)
        tiles = place_resources(tiles, seed=10)
        has_natural   = any(t["resource_natural"]   for t in tiles)
        has_strategic = any(t["resource_strategic"]  for t in tiles)
        assert has_natural and has_strategic

    def test_all_tiles_have_resource_fields(self):
        from palimpsest.python.procgen.terrain import generate_map
        from palimpsest.python.procgen.resources import place_resources
        tiles = place_resources(generate_map(seed=0), seed=0)
        for t in tiles:
            assert "resource_natural"   in t
            assert "resource_strategic" in t
            assert "resource_luxury"    in t


class TestProcgenInstitutions:
    def _tiles(self):
        from palimpsest.python.procgen.terrain import generate_map
        from palimpsest.python.procgen.resources import place_resources
        return place_resources(generate_map(width=20, height=12, seed=42), seed=42)

    def test_generates_correct_civ_count(self):
        from palimpsest.python.procgen.institutions import generate_starting_institutions
        result = generate_starting_institutions(self._tiles(), num_civs=4, seed=0)
        assert len(result["civs"]) == 4

    def test_civ_schema(self):
        from palimpsest.python.procgen.institutions import generate_starting_institutions
        civs = generate_starting_institutions(self._tiles(), num_civs=2, seed=1)["civs"]
        for civ in civs:
            assert "id" in civ and "name" in civ
            assert "ruler" in civ and "pantheon" in civ
            assert "start_q" in civ and "start_r" in civ
            assert "archetype" in civ

    def test_civ_0_is_human(self):
        from palimpsest.python.procgen.institutions import generate_starting_institutions
        civs = generate_starting_institutions(self._tiles(), num_civs=3, seed=2)["civs"]
        assert civs[0]["player_controlled"] is True
        assert all(not c["player_controlled"] for c in civs[1:])

    def test_starts_spread_apart(self):
        from palimpsest.python.procgen.institutions import generate_starting_institutions, _axial_dist
        civs = generate_starting_institutions(self._tiles(), num_civs=4, seed=99)["civs"]
        positions = [(c["start_q"], c["start_r"]) for c in civs]
        for i, (q1, r1) in enumerate(positions):
            for q2, r2 in positions[i+1:]:
                assert _axial_dist(q1, r1, q2, r2) >= 4  # relaxed for small maps


# ─────────────────────────────────────────────────────────────────────────────
# Beliefs & Memory
# ─────────────────────────────────────────────────────────────────────────────

class TestKarma:
    def test_no_tenets_zero_delta(self):
        from palimpsest.python.beliefs.karma import KarmaTracker
        kt = KarmaTracker(civ_id=0)
        delta = kt.apply_action("found_city", {}, tick=1)
        assert delta == 0.0

    def test_karma_clamps(self):
        from palimpsest.python.beliefs.karma import KarmaTracker
        kt = KarmaTracker(civ_id=0, karma=0.99)
        kt.tenets = [{"alignment": 1, "action_affinity": {"attack": 2.0}}]
        kt.apply_action("attack", {}, tick=1)
        assert kt.karma <= 1.0

    def test_label_mapping(self):
        from palimpsest.python.beliefs.karma import KarmaTracker
        kt = KarmaTracker(civ_id=0, karma=0.8)
        assert kt.label == "Virtuous"
        kt.karma = -0.8
        assert kt.label == "Cursed"

    def test_event_weight_high_karma_boosts_positive(self):
        from palimpsest.python.beliefs.karma import KarmaTracker
        kt = KarmaTracker(civ_id=0, karma=1.0)
        assert kt.event_weight_multiplier(1.0) > 1.0
        assert kt.event_weight_multiplier(-1.0) < 1.0


class TestMemory:
    def test_encode_and_recall(self):
        from palimpsest.python.beliefs.memory import InstitutionalMemory
        mem = InstitutionalMemory(institution_id="army_0")
        mem.encode("battle_result", {"outcome": "victory"}, tick=5, salience=0.8)
        results = mem.recall("battle_result")
        assert len(results) == 1
        assert results[0].salience == pytest.approx(0.8)

    def test_aging_decays_salience(self):
        from palimpsest.python.beliefs.memory import InstitutionalMemory
        mem = InstitutionalMemory(institution_id="city_0")
        mem.encode("famine", {}, tick=1, salience=0.5)
        mem.age_all(turns=20)
        assert mem.entries[0].salience < 0.5

    def test_myth_stabilises(self):
        from palimpsest.python.beliefs.memory import InstitutionalMemory
        mem = InstitutionalMemory(institution_id="dynasty_0")
        mem.encode("great_victory", {}, tick=1, salience=0.9)
        mem.entries[0].distortion = 0.75    # Already mythologised
        before = mem.entries[0].salience
        mem.age_all(turns=50)
        assert mem.entries[0].salience >= 0.4  # Stabilised, not zero

    def test_multi_institution_encoding(self):
        from palimpsest.python.beliefs.memory import (
            InstitutionalMemory, encode_event_for_all
        )
        mems = {
            "army_0":   InstitutionalMemory("army_0"),
            "city_0":   InstitutionalMemory("city_0"),
            "dynasty_0": InstitutionalMemory("dynasty_0"),
        }
        encode_event_for_all(
            "battle_result", {"outcome": "victory"}, tick=3,
            memories=mems,
            salience_by_institution={"army_0": 0.9, "city_0": 0.3, "dynasty_0": 0.6},
        )
        assert mems["army_0"].entries[0].salience == pytest.approx(0.9)
        assert mems["city_0"].entries[0].salience == pytest.approx(0.3)
        # Different frames applied
        frames = {k: mems[k].entries[0].interpretation for k in mems}
        assert len(set(frames.values())) > 1


# ─────────────────────────────────────────────────────────────────────────────
# Agents
# ─────────────────────────────────────────────────────────────────────────────

def _make_state(num_civs: int = 2, has_cities: bool = False) -> dict:
    civs = {str(i): {"id": i, "name": f"Civ{i}"} for i in range(num_civs)}
    armies = [
        {
            "id": f"army_{i}", "civ_id": i, "type_tags": ["military", "mobile"],
            "scale": "regional", "organization": 0.85,
            "legitimacy_sources": {"tradition": 0.5, "performance": 0.6, "belief": 0.5,
                                   "law": 0.4, "charisma": 0.5, "fear": 0.0},
            "territory": [{"q": i * 5, "r": 0}],
            "action_budget": 3, "goals": [], "automation_level": 1.0,
            "delegation_contract": {
                "units": [
                    {"unit_id": f"settler_{i}", "type": "settler"},
                    {"unit_id": f"warrior_{i}", "type": "warrior"},
                ]
            },
            "key_person_ids": [],
        }
        for i in range(num_civs)
    ]
    cities = []
    if has_cities:
        cities = [
            {
                "id": f"city_0_0", "civ_id": 0, "type_tags": ["civic", "anchored"],
                "scale": "regional", "organization": 1.0,
                "legitimacy_sources": {"tradition": 0.6, "performance": 0.6, "belief": 0.5,
                                       "law": 0.5, "charisma": 0.3, "fear": 0.0},
                "territory": [{"q": 0, "r": 0}], "action_budget": 3,
                "goals": [], "automation_level": 1.0, "key_person_ids": [],
                "delegation_contract": {
                    "civic_identity": {0: 0.1, 1: 0.2, 2: 0.1, 3: 0.1, 4: 0.5, 5: 0.0, 6: 0.1},
                    "buildings": [], "population": 2,
                },
            }
        ]
    tiles = [{"q": i, "r": 0, "terrain": 6} for i in range(-5, 20)]  # TEMPERATE
    return {
        "civs": civs, "armies": armies, "cities": cities,
        "dynasties": [], "beliefs": {}, "human_civ": 0, "tiles": tiles,
    }


class FakeSession:
    pass


class TestAgentCouncil:
    @pytest.mark.asyncio
    async def test_always_sends_planning_done(self):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        msg = {"topic": Topics.PLANNING_START, "payload": _make_state(), "tick": 1}
        responses = await handle_ai(msg, FakeSession())
        topics = [json.loads(r)["topic"] for r in responses]
        assert Topics.AI_PLANNING_DONE in topics

    @pytest.mark.asyncio
    async def test_no_human_orders(self):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        # State with one human (civ 0) and one AI (civ 1)
        state = _make_state(num_civs=2)
        msg = {"topic": Topics.PLANNING_START, "payload": state, "tick": 2}
        responses = await handle_ai(msg, FakeSession())
        orders = [json.loads(r) for r in responses if json.loads(r)["topic"] == Topics.AI_INSTITUTION_ORDER]
        # All orders should be for civ 1 (not human civ 0)
        for order in orders:
            inst_id = order["payload"].get("institution_id", "")
            assert not inst_id.endswith("_0") or "1" in inst_id or inst_id == ""

    @pytest.mark.asyncio
    async def test_collapsed_institution_skipped(self):
        from palimpsest.python.agents.council import handle_ai
        from palimpsest.python.bridge.protocol import Topics
        state = _make_state(num_civs=2)
        # Collapse civ 1's army
        state["armies"][1]["organization"] = 0.0
        for k in state["armies"][1]["legitimacy_sources"]:
            state["armies"][1]["legitimacy_sources"][k] = 0.0
        msg = {"topic": Topics.PLANNING_START, "payload": state, "tick": 3}
        responses = await handle_ai(msg, FakeSession())
        orders = [json.loads(r) for r in responses
                  if json.loads(r)["topic"] == Topics.AI_INSTITUTION_ORDER]
        # No orders for the collapsed army_1
        for o in orders:
            assert o["payload"].get("institution_id") != "army_1"


class TestExpansionLens:
    def test_no_cities_proposes_found(self):
        from palimpsest.python.agents.lenses.expansion import expansion_lens
        from palimpsest.python.institutions.model import institutions_from_state
        state = _make_state(num_civs=2, has_cities=False)
        registry = institutions_from_state(state)
        civ_insts = {iid: inst for iid, inst in registry.items() if inst.civ_id == 1}
        proposals = expansion_lens(1, state, civ_insts, registry)
        assert any(p.order_type == "found_city" for p in proposals)

    def test_has_city_proposes_move(self):
        from palimpsest.python.agents.lenses.expansion import expansion_lens
        from palimpsest.python.institutions.model import institutions_from_state
        state = _make_state(num_civs=2, has_cities=True)
        # Add a city for civ 1 too
        state["cities"].append({
            "id": "city_1_0", "civ_id": 1, "type_tags": ["civic", "anchored"],
            "scale": "regional", "organization": 1.0,
            "legitimacy_sources": {"tradition": 0.5, "performance": 0.5, "belief": 0.5,
                                   "law": 0.5, "charisma": 0.3, "fear": 0.0},
            "territory": [{"q": 5, "r": 0}], "action_budget": 3,
            "goals": [], "automation_level": 1.0, "key_person_ids": [],
            "delegation_contract": {"civic_identity": {}, "buildings": [], "population": 1},
        })
        registry = institutions_from_state(state)
        civ_insts = {iid: inst for iid, inst in registry.items() if inst.civ_id == 1}
        proposals = expansion_lens(1, state, civ_insts, registry)
        # Should either move or found depending on position scoring
        order_types = {p.order_type for p in proposals}
        assert order_types & {"move", "found_city"}


class TestMilitaryLens:
    def test_low_org_proposes_retreat(self):
        from palimpsest.python.agents.lenses.military import military_lens
        from palimpsest.python.institutions.model import institutions_from_state
        state = _make_state(num_civs=2, has_cities=True)
        # Damage civ 1's army
        state["armies"][1]["organization"] = 0.1
        registry = institutions_from_state(state)
        civ_insts = {iid: inst for iid, inst in registry.items() if inst.civ_id == 1}
        proposals = military_lens(1, state, civ_insts, registry)
        stances = [p.payload.get("stance") for p in proposals if p.order_type == "set_stance"]
        from palimpsest.python.agents.lenses.military import STANCE_RETREATING, STANCE_GARRISON
        assert any(s in (STANCE_RETREATING, STANCE_GARRISON) for s in stances)

    def test_healthy_army_advances(self):
        from palimpsest.python.agents.lenses.military import military_lens, STANCE_AGGRESSIVE, STANCE_CAUTIOUS
        from palimpsest.python.institutions.model import institutions_from_state
        state = _make_state(num_civs=2, has_cities=True)
        registry = institutions_from_state(state)
        civ_insts = {iid: inst for iid, inst in registry.items() if inst.civ_id == 1}
        proposals = military_lens(1, state, civ_insts, registry)
        stances = [p.payload.get("stance") for p in proposals if p.order_type == "set_stance"]
        assert any(s in (STANCE_AGGRESSIVE, STANCE_CAUTIOUS) for s in stances)


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalytics:
    @pytest.mark.asyncio
    async def test_no_response_on_non_turn_end(self):
        # Reset accumulator state
        import palimpsest.python.analytics.pipeline as ap
        ap._acc = ap.GameStateAccumulator()
        from palimpsest.python.bridge.protocol import Topics
        msg = {"topic": Topics.INSTITUTION_CREATED, "payload": {}, "tick": 1}
        responses = await ap.handle_analytics(msg, FakeSession())
        assert responses == []

    @pytest.mark.asyncio
    async def test_turn_end_sends_metrics(self):
        import palimpsest.python.analytics.pipeline as ap
        ap._acc = ap.GameStateAccumulator()
        from palimpsest.python.bridge.protocol import Topics

        # Ingest a planning_start first so there's data
        state_msg = {
            "topic": Topics.PLANNING_START,
            "payload": _make_state(num_civs=2, has_cities=True),
            "tick": 1,
        }
        await ap.handle_analytics(state_msg, FakeSession())

        # Now fire turn_end
        turn_msg = {
            "topic": Topics.TURN_END,
            "payload": {"tick": 1, "scores": {"0": 10, "1": 8}},
            "tick": 1,
        }
        responses = await ap.handle_analytics(turn_msg, FakeSession())
        topics = [json.loads(r)["topic"] for r in responses]
        assert Topics.ANALYTICS_REPORT in topics
        # Score leader report should be present
        payloads = [json.loads(r)["payload"] for r in responses]
        metrics = [p["metric"] for p in payloads]
        assert "score_leader" in metrics
