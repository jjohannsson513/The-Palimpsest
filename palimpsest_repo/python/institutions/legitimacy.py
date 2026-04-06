"""
institutions/legitimacy.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Legitimacy vector math, decay curves, threshold logic, and
contextual effective-legitimacy computation.

"Legitimacy is not power. It is permission to matter." — GDD §4
"""

from __future__ import annotations

import math
from typing import Any

from palimpsest.python.institutions.model import Institution, LEGITIMACY_WEIGHTS


# ── Decay Rates ───────────────────────────────────────────────────────────────

# Per-turn natural decay per source (without reinforcement)
BASE_DECAY: dict[str, float] = {
    "tradition":   0.002,   # Very slow — tradition is durable
    "performance": 0.008,   # Faster — needs ongoing success to maintain
    "belief":      0.003,   # Slow — beliefs are sticky
    "law":         0.004,   # Moderate — erodes without institutional maintenance
    "charisma":    0.010,   # Fastest — tied to specific persons
    "fear":        0.015,   # Fastest of all — coercion is expensive
}


def decay_legitimacy(inst: Institution, turns: int = 1) -> None:
    """Apply per-turn decay to all legitimacy sources."""
    for key, rate in BASE_DECAY.items():
        current = inst.legitimacy_sources.get(key, 0.0)
        inst.legitimacy_sources[key] = max(0.0, current - rate * turns)


def reinforce(inst: Institution, source: str, amount: float) -> None:
    """Boost a legitimacy source, capped at 1.0."""
    inst.legitimacy_sources[source] = min(
        1.0,
        inst.legitimacy_sources.get(source, 0.0) + amount
    )


# ── Effective Legitimacy ─────────────────────────────────────────────────────

def effective_legitimacy(inst: Institution, context: str = "general") -> float:
    """Weighted average legitimacy for a given audience context."""
    weights = LEGITIMACY_WEIGHTS.get(context, LEGITIMACY_WEIGHTS["general"])
    total = sum(inst.legitimacy_sources.get(k, 0.0) * w for k, w in weights.items())
    return total / sum(weights.values())


def legitimacy_profile(inst: Institution) -> dict[str, float]:
    """Return effective legitimacy in all contexts."""
    return {ctx: effective_legitimacy(inst, ctx) for ctx in LEGITIMACY_WEIGHTS}


# ── Threshold Logic ───────────────────────────────────────────────────────────

# Below these thresholds, consequences escalate
THRESHOLD_STRESS:      float = 0.30
THRESHOLD_FRACTURE:    float = 0.15
THRESHOLD_COLLAPSE:    float = 0.05


def legitimacy_consequences(inst: Institution) -> list[str]:
    """
    Return a list of active consequence labels based on current legitimacy.
    The caller decides how to apply them.
    """
    eff = effective_legitimacy(inst)
    consequences = []
    if eff < THRESHOLD_COLLAPSE:
        consequences.append("imminent_collapse")
    if eff < THRESHOLD_FRACTURE:
        consequences.append("fragmentation_risk")
        consequences.append("high_variance_events")
        consequences.append("delegation_unreliable")
    if eff < THRESHOLD_STRESS:
        consequences.append("belief_ossification")
        consequences.append("ai_behavior_erratic")
    return consequences


# ── Transfer & Inheritance ────────────────────────────────────────────────────

def transfer_legitimacy(
    source: Institution,
    target: Institution,
    fraction: float = 0.5,
    sources: list[str] | None = None,
) -> None:
    """
    Transfer a fraction of legitimacy from source to target.
    Used for succession, merger, vassalage.
    """
    keys = sources or list(LEGITIMACY_WEIGHTS["general"].keys())
    for k in keys:
        amount = source.legitimacy_sources.get(k, 0.0) * fraction
        target.legitimacy_sources[k] = min(
            1.0,
            target.legitimacy_sources.get(k, 0.0) + amount
        )
        source.legitimacy_sources[k] = max(
            0.0,
            source.legitimacy_sources.get(k, 0.0) - amount * 0.5
        )


# ── Delegation Drift ─────────────────────────────────────────────────────────

def compute_drift_rate(inst: Institution, oversight_level: float) -> float:
    """
    How fast a delegated institution drifts from its principal's intent.
    drift_rate ∈ [0, 1] per turn.

    oversight_level: 0.0 = fully autonomous, 1.0 = tightly controlled
    low legitimacy → faster drift (less alignment)
    high autonomy  → faster drift (less control)
    """
    base_drift = 0.02
    autonomy_factor  = 1.0 - oversight_level
    legitimacy_brake = effective_legitimacy(inst)
    drift = base_drift * autonomy_factor * (1.0 - legitimacy_brake * 0.5)
    return min(drift, 0.2)


def apply_drift(
    inst: Institution,
    contract: dict[str, Any],
    turns: int = 1,
) -> dict[str, float]:
    """
    Apply drift to a delegated institution's goal weights.
    Returns a dict of how much each goal weight shifted.
    """
    oversight = contract.get("oversight_level", 0.5)
    rate = compute_drift_rate(inst, oversight) * turns
    drift_log: dict[str, float] = {}

    policy_bias: dict[str, float] = contract.get("policy_bias", {})
    for goal_key, bias in policy_bias.items():
        # Drift away from principal's bias toward institution's own belief
        shift = (inst.legitimacy_sources.get("belief", 0.5) - bias) * rate
        drift_log[goal_key] = shift

    return drift_log
