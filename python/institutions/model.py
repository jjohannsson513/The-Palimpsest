"""
institutions/model.py
~~~~~~~~~~~~~~~~~~~~~
Python-side Institution dataclass. Mirrors the GDScript Institution.gd schema
exactly. This is the authoritative Python representation — all AI lenses,
analytics, and procgen work with this type.

"Everything is an Institution. They differ in scale, permissions, and
 narrative framing — not in underlying structure." — GDD §4
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Enums ─────────────────────────────────────────────────────────────────────

Scale = Literal["local", "regional", "civilizational", "transnational"]
Phase = Literal["stable", "stressed", "fracturing", "collapsed"]

# Legitimacy source keys (must match GDScript)
LEGITIMACY_SOURCES = ("tradition", "performance", "belief", "law", "charisma", "fear")

# ── Legitimacy Weights by Context ─────────────────────────────────────────────

LEGITIMACY_WEIGHTS: dict[str, dict[str, float]] = {
    "military":  {"performance": 0.4, "charisma": 0.3, "tradition": 0.2, "fear": 0.1},
    "civic":     {"performance": 0.3, "law": 0.3, "tradition": 0.2, "belief": 0.2},
    "religious": {"belief": 0.5, "tradition": 0.3, "charisma": 0.2},
    "dynastic":  {"tradition": 0.5, "law": 0.3, "belief": 0.2},
    "general":   {"tradition": 0.2, "performance": 0.2, "belief": 0.2, "law": 0.2, "charisma": 0.1, "fear": 0.1},
}


# ── Institution ───────────────────────────────────────────────────────────────

@dataclass
class Institution:
    # Identity
    id:           str
    label:        str = ""
    type_tags:    list[str] = field(default_factory=list)
    scale:        Scale = "regional"
    civ_id:       int = -1
    founded_tick: int = 0

    # Four fundamental fields
    organization: float = 1.0
    legitimacy_sources: dict[str, float] = field(default_factory=lambda: {
        "tradition":   0.5,
        "performance": 0.5,
        "belief":      0.5,
        "law":         0.5,
        "charisma":    0.3,
        "fear":        0.0,
    })
    memory_log:  list[dict[str, Any]] = field(default_factory=list)
    belief_set:  list[dict[str, Any]] = field(default_factory=list)

    # Capacity
    resources: dict[str, float] = field(default_factory=lambda: {
        "food": 0, "production": 0, "culture": 0, "conviction": 0,
        "research": 0, "trade_value": 0, "manpower": 0, "gold": 0,
    })
    action_budget: int = 3
    territory: list[dict[str, int]] = field(default_factory=list)  # [{"q": q, "r": r}]

    # Cognition
    goals:              list[dict[str, Any]] = field(default_factory=list)
    automation_level:   float = 0.0
    delegation_contract: dict[str, Any] = field(default_factory=dict)

    # Lineage
    parent_institution_ids: list[str] = field(default_factory=list)
    successor_candidates:   list[str] = field(default_factory=list)
    key_person_ids:         list[str] = field(default_factory=list)

    # ── Computed Properties ───────────────────────────────────────────────────

    @property
    def phase(self) -> Phase:
        leg = self.effective_legitimacy()
        if self.organization > 0.3 and leg > 0.3:
            return "stable"
        if self.organization > 0.15 and leg > 0.15:
            return "stressed"
        if self.organization > 0.0 or leg > 0.0:
            return "fracturing"
        return "collapsed"

    def effective_legitimacy(self, context: str = "general") -> float:
        weights = LEGITIMACY_WEIGHTS.get(context, LEGITIMACY_WEIGHTS["general"])
        total = sum(self.legitimacy_sources.get(k, 0.0) * w for k, w in weights.items())
        weight_sum = sum(weights.values())
        return total / weight_sum if weight_sum > 0 else 0.0

    def can_act(self) -> bool:
        return self.phase != "collapsed"

    def fragmentation_risk(self) -> float:
        if self.phase == "fracturing":
            return max(0.0, 1.0 - (self.organization + self.effective_legitimacy()) * 0.5)
        return 0.0

    def has_tag(self, tag: str) -> bool:
        return tag in self.type_tags

    # ── Derived Queries ───────────────────────────────────────────────────────

    @property
    def is_military(self) -> bool:
        return "military" in self.type_tags

    @property
    def is_civic(self) -> bool:
        return "civic" in self.type_tags

    @property
    def is_dynastic(self) -> bool:
        return "dynastic" in self.type_tags

    @property
    def position(self) -> int | None:
        """
        For mobile institutions: cell_id of current position.
        Territory is list[int] (cell_ids) in the sphere world.
        Falls back to dict territory for backward compatibility.
        """
        if not self.territory:
            return None
        t = self.territory[0]
        if isinstance(t, int):
            return t
        if isinstance(t, dict):
            return t.get("cell_id", t.get("id", None))
        return None


# ── Convenience Constructor ───────────────────────────────────────────────────

def make_institution(
    type_tags: list[str],
    civ_id: int,
    scale: Scale = "regional",
    label: str = "",
) -> Institution:
    return Institution(
        id=str(uuid.uuid4())[:12],
        label=label,
        type_tags=type_tags,
        scale=scale,
        civ_id=civ_id,
    )


# ── From Wire Dict ────────────────────────────────────────────────────────────

def institution_from_dict(d: dict[str, Any]) -> Institution:
    """Reconstruct an Institution from a Godot bridge payload dict."""
    inst = Institution(
        id            = d.get("id", str(uuid.uuid4())[:12]),
        label         = d.get("label", ""),
        type_tags     = d.get("type_tags", []),
        scale         = d.get("scale", "regional"),
        civ_id        = d.get("civ_id", -1),
        founded_tick  = d.get("founded_tick", 0),
        organization  = d.get("organization", 1.0),
        legitimacy_sources = d.get("legitimacy_sources", {
            s: 0.5 for s in LEGITIMACY_SOURCES
        }),
        belief_set       = d.get("belief_set", []),
        resources        = d.get("resources", {}),
        action_budget    = d.get("action_budget", 3),
        territory        = d.get("territory", []),
        delegation_contract = d.get("delegation_contract", {}),
        goals            = d.get("goals", []),
        automation_level = d.get("automation_level", 0.0),
        key_person_ids   = d.get("key_person_ids", []),
        # Preserve extra fields that lenses rely on (units, civic_identity, etc.)
    )
    return inst


def institutions_from_state(state: dict[str, Any]) -> dict[str, Institution]:
    """Build an id→Institution registry from a full planning_start payload."""
    registry: dict[str, Institution] = {}
    for key in ("cities", "armies", "dynasties"):
        for d in state.get(key, []):
            inst = institution_from_dict(d)
            registry[inst.id] = inst
    return registry
