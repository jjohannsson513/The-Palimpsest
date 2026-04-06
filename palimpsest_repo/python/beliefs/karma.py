"""
beliefs/karma.py — extended with bridge handler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Karma accumulation, tenet-alignment scoring, and event weight modulation.
The `handle_beliefs` function is the bridge-routed handler for
player.action events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from palimpsest.python.bridge.protocol import Envelope, Topics

log = logging.getLogger(__name__)


@dataclass
class KarmaTracker:
    civ_id: int
    karma: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)
    tenets: list[dict[str, Any]] = field(default_factory=list)

    def apply_action(self, action_type: str, payload: dict[str, Any], tick: int) -> float:
        delta = self._score_action(action_type, payload)
        self.karma = max(-1.0, min(1.0, self.karma + delta))
        self.history.append({
            "tick": tick, "action": action_type,
            "delta": delta, "karma_after": self.karma,
        })
        if abs(delta) > 0.04:
            log.info("Karma[civ=%d] %s -> %+.3f (now %.3f)", self.civ_id, action_type, delta, self.karma)
        return delta

    def _score_action(self, action: str, payload: dict[str, Any]) -> float:
        if not self.tenets:
            return 0.0
        total = 0.0
        for tenet in self.tenets:
            alignment: int = tenet.get("alignment", 0)
            affinity = tenet.get("action_affinity", {})
            weight = affinity.get(action, 0.0)
            total += alignment * weight * 0.1
        return max(-0.2, min(0.2, total))

    def event_weight_multiplier(self, event_valence: float) -> float:
        return 1.0 + self.karma * event_valence * 0.3

    @property
    def label(self) -> str:
        if self.karma > 0.6:  return "Virtuous"
        if self.karma > 0.2:  return "Balanced"
        if self.karma > -0.2: return "Neutral"
        if self.karma > -0.6: return "Strained"
        return "Cursed"

    def to_dict(self) -> dict[str, Any]:
        return {"civ_id": self.civ_id, "karma": self.karma, "label": self.label}


# Global tracker registry
_trackers: dict[int, KarmaTracker] = {}


def _get_tracker(civ_id: int) -> KarmaTracker:
    if civ_id not in _trackers:
        _trackers[civ_id] = KarmaTracker(civ_id=civ_id)
    return _trackers[civ_id]


async def handle_beliefs(msg: dict[str, Any], session: Any) -> list[bytes]:
    payload     = msg.get("payload", {})
    tick: int   = msg.get("tick", 0)
    civ_id: int = payload.get("civ_id", 0)
    action: str = payload.get("action_type", "")

    tracker = _get_tracker(civ_id)
    delta   = tracker.apply_action(action, payload, tick)

    if abs(delta) < 0.001:
        return []

    env = Envelope.command(
        domain  = "beliefs",
        topic   = Topics.BELIEFS_KARMA_UPDATE,
        payload = {
            "civ_id": civ_id,
            "delta":  round(delta, 4),
            "reason": action,
            "karma":  round(tracker.karma, 4),
            "label":  tracker.label,
        },
        tick=tick,
    )
    return [env.to_ndjson()]
