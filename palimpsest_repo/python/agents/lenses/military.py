"""
agents/lenses/military.py — sphere-aware, cell_id based
"""
from __future__ import annotations
from typing import Any
from palimpsest.python.agents.council      import Proposal, lens
from palimpsest.python.agents.sphere_utils import build_cell_index, get_position
from palimpsest.python.institutions.model  import Institution
from palimpsest.python.institutions.legitimacy import effective_legitimacy

STANCE_AGGRESSIVE, STANCE_CAUTIOUS, STANCE_DEFENSIVE, STANCE_RETREATING, STANCE_GARRISON = 0,1,2,3,4


@lens
def military_lens(civ_id, state, civ_insts, registry):
    idx          = build_cell_index(state)
    proposals    = []
    civ_cities   = [i for i in civ_insts.values() if i.is_civic]
    civ_armies   = [i for i in civ_insts.values() if i.is_military and i.can_act()]
    enemy_cities = [i for i in registry.values() if i.is_civic and i.civ_id not in (-1, civ_id)]

    for army in civ_armies:
        leg, org = effective_legitimacy(army, "military"), army.organization
        pos = get_position(army)
        if pos is None:
            continue

        # ── Degraded: retreat or garrison ──────────────────────────────────
        if org < 0.2 or leg < 0.2:
            nearest = _nearest_city_cell(pos, civ_cities, idx)
            if nearest is not None:
                proposals.append(Proposal(army.id, "set_stance", {"stance": STANCE_RETREATING}, 2.0, "military", "low_org_retreat"))
                proposals.append(Proposal(army.id, "move", {"cell_id": idx.step_toward(pos, nearest)}, 1.8, "military", "retreating"))
            continue

        if org < 0.45:
            nearest = _nearest_city_cell(pos, civ_cities, idx)
            if nearest is not None:
                proposals.append(Proposal(army.id, "set_stance", {"stance": STANCE_GARRISON}, 1.5, "military", "stressed_garrison"))
                proposals.append(Proposal(army.id, "move", {"cell_id": idx.step_toward(pos, nearest)}, 1.3, "military", "moving_to_garrison"))
            continue

        # ── Healthy: advance on enemy ──────────────────────────────────────
        if not enemy_cities:
            if civ_cities:
                nearest = _nearest_city_cell(pos, civ_cities, idx)
                if nearest is not None:
                    proposals.append(Proposal(army.id, "set_stance", {"stance": STANCE_DEFENSIVE}, 0.8, "military", "no_enemies_defensive"))
            continue

        target = min(enemy_cities, key=lambda c: c.effective_legitimacy("civic"))
        target_pos = get_position(target)
        if target_pos is not None:
            next_step = idx.step_toward(pos, target_pos)
            stance = STANCE_CAUTIOUS if org < 0.7 else STANCE_AGGRESSIVE
            proposals.append(Proposal(army.id, "set_stance", {"stance": stance}, 1.0 * leg, "military", "advancing"))
            if next_step != pos:
                proposals.append(Proposal(army.id, "move", {"cell_id": next_step}, 0.9 * leg, "military", f"targeting_{target.id}"))

    return proposals


def _nearest_city_cell(pos, cities, idx):
    city_positions = [get_position(c) for c in cities if get_position(c) is not None]
    if not city_positions:
        return None
    return min(city_positions, key=lambda cp: idx.bfs_distance(pos, cp))
