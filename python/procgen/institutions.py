"""
procgen/institutions.py
~~~~~~~~~~~~~~~~~~~~~~~
Generates the starting civilizations, dynasties, rulers, and belief systems
that Godot applies before the first turn via procgen.apply_institutions.

Each civilization gets:
  - A name, color, and archetype (from GDD §14 AI archetypes)
  - A ruling dynasty with a named founder
  - A pantheon and founding belief
  - A starting position on a viable land tile
"""

from __future__ import annotations

import random
from typing import Any

from palimpsest.python.procgen.terrain import (
    DEEP_OCEAN, OCEAN, COASTAL, POLAR_ICE, MONTANE_IMPASSABLE, WASTELANDS,
)

# Tiles unsuitable for starting positions
_IMPASSABLE = {DEEP_OCEAN, OCEAN, COASTAL, POLAR_ICE, MONTANE_IMPASSABLE, WASTELANDS}

# ── Name pools ────────────────────────────────────────────────────────────────

_CIV_NAMES = [
    "Aethoria", "Valdenmoor", "Seraphine", "Korrath", "Thessilund",
    "Malveria", "Ironhaven", "Dunskaer", "Caledris", "Orenthia",
    "Pyrhal", "Veldrun", "Ashenmere", "Stormgard", "Khalveth",
]

_DYNASTY_PREFIXES = [
    "House", "Clan", "The Order of", "Line of", "The", "The Ancient",
]

_DYNASTY_NAMES = [
    "Serath", "Valkor", "Draeven", "Mirelis", "Thornwood",
    "Arundar", "Kessel", "Vanthis", "Duriel", "Oremis",
    "Caldris", "Fenmoor", "Ashareth", "Gorvain", "Lumindra",
]

_RULER_FIRST = [
    "Aldric", "Mira", "Varek", "Serafina", "Dorn",
    "Lyris", "Cahal", "Theonia", "Gorvan", "Asha",
    "Brennan", "Illara", "Kestrel", "Morwen", "Talveth",
]

_RULER_EPITHETS = [
    "the Bold", "the Wise", "the Unbroken", "the First",
    "the Wanderer", "Iron-Hand", "the Steadfast", "the Dreamer",
    "the Builder", "the Ruthless",
]

# ── Pantheon Pool ─────────────────────────────────────────────────────────────

_PANTHEONS = [
    {
        "id": "fertility", "label": "Cult of Fertility",
        "belief_label": "The land blesses those who tend it.",
        "alignment": 1,   # Benevolent
        "bonus": {"food": 1},
    },
    {
        "id": "war", "label": "The War Pantheon",
        "belief_label": "Strength is the only true law.",
        "alignment": -1,  # Malevolent
        "bonus": {"production": 1},
    },
    {
        "id": "knowledge", "label": "The Archive Covenant",
        "belief_label": "What is written endures beyond empires.",
        "alignment": 0,   # Indifferent
        "bonus": {"research": 1},
    },
    {
        "id": "commerce", "label": "The Merchant Saints",
        "belief_label": "Exchange is the lifeblood of civilization.",
        "alignment": 0,
        "bonus": {"trade_value": 1},
    },
    {
        "id": "ancestors", "label": "The Ancestor Rites",
        "belief_label": "We honour those who came before.",
        "alignment": 1,
        "bonus": {"legitimacy_tradition": 0.1},
    },
    {
        "id": "sky", "label": "The Sky Covenant",
        "belief_label": "The heavens judge what mortals cannot.",
        "alignment": 1,
        "bonus": {"conviction": 1},
    },
    {
        "id": "void", "label": "The Void Compact",
        "belief_label": "Power lies beyond the edge of the knowable.",
        "alignment": -1,
        "bonus": {"research": 1, "conviction": -1},
    },
]

# ── AI Archetypes (GDD §14) ───────────────────────────────────────────────────

_ARCHETYPES = [
    {"id": "expansionist",  "goal_weights": {"territory": 3, "military": 2, "trade": -1}},
    {"id": "mercantile",    "goal_weights": {"trade": 3, "research": 2, "military": -1}},
    {"id": "scholarly",     "goal_weights": {"research": 3, "culture": 2, "expansion": -1}},
    {"id": "militarist",    "goal_weights": {"military": 3, "expansion": 2, "trade": -1}},
    {"id": "spiritual",     "goal_weights": {"conviction": 3, "diplomacy": 2, "aggression": -2}},
    {"id": "pragmatist",    "goal_weights": {"balanced": 1}},
]

# Civ colours as hex strings (for Godot to parse)
_COLORS = [
    "4A90D9", "D94A4A", "4AD97A", "D9B94A", "9B4AD9", "4AD9C9",
    "D97A4A", "7AD94A", "D94A90", "4A7AD9",
]


# ── Starting Position Selection ───────────────────────────────────────────────

def _viable_start_tiles(tiles: list[dict]) -> list[dict]:
    return [t for t in tiles if t["terrain"] not in _IMPASSABLE]


def _pick_spread_positions(
    viable: list[dict],
    num: int,
    rng: random.Random,
    min_angular_dist: float = 0.55,
) -> list[dict]:
    """Pick num cells well-separated on the sphere using great-circle distance."""
    chosen: list[dict] = []
    shuffled = list(viable)
    rng.shuffle(shuffled)
    for tile in shuffled:
        if len(chosen) >= num:
            break
        c0 = tile["center"]
        too_close = any(_angular_dist(c0, c["center"]) < min_angular_dist for c in chosen)
        if not too_close:
            chosen.append(tile)
    if len(chosen) < num:
        for tile in shuffled:
            if len(chosen) >= num:
                break
            if tile not in chosen:
                chosen.append(tile)
    return chosen[:num]


def _angular_dist(c1: list, c2: list) -> float:
    import math
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(c1, c2))))
    return math.acos(dot)


# ── Generator ─────────────────────────────────────────────────────────────────

def generate_starting_institutions(
    tiles: list[dict],
    num_civs: int = 6,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Returns a dict matching the procgen.apply_institutions payload schema:
    { "civs": [ civ_dict, … ] }
    """
    rng = random.Random(seed + 42)

    viable  = _viable_start_tiles(tiles)
    starts  = _pick_spread_positions(viable, num_civs, rng)
    civs: list[dict[str, Any]] = []

    civ_names    = rng.sample(_CIV_NAMES, min(num_civs, len(_CIV_NAMES)))
    dyn_names    = rng.sample(_DYNASTY_NAMES, min(num_civs, len(_DYNASTY_NAMES)))
    ruler_firsts = rng.sample(_RULER_FIRST, min(num_civs, len(_RULER_FIRST)))
    epithets     = rng.sample(_RULER_EPITHETS, min(num_civs, len(_RULER_EPITHETS)))
    pantheons    = rng.choices(_PANTHEONS, k=num_civs)
    archetypes   = rng.choices(_ARCHETYPES, k=num_civs)

    for i in range(min(num_civs, len(starts))):
        start_tile = starts[i]
        ruler_name = f"{ruler_firsts[i % len(ruler_firsts)]} {epithets[i % len(epithets)]}"
        ruler_id   = f"ruler_{i}"
        dynasty_label = f"{_DYNASTY_PREFIXES[i % len(_DYNASTY_PREFIXES)]} {dyn_names[i % len(dyn_names)]}"

        civ: dict[str, Any] = {
            "id":           i,
            "name":         civ_names[i % len(civ_names)],
            "color":        _COLORS[i % len(_COLORS)],
            "archetype":    archetypes[i],
            "player_controlled": (i == 0),   # Civ 0 is always the human player
            "start_cell_id": start_tile.get("id", 0),
            "dynasty_name": dynasty_label,
            "ruler": {
                "id":    ruler_id,
                "name":  ruler_name,
                "role":  "ruler",
                "age":   rng.randint(24, 55),
                "traits": _pick_ruler_traits(rng, archetypes[i]["id"]),
                "reputation": {
                    "honor":      round(rng.uniform(0.3, 0.8), 2),
                    "cruelty":    round(rng.uniform(0.0, 0.5), 2),
                    "piety":      round(rng.uniform(0.2, 0.8), 2),
                    "competence": round(rng.uniform(0.4, 0.9), 2),
                },
                "faction_alignment": "loyalists",
                "parent_ids": [],
                "child_ids":  [],
            },
            "pantheon": pantheons[i],
            "legitimacy_sources": {
                "tradition":   round(rng.uniform(0.3, 0.7), 2),
                "performance": 0.5,
                "belief":      round(rng.uniform(0.4, 0.8), 2),
                "law":         round(rng.uniform(0.3, 0.6), 2),
                "charisma":    round(rng.uniform(0.3, 0.7), 2),
                "fear":        0.0,
            },
        }
        civs.append(civ)

    return {"civs": civs}


def _pick_ruler_traits(rng: random.Random, archetype_id: str) -> list[str]:
    """Return 2–3 traits biased toward the archetype."""
    trait_pools: dict[str, list[str]] = {
        "expansionist":  ["ambitious", "bold", "restless", "charismatic"],
        "mercantile":    ["shrewd", "patient", "well-connected", "pragmatic"],
        "scholarly":     ["curious", "methodical", "cautious", "visionary"],
        "militarist":    ["fierce", "disciplined", "ruthless", "loyal"],
        "spiritual":     ["devout", "compassionate", "ascetic", "inspiring"],
        "pragmatist":    ["adaptable", "calculating", "steady", "diplomatic"],
    }
    generic = ["dutiful", "experienced", "perceptive"]
    pool = trait_pools.get(archetype_id, []) + generic
    return rng.sample(pool, min(3, len(pool)))
