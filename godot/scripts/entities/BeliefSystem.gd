## BeliefSystem.gd
## ─────────────────────────────────────────────────────────────────────────────
## Tracks beliefs, karma alignment, and tenets for one civilization.
##
## Karma is a partially-hidden value tracking alignment between stated
## beliefs and actual actions. High karma = stability and prosperity.
## Low karma = variance, chaos, unrest.
##
## Beliefs are not static selections — they evolve based on events,
## artifacts, legendary figures, and accumulated memory. (GDD §11)
## ─────────────────────────────────────────────────────────────────────────────

class_name BeliefSystem
extends Resource

# ── Karma Alignment ───────────────────────────────────────────────────────────

enum KarmaAlignment {
	BENEVOLENT  =  1,
	INDIFFERENT =  0,
	MALEVOLENT  = -1,
}

# ── Belief Schema ─────────────────────────────────────────────────────────────
## Each belief: {
##   id, label, confidence [0–1], karma_alignment,
##   source: "pantheon" | "tenet" | "legend" | "artifact",
##   epoch_adopted, supporting_events[], contradicting_events[]
## }

# ── Properties ────────────────────────────────────────────────────────────────

@export var civ_id: int = -1

## Karma ranges from -1.0 (fully malevolent) to +1.0 (fully benevolent).
## Visible to the player only as vague signals (frequent chaos vs. prosperity).
@export var karma: float = 0.0

## Active beliefs array
@export var beliefs: Array = []

## Pantheon chosen in Era 1
@export var pantheon_id: String = ""
@export var pantheon_label: String = ""

## Active tenets
@export var tenets: Array = []   # Array of { id, label, alignment, adopted_tick }

## Artifacts held
@export var artifacts: Array = []  # { id, label, event_anchored, salience_boost }

## Legends recorded
@export var legends: Array = []    # { id, label, person_id?, place?, interpretation }

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func setup_beliefs(p_civ_id: int, p_pantheon: Dictionary) -> void:
	civ_id = p_civ_id
	pantheon_id    = p_pantheon.get("id", "")
	pantheon_label = p_pantheon.get("label", "")
	karma = 0.0
	## Seed one founding belief from the pantheon
	beliefs.append({
		"id":            "belief_pantheon_" + pantheon_id,
		"label":         p_pantheon.get("belief_label", "The old ways guide us"),
		"confidence":    0.7,
		"karma_alignment": p_pantheon.get("alignment", KarmaAlignment.INDIFFERENT),
		"source":        "pantheon",
		"epoch_adopted": 0,
	})

# ── Belief Operations ─────────────────────────────────────────────────────────

func add_tenet(tenet: Dictionary, tick: int) -> void:
	tenet["adopted_tick"] = tick
	tenets.append(tenet)
	## New tenet seeds a belief
	beliefs.append({
		"id":             "belief_tenet_" + tenet.get("id", ""),
		"label":          tenet.get("belief_label", tenet.get("label", "")),
		"confidence":     0.5,
		"karma_alignment": tenet.get("alignment", KarmaAlignment.INDIFFERENT),
		"source":         "tenet",
		"epoch_adopted":  tick,
	})

func get_belief(belief_id: String) -> Dictionary:
	for b in beliefs:
		if b["id"] == belief_id:
			return b
	return {}

func update_belief_confidence(belief_id: String, delta: float) -> void:
	for b in beliefs:
		if b["id"] == belief_id:
			b["confidence"] = clampf(b["confidence"] + delta, 0.0, 1.0)
			return

## When an event occurs, update confidence of aligned/contradicting beliefs.
func on_event(event_topic: String, event_payload: Dictionary, aligns_with: Array, contradicts: Array) -> void:
	for bid in aligns_with:
		update_belief_confidence(bid, 0.05)
	for bid in contradicts:
		update_belief_confidence(bid, -0.05)

# ── Karma ─────────────────────────────────────────────────────────────────────

## Called when an action is taken that aligns with or contradicts current tenets.
func apply_karma_delta(delta: float, reason: String = "") -> void:
	karma = clampf(karma + delta, -1.0, 1.0)

func karma_label() -> String:
	if karma > 0.6:  return "Virtuous"
	if karma > 0.2:  return "Balanced"
	if karma > -0.2: return "Neutral"
	if karma > -0.6: return "Strained"
	return "Cursed"

## Returns an event weight multiplier based on karma.
## High karma: stable/positive events more likely.
## Low karma: chaotic/negative events more likely.
func event_weight_multiplier(event_valence: float) -> float:
	## event_valence: +1.0 = positive, -1.0 = negative
	return 1.0 + karma * event_valence * 0.3

# ── Artifacts & Legends ───────────────────────────────────────────────────────

func add_artifact(artifact: Dictionary) -> void:
	artifacts.append(artifact)
	## Artifacts boost salience of the event they anchor
	var anchored_belief := artifact.get("anchors_belief_id", "")
	if not anchored_belief.is_empty():
		update_belief_confidence(anchored_belief, 0.1)

func add_legend(legend: Dictionary) -> void:
	legends.append(legend)
	## Legends reinforce the dominant interpretation of an event
	var anchored_belief := legend.get("anchors_belief_id", "")
	if not anchored_belief.is_empty():
		update_belief_confidence(anchored_belief, 0.08)

# ── Serialization ─────────────────────────────────────────────────────────────

func to_dict() -> Dictionary:
	return {
		"civ_id":          civ_id,
		"karma":           karma,
		"karma_label":     karma_label(),
		"pantheon":        pantheon_label,
		"belief_count":    beliefs.size(),
		"tenet_count":     tenets.size(),
		"artifact_count":  artifacts.size(),
		"beliefs":         beliefs,
		"tenets":          tenets,
	}
