"""
bridge/protocol.py
~~~~~~~~~~~~~~~~~~
Message envelope schema, typed constructors, and the canonical topic registry.
Stdlib-only — importable everywhere without pulling in agent/belief stacks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

MessageType = Literal["event", "command", "response", "error"]
Domain      = Literal["ai", "analytics", "procgen", "beliefs", "system"]
Phase       = Literal["planning", "execution", "observe"]


@dataclass
class Envelope:
    topic:   str
    payload: dict[str, Any]
    type:    MessageType = "event"
    domain:  Domain      = "system"
    phase:   Phase       = "planning"
    tick:    int         = 0
    id:      str         = field(default_factory=lambda: str(uuid.uuid4()))

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Envelope":
        return cls(
            id      = d.get("id",      str(uuid.uuid4())),
            type    = d.get("type",    "event"),
            domain  = d.get("domain",  "system"),
            topic   = d.get("topic",   ""),
            payload = d.get("payload", {}),
            phase   = d.get("phase",   "planning"),
            tick    = d.get("tick",    0),
        )

    @classmethod
    def command(cls, domain: Domain, topic: str, payload: dict, tick: int = 0) -> "Envelope":
        return cls(type="command", domain=domain, topic=topic, payload=payload, tick=tick)

    @classmethod
    def response(cls, domain: Domain, topic: str, payload: dict, tick: int = 0) -> "Envelope":
        return cls(type="response", domain=domain, topic=topic, payload=payload, tick=tick)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_ndjson(self) -> bytes:
        import json
        return (json.dumps(asdict(self)) + "\n").encode()

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.topic:
            errors.append("topic is required")
        if self.type not in ("event", "command", "response", "error"):
            errors.append(f"unknown type: {self.type!r}")
        if self.domain not in ("ai", "analytics", "procgen", "beliefs", "system"):
            errors.append(f"unknown domain: {self.domain!r}")
        return errors


# ── Topic Registry ────────────────────────────────────────────────────────────

class Topics:
    # ── Godot → Python (events) ───────────────────────────────────────────────
    HANDSHAKE              = "system.handshake"
    PLANNING_START         = "phase.planning_start"
    EXECUTION_START        = "phase.execution_start"
    TURN_END               = "phase.turn_end"
    INSTITUTION_CREATED    = "institution.created"
    INSTITUTION_CHANGED    = "institution.changed"
    INSTITUTION_DESTROYED  = "institution.destroyed"
    TILE_SELECTED          = "map.tile_selected"
    PLAYER_ACTION          = "player.action"

    # ── Python → Godot (commands) ─────────────────────────────────────────────
    SYSTEM_READY           = "system.ready"
    AI_INSTITUTION_ORDER   = "ai.institution_order"
    AI_PLANNING_DONE       = "ai.planning_done"
    PROCGEN_APPLY_MAP      = "procgen.apply_map"
    PROCGEN_APPLY_INSTS    = "procgen.apply_institutions"
    BELIEFS_KARMA_UPDATE   = "beliefs.karma_update"
    BELIEFS_EVENT_INTERP   = "beliefs.event_interpretation"
    ANALYTICS_REPORT       = "analytics.report"
