"""
agents/lenses/expansion.py — sphere-aware, cell_id based
"""
from __future__ import annotations
from typing import Any
from palimpsest.python.agents.council      import Proposal, lens
from palimpsest.python.agents.sphere_utils import (
    CellIndex, build_cell_index, get_position,
    TERRAIN_FOOD_SCORE, FOUNDING_MIN_FOOD,
)
from palimpsest.python.institutions.model  import Institution
from palimpsest.python.institutions.legitimacy import effective_legitimacy


@lens
def expansion_lens(civ_id, state, civ_insts, registry):
    idx          = build_cell_index(state)
    proposals    = []
    civ_cities   = [i for i in civ_insts.values() if i.is_civic]
    settler_armies = [i for i in civ_insts.values() if i.is_military and _has_settler(i)]

    owned_cells: set[int] = set()
    for city in state.get("cities", []):
        for t in city.get("territory", []):
            cid = t if isinstance(t, int) else t.get("id", t.get("cell_id", -1))
            owned_cells.add(cid)

    for army in settler_armies:
        if not army.can_act():
            continue
        leg = effective_legitimacy(army, "military")
        pos = get_position(army)
        if pos is None:
            continue

        if not civ_cities:
            civ_name = state.get("civs", {}).get(str(civ_id), {}).get("name", "Civ")
            proposals.append(Proposal(
                institution_id=army.id, order_type="found_city",
                payload={"name": f"{civ_name} Prime"},
                weight=2.0 * leg, lens_name="expansion", reason="no_cities_yet",
            ))
            continue

        best_cell = _best_founding_cell(pos, idx, owned_cells)
        if best_cell is None:
            continue
        if best_cell == pos:
            proposals.append(Proposal(
                institution_id=army.id, order_type="found_city",
                payload={"name": _city_name(civ_id, len(civ_cities))},
                weight=1.5 * leg, lens_name="expansion", reason="good_site_reached",
            ))
        else:
            next_step = idx.step_toward(pos, best_cell)
            if next_step != pos:
                proposals.append(Proposal(
                    institution_id=army.id, order_type="move",
                    payload={"cell_id": next_step},
                    weight=0.9 * leg, lens_name="expansion", reason=f"scouting_{best_cell}",
                ))
    return proposals


def _has_settler(army):
    units = army.delegation_contract.get("units", []) or getattr(army, "units", [])
    return any(u.get("type") == "settler" for u in units) if isinstance(units, list) else False


def _best_founding_cell(origin, idx, owned_cells, scout_radius=5):
    candidates = idx.cells_within_hops(origin, scout_radius) + [origin]
    best_score, best_cell = -1, None
    for cell_id in candidates:
        if cell_id in owned_cells or not idx.is_land(cell_id):
            continue
        food = TERRAIN_FOOD_SCORE.get(idx.terrain(cell_id), 0)
        if food < FOUNDING_MIN_FOOD:
            continue
        score = food * 3 - idx.bfs_distance(origin, cell_id)
        if score > best_score:
            best_score, best_cell = score, cell_id
    return best_cell


def _city_name(civ_id, city_index):
    suffixes = ["Minor","Secundus","Reach","Hold","Haven","Watch","Ford","Gate","Stead","Crossing","Moor","Vale","Ridge","Strand","Keep"]
    return f"City {suffixes[city_index % len(suffixes)]}"
