"""
procgen/resources.py
~~~~~~~~~~~~~~~~~~~~
Places natural, strategic, and luxury resources onto map tiles
based on terrain affinity tables from GDD §3.

Operates as a pure function over the tile list produced by terrain.py.
"""

from __future__ import annotations

import random
from typing import Any

# Terrain codes (must match terrain.py)
DEEP_OCEAN, OCEAN, COASTAL    = 0, 1, 2
POLAR_ICE, TUNDRA, TAIGA      = 3, 4, 5
TEMPERATE, GRASSLAND, SAVANNA  = 6, 7, 8
MEDITERRANEAN, MONSOON, TROPICAL = 9, 10, 11
DESERT, ARID_DESERT, XERIC    = 12, 13, 14
DRY_STEPPE                    = 15
MONTANE, MONTANE_IMPASSABLE   = 16, 17
WASTELANDS                    = 18

# ── Affinity Tables ───────────────────────────────────────────────────────────
# terrain → [(resource_name, weight), ...]
# Weight is relative probability; only one resource per category per tile.

NATURAL_BY_TERRAIN: dict[int, list[tuple[str, float]]] = {
    DEEP_OCEAN:    [("Whales", 0.4), ("Pearls", 0.2)],
    OCEAN:         [("Fish", 0.6), ("Kelp", 0.3)],
    COASTAL:       [("Fish", 0.5), ("Shellfish", 0.4), ("Coral", 0.2)],
    TUNDRA:        [("Furs", 0.5)],
    TAIGA:         [("Lumber", 0.6), ("Furs", 0.3)],
    TEMPERATE:     [("Wheat", 0.5), ("Cattle", 0.4), ("Hemp", 0.2)],
    GRASSLAND:     [("Cattle", 0.5), ("Sheep", 0.4), ("Wheat", 0.3)],
    SAVANNA:       [("Cattle", 0.4), ("Maize", 0.3), ("Sheep", 0.2)],
    MEDITERRANEAN: [("Olives", 0.5), ("Sheep", 0.3), ("Barley", 0.3)],
    MONSOON:       [("Pigs", 0.3), ("Maize", 0.4)],
    TROPICAL:      [("Pigs", 0.3), ("Lumber", 0.4), ("Nuts", 0.3)],
    DESERT:        [("Salt", 0.4)],
    ARID_DESERT:   [("Salt", 0.3)],
    DRY_STEPPE:    [("Horses", 0.4), ("Sheep", 0.3)],
    MONTANE:       [("Stone", 0.5), ("Marble", 0.2), ("Clay", 0.3)],
}

STRATEGIC_BY_TERRAIN: dict[int, list[tuple[str, float]]] = {
    TUNDRA:        [("Iron", 0.25), ("Titanium", 0.05)],
    TAIGA:         [("Iron", 0.2),  ("Coal", 0.15)],
    TEMPERATE:     [("Copper", 0.2), ("Tin", 0.15)],
    GRASSLAND:     [("Horses", 0.3), ("Copper", 0.1)],
    SAVANNA:       [("Horses", 0.25), ("Aluminum", 0.05)],
    DESERT:        [("Petroleum", 0.2), ("Natural_Gas", 0.15), ("Saltpeter", 0.1)],
    ARID_DESERT:   [("Petroleum", 0.25), ("Natural_Gas", 0.2)],
    XERIC:         [("Petroleum", 0.15), ("Lithium", 0.1)],
    DRY_STEPPE:    [("Horses", 0.3), ("Coal", 0.1)],
    MONTANE:       [("Iron", 0.3), ("Coal", 0.2), ("Copper", 0.2),
                    ("Titanium", 0.05), ("Uranium", 0.03), ("Platinum", 0.02)],
    COASTAL:       [("Aluminum", 0.1)],
}

LUXURY_BY_TERRAIN: dict[int, list[tuple[str, float]]] = {
    DEEP_OCEAN:    [("Whales", 0.2), ("Pearls", 0.3)],
    COASTAL:       [("Pearls", 0.3), ("Amber", 0.1)],
    TUNDRA:        [("Furs", 0.4), ("Amber", 0.1)],
    TAIGA:         [("Furs", 0.3)],
    TEMPERATE:     [("Wine", 0.2), ("Amber", 0.1)],
    GRASSLAND:     [("Cotton", 0.2)],
    SAVANNA:       [("Ivory", 0.2), ("Cotton", 0.2)],
    MEDITERRANEAN: [("Wine", 0.35), ("Silk", 0.2), ("Perfume", 0.15)],
    MONSOON:       [("Tea", 0.3), ("Cocoa", 0.2), ("Spices", 0.25)],
    TROPICAL:      [("Spices", 0.3), ("Vanilla", 0.2), ("Cocoa", 0.25),
                    ("Opium", 0.1), ("Sugar", 0.2)],
    DESERT:        [("Gold", 0.2), ("Incense", 0.25)],
    ARID_DESERT:   [("Gold", 0.15), ("Incense", 0.2)],
    MONTANE:       [("Gold", 0.15), ("Silver", 0.2), ("Gems", 0.1)],
    DRY_STEPPE:    [("Silver", 0.1)],
}

# ── Placement rates ───────────────────────────────────────────────────────────
# Per-tile base probability for each resource category
_NATURAL_RATE   = 0.22
_STRATEGIC_RATE = 0.08
_LUXURY_RATE    = 0.06


def _weighted_pick(
    pool: list[tuple[str, float]],
    rng: random.Random,
    base_rate: float,
) -> str:
    """Return a resource name or '' based on weighted probability."""
    roll = rng.random()
    if roll >= base_rate:
        return ""
    # Weighted selection within the pool
    total = sum(w for _, w in pool)
    r = rng.random() * total
    cumulative = 0.0
    for name, weight in pool:
        cumulative += weight
        if r <= cumulative:
            return name
    return pool[-1][0]


# ── Public API ────────────────────────────────────────────────────────────────

def place_resources(
    tiles: list[dict[str, Any]],
    seed: int = 0,
) -> list[dict[str, Any]]:
    """
    Mutates tile dicts in-place to add resource fields.
    Returns the same list for convenience.
    """
    rng = random.Random(seed + 9999)

    for tile in tiles:
        t = tile["terrain"]

        nat_pool  = NATURAL_BY_TERRAIN.get(t,   [])
        strat_pool = STRATEGIC_BY_TERRAIN.get(t, [])
        lux_pool  = LUXURY_BY_TERRAIN.get(t,    [])

        tile["resource_natural"]   = _weighted_pick(nat_pool,   rng, _NATURAL_RATE)   if nat_pool   else ""
        tile["resource_strategic"] = _weighted_pick(strat_pool, rng, _STRATEGIC_RATE) if strat_pool else ""
        tile["resource_luxury"]    = _weighted_pick(lux_pool,   rng, _LUXURY_RATE)    if lux_pool   else ""

    return tiles
