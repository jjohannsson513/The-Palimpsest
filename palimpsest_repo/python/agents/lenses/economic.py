"""
agents/lenses/economic.py — sphere-aware (city positions unused, logic unchanged)
"""
from __future__ import annotations
from typing import Any
from palimpsest.python.agents.council      import Proposal, lens
from palimpsest.python.institutions.model  import Institution
from palimpsest.python.institutions.legitimacy import effective_legitimacy

_IDENTITY_QUEUE = {
    0: ["market","trade_post","harbor"],       # MERCANTILE
    1: ["barracks","walls","armory"],          # MILITARIZED
    2: ["library","academy","observatory"],    # SCHOLARLY
    3: ["shrine","temple","holy_site"],        # SACRED
    4: ["granary","watchtower","stable"],      # FRONTIER
    5: ["entertainment","bath_house","garden"],# DECADENT
    6: ["courthouse","road","admin_hall"],     # ADMINISTRATIVE
}


@lens
def economic_lens(civ_id, state, civ_insts, registry):
    proposals = []
    for city in [i for i in civ_insts.values() if i.is_civic]:
        if not city.can_act():
            continue
        leg       = effective_legitimacy(city, "civic")
        identity  = city.delegation_contract.get("civic_identity", {})
        dominant  = max(identity, key=lambda k: identity[k], default=4)
        existing  = city.delegation_contract.get("buildings", [])
        next_build = next((b for b in _IDENTITY_QUEUE.get(int(dominant), ["granary"]) if b not in existing), None)
        if next_build:
            proposals.append(Proposal(
                institution_id=city.id, order_type="queue_production",
                payload={"item": next_build, "type": "building"},
                weight=0.7 * leg, lens_name="economic", reason=f"build_{next_build}",
            ))
        food = city.resources.get("food", 0)
        pop  = city.delegation_contract.get("population", 1)
        if food < pop * 0.5 and "granary" not in existing:
            proposals.append(Proposal(
                institution_id=city.id, order_type="queue_production",
                payload={"item": "granary", "type": "building"},
                weight=1.5, lens_name="economic", reason="food_crisis",
            ))
    return proposals
