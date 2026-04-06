"""
agents/council.py
~~~~~~~~~~~~~~~~~
The AI council: a meta-interpreter that collects proposals from
institution-aware lenses and resolves them into coherent orders.

Architecture:
  1. Lenses are pure functions: lens(civ_id, state, registry) → list[Proposal]
  2. Council collects all proposals, weights them, resolves conflicts
  3. Returns a list of ai.institution_order command bytes

Lens registration uses the @lens decorator. Lenses are automatically
imported from the agents/lenses/ subpackage.
"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from palimpsest.python.bridge.protocol import Envelope, Topics
from palimpsest.python.institutions.model import (
    Institution,
    institutions_from_state,
)
from palimpsest.python.institutions.legitimacy import effective_legitimacy

log = logging.getLogger(__name__)

# ── Proposal ──────────────────────────────────────────────────────────────────

@dataclass
class Proposal:
    """A single action proposed by a lens for one institution."""
    institution_id: str
    order_type:     str                  # "move", "found_city", "set_stance", …
    payload:        dict[str, Any] = field(default_factory=dict)
    weight:         float = 1.0          # Confidence in this proposal
    lens_name:      str = ""
    reason:         str = ""


# ── Lens Registry ─────────────────────────────────────────────────────────────

_LENSES: list[Callable] = []

def lens(fn: Callable) -> Callable:
    """Decorator: register a function as a decision lens."""
    _LENSES.append(fn)
    log.debug("Registered lens: %s", fn.__name__)
    return fn


def _import_all_lenses() -> None:
    """Auto-import all modules in agents/lenses/ to trigger @lens decorators."""
    import palimpsest.python.agents.lenses as lenses_pkg
    for _, mod_name, _ in pkgutil.iter_modules(lenses_pkg.__path__):
        importlib.import_module(f"palimpsest.python.agents.lenses.{mod_name}")


# ── Meta-Interpreter ──────────────────────────────────────────────────────────

def _resolve_proposals(proposals: list[Proposal]) -> list[Proposal]:
    """
    Conflict resolution: keep highest-weight proposal per (institution_id, order_type).
    Two lenses proposing contradictory moves for the same army → higher weight wins.
    """
    best: dict[str, Proposal] = {}
    for p in proposals:
        key = f"{p.institution_id}:{p.order_type}"
        if key not in best or p.weight > best[key].weight:
            best[key] = p
    return list(best.values())


def _legitimacy_weight_multiplier(inst: Institution) -> float:
    """
    Low-legitimacy institutions get reduced action budget.
    Stressed/fracturing institutions may refuse orders.
    """
    eff = effective_legitimacy(inst)
    if eff < 0.15:
        return 0.0   # Collapsed / won't comply
    if eff < 0.30:
        return 0.5   # Very unreliable
    return 1.0


# ── Handler ───────────────────────────────────────────────────────────────────

async def handle_ai(msg: dict[str, Any], session: Any) -> list[bytes]:
    """
    Called when Godot sends phase.planning_start.
    Returns encoded command bytes.
    """
    _import_all_lenses()

    state:   dict = msg.get("payload", {})
    tick:    int  = msg.get("tick", 0)
    human_civ: int = state.get("human_civ", 0)

    registry = institutions_from_state(state)
    all_civs: dict = state.get("civs", {})

    all_proposals: list[Proposal] = []

    for civ_id_str, civ_data in all_civs.items():
        civ_id = int(civ_id_str)
        if civ_id == human_civ:
            continue   # Don't play for the human

        civ_insts = {
            iid: inst for iid, inst in registry.items()
            if inst.civ_id == civ_id
        }

        for lens_fn in _LENSES:
            try:
                proposals = lens_fn(civ_id, state, civ_insts, registry)
                all_proposals.extend(proposals or [])
            except Exception as exc:
                log.exception("Lens %s failed for civ %d: %s", lens_fn.__name__, civ_id, exc)

    resolved = _resolve_proposals(all_proposals)
    log.info("Tick %d: %d AI proposals → %d resolved orders", tick, len(all_proposals), len(resolved))

    responses: list[bytes] = []

    for proposal in resolved:
        inst = registry.get(proposal.institution_id)
        if inst is None:
            continue
        ## Skip if institution is too illegitimate to act
        if _legitimacy_weight_multiplier(inst) == 0.0:
            log.debug("Skipping order for collapsed institution %s", proposal.institution_id)
            continue

        payload = {"institution_id": proposal.institution_id, "order_type": proposal.order_type}
        payload.update(proposal.payload)

        env = Envelope.command(
            domain  = "ai",
            topic   = Topics.AI_INSTITUTION_ORDER,
            payload = payload,
            tick    = tick,
        )
        responses.append(env.to_ndjson())

    ## Always close with planning_done
    done = Envelope.command("ai", Topics.AI_PLANNING_DONE, {"tick": tick}, tick)
    responses.append(done.to_ndjson())
    return responses
