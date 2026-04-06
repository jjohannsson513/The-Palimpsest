## Institution.gd
## ─────────────────────────────────────────────────────────────────────────────
## Base resource class shared by ALL entities in The Palimpsest:
## armies, cities, dynasties, religions, factions, bandit clans, empires.
##
## "Everything is an Institution. They differ in scale, permissions, and
##  narrative framing — not in underlying structure." — GDD §4
##
## Usage:
##   var inst := Institution.new()
##   inst.setup("army_001", ["military", "mobile"], InstitutionScale.REGIONAL)
##   inst.organization = 0.85
##   inst.legitimacy_sources["tradition"] = 0.6
## ─────────────────────────────────────────────────────────────────────────────

class_name Institution
extends Resource

# ── Enums ─────────────────────────────────────────────────────────────────────

enum Scale {
	LOCAL          = 0,   # A village, a patrol, a minor cult
	REGIONAL       = 1,   # A city, an army, a noble house
	CIVILIZATIONAL = 2,   # A major power, a great religion
	TRANSNATIONAL  = 3,   # A trade league, a world religion, an empire
}

enum Phase {
	STABLE     = 0,   # Normal operation
	STRESSED   = 1,   # Below organization/legitimacy thresholds
	FRACTURING = 2,   # Active fragmentation risk
	COLLAPSED  = 3,   # Destroyed or absorbed
}

# ── Identity ──────────────────────────────────────────────────────────────────

@export var id:         String = ""
@export var label:      String = ""          # Display name
@export var type_tags:  Array[String] = []   # ["military", "mobile"], ["civic", "anchored"], etc.
@export var scale:      Scale = Scale.LOCAL
@export var civ_id:     int = -1             # Owning civilization (-1 = independent)
@export var founded_tick: int = 0

# ── Four Fundamental Fields ───────────────────────────────────────────────────

## Organization [0.0 – 1.0]: internal coherence, doctrine, logistics, trust.
## Below 0.3 = STRESSED. Below 0.15 = FRACTURING risk.
@export var organization: float = 1.0

## Legitimacy is a multi-source vector (not a single number).
## Keys: "tradition", "performance", "belief", "law", "charisma", "fear"
## Each component decays independently; the effective legitimacy is a
## weighted dot product against context (see legitimacy.py on Python side).
@export var legitimacy_sources: Dictionary = {
	"tradition":   0.5,
	"performance": 0.5,
	"belief":      0.5,
	"law":         0.5,
	"charisma":    0.3,
	"fear":        0.0,
}

## Memory: list of { tick, topic, salience, distortion } dicts.
## Stored here as raw events; interpreted by Python memory module.
@export var memory_log: Array = []

## Belief set: active interpretive models.
## Each entry: { id, label, confidence, karma_alignment }
@export var belief_set: Array = []

# ── Capacity & Resources ──────────────────────────────────────────────────────

@export var resources: Dictionary = {
	"food":        0,
	"production":  0,
	"culture":     0,
	"conviction":  0,
	"research":    0,
	"trade_value": 0,
	"manpower":    0,
	"gold":        0,
}

@export var action_budget: int = 3      # How much this institution can do per turn
@export var territory: Array = []       # Array of axial Vector2i tiles

# ── Cognition / Goals ─────────────────────────────────────────────────────────

## Active goals — drives AI decision making for this institution.
## Each: { type, target_id, priority, expires_tick }
@export var goals: Array = []

## Automation level: 0.0 = full manual, 1.0 = full delegation
@export var automation_level: float = 0.0

## Delegation contract reference (set when delegated by parent institution)
@export var delegation_contract: Dictionary = {}

# ── Lineage ───────────────────────────────────────────────────────────────────

@export var parent_institution_ids: Array[String] = []
@export var successor_candidates: Array[String] = []  # person IDs
@export var key_person_ids: Array[String] = []        # leaders, courtiers attached

# ── Derived State ─────────────────────────────────────────────────────────────

var phase: Phase = Phase.STABLE

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func setup(p_id: String, p_tags: Array[String], p_scale: Scale) -> void:
	id    = p_id
	type_tags = p_tags
	scale = p_scale

func _to_dict() -> Dictionary:
	## Serialize to wire-format dict (for bridge events).
	return {
		"id":                  id,
		"label":               label,
		"type_tags":           type_tags,
		"scale":               scale,
		"civ_id":              civ_id,
		"founded_tick":        founded_tick,
		"organization":        organization,
		"legitimacy_sources":  legitimacy_sources,
		"belief_set":          belief_set,
		"resources":           resources,
		"action_budget":       action_budget,
		"territory":           territory.map(func(v): return {"q": v.x, "r": v.y}),
		"goals":               goals,
		"automation_level":    automation_level,
		"key_person_ids":      key_person_ids,
	}

# ── Organization Logic ────────────────────────────────────────────────────────

## Apply a shock to organization (defeats, disasters, betrayals).
func apply_org_shock(magnitude: float, source: String = "") -> void:
	organization = clampf(organization - magnitude, 0.0, 1.0)
	_record_memory("org_shock", { "magnitude": magnitude, "source": source }, magnitude)
	_update_phase()

## Gradual recovery toward natural organization level (call each turn).
func recover_organization(rate: float = 0.02) -> void:
	var natural := _natural_org_level()
	if organization < natural:
		organization = minf(organization + rate, natural)
	_update_phase()

func _natural_org_level() -> float:
	## Natural org ceiling depends on legitimacy and delegation quality.
	var avg_leg := legitimacy_sources.values().reduce(func(a, b): return a + b, 0.0) \
				   / float(legitimacy_sources.size())
	return clampf(0.4 + avg_leg * 0.6, 0.2, 1.0)

# ── Legitimacy ────────────────────────────────────────────────────────────────

## Boost a legitimacy component (e.g., after a victory).
func boost_legitimacy(source: String, amount: float) -> void:
	if source in legitimacy_sources:
		legitimacy_sources[source] = clampf(legitimacy_sources[source] + amount, 0.0, 1.0)

## Decay all legitimacy components slightly each turn.
func decay_legitimacy(base_rate: float = 0.005) -> void:
	for key in legitimacy_sources:
		var decay := base_rate * (1.5 if key == "fear" else 1.0)
		legitimacy_sources[key] = maxf(legitimacy_sources[key] - decay, 0.0)

## Effective legitimacy: weighted average for a given audience context.
func effective_legitimacy(context: String = "general") -> float:
	var weights := _legitimacy_weights(context)
	var total := 0.0
	var weight_sum := 0.0
	for key in weights:
		total      += legitimacy_sources.get(key, 0.0) * weights[key]
		weight_sum += weights[key]
	return total / weight_sum if weight_sum > 0 else 0.0

func _legitimacy_weights(context: String) -> Dictionary:
	match context:
		"military": return { "performance": 0.4, "charisma": 0.3, "tradition": 0.2, "fear": 0.1 }
		"civic":    return { "performance": 0.3, "law": 0.3, "tradition": 0.2, "belief": 0.2 }
		"religious":return { "belief": 0.5, "tradition": 0.3, "charisma": 0.2 }
		"dynastic": return { "tradition": 0.5, "law": 0.3, "belief": 0.2 }
		_:          return { "tradition": 0.2, "performance": 0.2, "belief": 0.2, "law": 0.2, "charisma": 0.1, "fear": 0.1 }

# ── Memory ────────────────────────────────────────────────────────────────────

func _record_memory(topic: String, data: Dictionary, salience: float = 0.5) -> void:
	memory_log.append({
		"topic":     topic,
		"data":      data,
		"salience":  clampf(salience, 0.0, 1.0),
		"distortion": 0.0,  # grows over time on Python side
	})
	## Cap memory log size — older memories drop out
	if memory_log.size() > 64:
		memory_log.pop_front()

# ── Phase ─────────────────────────────────────────────────────────────────────

func _update_phase() -> void:
	var leg := effective_legitimacy()
	if organization > 0.3 and leg > 0.3:
		phase = Phase.STABLE
	elif organization > 0.15 and leg > 0.15:
		phase = Phase.STRESSED
	elif organization > 0.0 or leg > 0.0:
		phase = Phase.FRACTURING
	else:
		phase = Phase.COLLAPSED

func can_act() -> bool:
	return phase != Phase.COLLAPSED

func fragmentation_risk() -> float:
	## Returns probability [0-1] of fragmenting this turn.
	if phase == Phase.FRACTURING:
		return clampf(1.0 - (organization + effective_legitimacy()) * 0.5, 0.0, 1.0)
	return 0.0
