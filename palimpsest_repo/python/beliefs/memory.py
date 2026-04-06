"""
beliefs/memory.py
~~~~~~~~~~~~~~~~~
Institutional memory: event encoding, distortion over time, and
institution-specific recall. Different institutions remember the
same event differently.

"History does not constrain behavior — beliefs about history do." — GDD §4
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    topic:      str
    data:       dict[str, Any]
    tick:       int
    salience:   float = 0.5     # How prominent this memory is [0–1]
    distortion: float = 0.0     # Accumulated drift from original [0–1]
    # Institution-specific interpretation applied at encode time
    interpretation: str = ""


@dataclass
class InstitutionalMemory:
    institution_id: str
    max_entries: int = 64
    entries: list[MemoryEntry] = field(default_factory=list)

    def encode(
        self,
        topic: str,
        data: dict[str, Any],
        tick: int,
        salience: float = 0.5,
        interpretation: str = "",
    ) -> MemoryEntry:
        entry = MemoryEntry(
            topic=topic,
            data=data,
            tick=tick,
            salience=salience,
            interpretation=interpretation,
        )
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            # Drop the lowest-salience memory (not necessarily oldest)
            self.entries.sort(key=lambda e: e.salience, reverse=True)
            self.entries = self.entries[:self.max_entries]
        return entry

    def age_all(self, turns: int = 1) -> None:
        """
        Each turn: salience decays and distortion grows.
        High-salience memories decay slower.
        Memories that become myths (distortion > 0.7) flip to anchors —
        they stabilize rather than fade.
        """
        for entry in self.entries:
            if entry.distortion > 0.7:
                # Mythologized — salience stabilizes
                entry.salience = max(entry.salience, 0.4)
            else:
                decay = 0.01 * turns * (1.0 - entry.salience * 0.5)
                entry.salience = max(0.0, entry.salience - decay)
                # Distortion grows slowly
                entry.distortion = min(1.0, entry.distortion + 0.005 * turns)

    def recall(
        self,
        topic: str | None = None,
        min_salience: float = 0.1,
    ) -> list[MemoryEntry]:
        result = [e for e in self.entries if e.salience >= min_salience]
        if topic:
            result = [e for e in result if e.topic == topic]
        return sorted(result, key=lambda e: e.salience, reverse=True)

    def most_salient(self, n: int = 5) -> list[MemoryEntry]:
        return sorted(self.entries, key=lambda e: e.salience, reverse=True)[:n]

    def to_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "topic":          e.topic,
                "tick":           e.tick,
                "salience":       round(e.salience, 3),
                "distortion":     round(e.distortion, 3),
                "interpretation": e.interpretation,
            }
            for e in self.most_salient(10)
        ]


# ── Multi-Institution Event Encoding ─────────────────────────────────────────

def encode_event_for_all(
    event_topic: str,
    event_data: dict[str, Any],
    tick: int,
    memories: dict[str, InstitutionalMemory],
    salience_by_institution: dict[str, float] | None = None,
) -> None:
    """
    Encode one event into multiple institutional memories with
    institution-specific salience and interpretive framing.

    Different institutions notice different aspects of the same event.
    """
    default_salience = salience_by_institution or {}

    for inst_id, memory in memories.items():
        salience = default_salience.get(inst_id, 0.3)
        interpretation = _interpret_for(inst_id, event_topic, event_data)
        memory.encode(
            topic=event_topic,
            data=event_data,
            tick=tick,
            salience=salience,
            interpretation=interpretation,
        )
        log.debug(
            "Memory[%s] encoded '%s' salience=%.2f: '%s'",
            inst_id, event_topic, salience, interpretation
        )


def _interpret_for(inst_id: str, topic: str, data: dict[str, Any]) -> str:
    """
    Generate an institution-specific interpretation of an event.
    In a full implementation this would query the institution's belief set.
    For now: deterministic framing based on institution type prefix.
    """
    if "army" in inst_id or "military" in inst_id:
        return _military_frame(topic, data)
    if "dynasty" in inst_id:
        return _dynastic_frame(topic, data)
    if "city" in inst_id:
        return _civic_frame(topic, data)
    return _neutral_frame(topic, data)


def _military_frame(topic: str, data: dict[str, Any]) -> str:
    frames = {
        "battle_result":  "The lines held — proof that discipline wins wars.",
        "city_founded":   "A new position secured on the frontier.",
        "famine":         "Rations depleted; discipline tested.",
        "victory":        "Our strength is proven. The weak yield.",
    }
    return frames.get(topic, f"Significant event: {topic}")


def _dynastic_frame(topic: str, data: dict[str, Any]) -> str:
    frames = {
        "battle_result":  "Our bloodline proved its valor.",
        "city_founded":   "The dynasty extends its reach.",
        "famine":         "Providence tests the righteous ruler.",
        "victory":        "As was foretold, our house prevails.",
    }
    return frames.get(topic, f"A matter of dynastic significance: {topic}")


def _civic_frame(topic: str, data: dict[str, Any]) -> str:
    frames = {
        "battle_result":  "The soldiers passed through; the city endures.",
        "city_founded":   "Another settlement joins the network of civilization.",
        "famine":         "The granaries emptied. The people suffered.",
        "victory":        "Trade routes re-opened. Prosperity returns.",
    }
    return frames.get(topic, f"City record: {topic}")


def _neutral_frame(topic: str, data: dict[str, Any]) -> str:
    return f"Recorded: {topic}"
