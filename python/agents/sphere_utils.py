"""
agents/sphere_utils.py
~~~~~~~~~~~~~~~~~~~~~~
Shared helpers for all AI lenses operating on a spherical Voronoi world.

The state dict received from Godot (via phase.planning_start) contains
a flat 'cells' list. These helpers build fast lookup structures from it
and expose distance / proximity queries that replace the old axial math.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

# ── Cell index ────────────────────────────────────────────────────────────────

class CellIndex:
    """
    Builds O(1) cell lookup and BFS-distance cache from the state payload.
    Construct once per planning turn; pass to all lenses.
    """
    __slots__ = ("cells", "adjacency", "_dist_cache")

    def __init__(self, state: dict[str, Any]) -> None:
        raw_cells = state.get("cells", [])
        self.cells: dict[int, dict[str, Any]] = {c["id"]: c for c in raw_cells}
        # adjacency: cell_id → list[cell_id]
        self.adjacency: dict[int, list[int]] = {
            c["id"]: c.get("neighbors", []) for c in raw_cells
        }
        self._dist_cache: dict[tuple[int, int], int] = {}

    # ── Distance ──────────────────────────────────────────────────────────────

    def bfs_distance(self, a: int, b: int) -> int:
        """Hop count between two cells (exact graph distance)."""
        if a == b:
            return 0
        key = (min(a, b), max(a, b))
        if key in self._dist_cache:
            return self._dist_cache[key]

        visited = {a}
        queue: deque[tuple[int, int]] = deque([(a, 0)])
        while queue:
            cid, dist = queue.popleft()
            for n in self.adjacency.get(cid, []):
                if n == b:
                    self._dist_cache[key] = dist + 1
                    return dist + 1
                if n not in visited:
                    visited.add(n)
                    queue.append((n, dist + 1))

        self._dist_cache[key] = 9999
        return 9999

    def angular_dist(self, a: int, b: int) -> float:
        """Great-circle angular distance in radians between two cell centers."""
        ca = self.cells[a]["center"]
        cb = self.cells[b]["center"]
        dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(ca, cb))))
        return math.acos(dot)

    # ── Queries ───────────────────────────────────────────────────────────────

    def cells_within_hops(self, origin: int, hops: int) -> list[int]:
        """Return all cell IDs reachable within `hops` steps."""
        visited = {origin}
        frontier = [origin]
        for _ in range(hops):
            next_frontier = []
            for cid in frontier:
                for n in self.adjacency.get(cid, []):
                    if n not in visited:
                        visited.add(n)
                        next_frontier.append(n)
            frontier = next_frontier
        return list(visited - {origin})

    def nearest_cell(self, origin: int, candidates: list[int]) -> int | None:
        """Return the candidate cell with the lowest BFS hop count from origin."""
        if not candidates:
            return None
        return min(candidates, key=lambda c: self.bfs_distance(origin, c))

    def terrain(self, cell_id: int) -> int:
        return self.cells.get(cell_id, {}).get("terrain", -1)

    def height(self, cell_id: int) -> float:
        return self.cells.get(cell_id, {}).get("height", 0.0)

    def is_land(self, cell_id: int) -> bool:
        return not self.cells.get(cell_id, {}).get("is_oceanic", True)

    def is_owned(self, cell_id: int, civ_id: int | None = None) -> bool:
        """True if any city's territory includes this cell."""
        return self.cells.get(cell_id, {}).get("owner_institution_id", "") != ""

    def step_toward(self, origin: int, target: int) -> int:
        """
        Return the neighbor of `origin` that is closest (by BFS) to `target`.
        Falls back to origin if no neighbors exist.
        """
        neighbors = self.adjacency.get(origin, [])
        if not neighbors:
            return origin
        return min(neighbors, key=lambda n: self.bfs_distance(n, target))


# ── Terrain food score table (matches procgen/climate.py terrain codes) ───────

TERRAIN_FOOD_SCORE: dict[int, int] = {
    0:  0,   # DEEP_OCEAN
    1:  1,   # OCEAN
    2:  2,   # COASTAL
    3:  0,   # POLAR_ICE
    4:  1,   # TUNDRA
    5:  1,   # TAIGA
    6:  3,   # TEMPERATE
    7:  4,   # GRASSLAND
    8:  2,   # SAVANNA
    9:  3,   # MEDITERRANEAN
    10: 3,   # MONSOON
    11: 3,   # TROPICAL
    12: 1,   # DESERT
    13: 0,   # ARID_DESERT
    14: 1,   # XERIC
    15: 2,   # DRY_STEPPE
    16: 1,   # MONTANE
    17: 0,   # MONTANE_IMPASSABLE
    18: 0,   # WASTELANDS
}

FOUNDING_MIN_FOOD = 2   # Minimum food score to consider a cell for settlement


# ── State helpers ─────────────────────────────────────────────────────────────

def get_position(inst: Any) -> int | None:
    """
    Extract cell_id position from an Institution.
    Army.position is an int cell_id in the sphere world.
    Falls back to territory[0] if position is missing.
    """
    # Direct cell_id (sphere world)
    pos = getattr(inst, "position", None)
    if isinstance(pos, int) and pos >= 0:
        return pos
    # Wire-dict fallback (from institution_from_dict)
    if isinstance(pos, dict):
        return pos.get("cell_id", None)
    # Try territory list
    territory = getattr(inst, "territory", [])
    if territory:
        t = territory[0]
        if isinstance(t, int):
            return t
        if isinstance(t, dict):
            return t.get("cell_id", t.get("id", None))
    return None


def build_cell_index(state: dict[str, Any]) -> CellIndex:
    return CellIndex(state)
