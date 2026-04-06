"""
analytics/pipeline.py
~~~~~~~~~~~~~~~~~~~~~
Passive event accumulator. Ingests all game events and computes
institution-aware metrics on turn_end, pushing analytics.report
commands back to Godot's overlay.

Non-blocking: Godot never waits on analytics responses.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from palimpsest.python.bridge.protocol import Envelope, Topics
from palimpsest.python.institutions.model import institution_from_dict

log = logging.getLogger(__name__)


# ── Accumulator ───────────────────────────────────────────────────────────────

@dataclass
class GameStateAccumulator:
    # Turn-by-turn score history: tick → { civ_id_str: score }
    score_history:    list[dict[str, Any]] = field(default_factory=list)
    # Institution snapshots by tick
    city_counts:      dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    army_org_history: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    # Raw event log
    events:           list[dict[str, Any]] = field(default_factory=list)
    # Legitimacy trajectory
    leg_history:      dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def ingest(self, topic: str, payload: dict[str, Any], tick: int) -> None:
        self.events.append({"tick": tick, "topic": topic, "payload": payload})

        if topic == Topics.PLANNING_START:
            self._ingest_state(payload, tick)

        elif topic == Topics.TURN_END:
            scores = payload.get("scores", {})
            self.score_history.append({"tick": tick, "scores": scores})

    def _ingest_state(self, state: dict[str, Any], tick: int) -> None:
        """Index institution state at planning_start."""
        for city_dict in state.get("cities", []):
            cid = str(city_dict.get("civ_id", -1))
            self.city_counts[cid].append(1)

        for army_dict in state.get("armies", []):
            aid = army_dict.get("id", "?")
            org = army_dict.get("organization", 1.0)
            self.army_org_history[aid].append(org)
            # Legitimacy
            leg_sources = army_dict.get("legitimacy_sources", {})
            if leg_sources:
                avg_leg = sum(leg_sources.values()) / max(len(leg_sources), 1)
                self.leg_history[aid].append(avg_leg)

    def compute_metrics(self, tick: int) -> list[dict[str, Any]]:
        metrics: list[dict[str, Any]] = []

        # ── Score leader ─────────────────────────────────────────────────────
        if self.score_history:
            latest = self.score_history[-1]["scores"]
            if latest:
                leader = max(latest, key=lambda k: latest[k])
                metrics.append({
                    "metric":    "score_leader",
                    "value":     leader,
                    "breakdown": latest,
                })

        # ── City count by civ ────────────────────────────────────────────────
        city_totals = {cid: len(v) for cid, v in self.city_counts.items()}
        if city_totals:
            metrics.append({
                "metric":    "city_count_by_civ",
                "value":     sum(city_totals.values()),
                "breakdown": city_totals,
            })

        # ── Average army organization ────────────────────────────────────────
        org_avgs = {
            aid: round(sum(v) / len(v), 3)
            for aid, v in self.army_org_history.items()
            if v
        }
        if org_avgs:
            most_degraded = min(org_avgs, key=org_avgs.get)
            metrics.append({
                "metric":    "most_degraded_army",
                "value":     most_degraded,
                "breakdown": org_avgs,
            })

        # ── Legitimacy warning ───────────────────────────────────────────────
        low_leg = {
            iid: round(vals[-1], 3)
            for iid, vals in self.leg_history.items()
            if vals and vals[-1] < 0.30
        }
        if low_leg:
            metrics.append({
                "metric":    "low_legitimacy_warning",
                "value":     list(low_leg.keys()),
                "breakdown": low_leg,
            })

        return metrics


_acc = GameStateAccumulator()


# ── Handler ───────────────────────────────────────────────────────────────────

async def handle_analytics(msg: dict[str, Any], session: Any) -> list[bytes]:
    """
    Called for all game.*, institution.*, map.*, and phase.turn_end events.
    Passive ingestion for most; sends reports on turn_end only.
    """
    topic:   str = msg.get("topic", "")
    payload: dict = msg.get("payload", {})
    tick:    int  = msg.get("tick", 0)

    _acc.ingest(topic, payload, tick)

    if topic != Topics.TURN_END:
        return []

    metrics = _acc.compute_metrics(tick)
    responses: list[bytes] = []

    for m in metrics:
        env = Envelope.command(
            domain  = "analytics",
            topic   = Topics.ANALYTICS_REPORT,
            payload = m,
            tick    = tick,
        )
        responses.append(env.to_ndjson())
        log.info("Analytics tick=%d  metric=%-30s value=%s", tick, m["metric"], m["value"])

    return responses
