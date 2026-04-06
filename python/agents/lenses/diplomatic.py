"""
agents/lenses/diplomatic.py — sphere-aware (positions unused, logic unchanged)
"""
from __future__ import annotations
from typing import Any
from palimpsest.python.agents.council      import Proposal, lens
from palimpsest.python.institutions.model  import Institution
from palimpsest.python.institutions.legitimacy import effective_legitimacy


@lens
def diplomatic_lens(civ_id, state, civ_insts, registry):
    proposals = []
    our_power = (
        sum(a.organization for a in civ_insts.values() if a.is_military) * 2
        + sum(1 for c in civ_insts.values() if c.is_civic) * 3
    )

    foreign_civs: set[int] = set()
    for inst in registry.values():
        if inst.civ_id not in (-1, civ_id):
            foreign_civs.add(inst.civ_id)

    for foreign_civ in foreign_civs:
        their_power = (
            sum(i.organization for i in registry.values() if i.is_military and i.civ_id == foreign_civ) * 2
            + sum(1 for i in registry.values() if i.is_civic and i.civ_id == foreign_civ) * 3
        )
        power_ratio  = our_power / max(their_power, 0.1)
        our_karma    = state.get("beliefs", {}).get(str(civ_id), {}).get("karma", 0.0)
        their_karma  = state.get("beliefs", {}).get(str(foreign_civ), {}).get("karma", 0.0)
        affinity     = 1.0 - abs(our_karma - their_karma)

        if power_ratio < 0.6:
            stance, reason, w = "peaceful", "power_deficit", 0.5 * affinity
        elif power_ratio > 1.8 and affinity < 0.4:
            stance, reason, w = "competitive", "dominant_position", 0.6
        else:
            stance, reason, w = "trade", "balanced_power", 0.4 * affinity

        proposals.append(Proposal(
            institution_id=f"dynasty_{civ_id}",
            order_type="diplomatic_stance",
            payload={"target_civ": foreign_civ, "stance": stance, "reason": reason},
            weight=w, lens_name="diplomatic", reason=reason,
        ))
    return proposals
