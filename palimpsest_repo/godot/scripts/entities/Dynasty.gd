## Dynasty.gd
## ─────────────────────────────────────────────────────────────────────────────
## Dynasty is a genealogical legitimacy Institution.
## Its primary output is legitimacy continuity across generations.
##
## Contains: ruler, courtiers, succession rules, faction tracking.
## "A dynasty is a compression algorithm for history." — GDD §7
## ─────────────────────────────────────────────────────────────────────────────

class_name Dynasty
extends Institution

# ── Faction Enum ──────────────────────────────────────────────────────────────

enum Faction {
	LOYALISTS    = 0,   # Stability and dynasty continuity
	DISSIDENTS   = 1,   # Reform or replacement of leadership
	PRAGMATISTS  = 2,   # Efficiency above ideology
	GLORY_HOUNDS = 3,   # Military expansion and prestige
	REBELS       = 4,   # Secession; spawn when legitimacy collapses
}

const FACTION_NAMES := {
	Faction.LOYALISTS:    "Loyalists",
	Faction.DISSIDENTS:   "Dissidents",
	Faction.PRAGMATISTS:  "Pragmatists",
	Faction.GLORY_HOUNDS: "Glory Hounds",
	Faction.REBELS:       "Rebels",
}

## Faction pressure [0.0 – 1.0]: how loudly this faction is pushing
var faction_pressure: Dictionary = {
	Faction.LOYALISTS:    0.4,
	Faction.DISSIDENTS:   0.1,
	Faction.PRAGMATISTS:  0.2,
	Faction.GLORY_HOUNDS: 0.2,
	Faction.REBELS:       0.0,
}

# ── Person Schema ─────────────────────────────────────────────────────────────
## A person is the interface through which dynasties act.
## Schema: {
##   id, name, role, age, traits[], belief_affinity,
##   reputation: { honor, cruelty, piety, competence },
##   faction_alignment, parent_ids[], child_ids[],
##   institution_ties: { army_id?, city_id?, research_id? }
## }

# ── Properties ────────────────────────────────────────────────────────────────

@export var ruling_civ_id:   int = -1
@export var founding_myth:   String = ""
@export var succession_rule: String = "primogeniture"  # primogeniture | elective | merit

## The current ruler person dict
@export var ruler: Dictionary = {}

## All courtiers: id → person dict
@export var courtiers: Dictionary = {}

## Lineage graph: person_id → { parent_ids[], child_ids[] }
@export var lineage: Dictionary = {}

## Cadet branches: dynasty_id → founding_tick
@export var cadet_branches: Dictionary = {}

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _init() -> void:
	type_tags = ["dynastic", "legitimacy_network"]

func setup_dynasty(p_id: String, p_civ_id: int, founder: Dictionary) -> void:
	setup(p_id, ["dynastic", "legitimacy_network"], Institution.Scale.CIVILIZATIONAL)
	ruling_civ_id = p_civ_id
	ruler         = founder
	courtiers[founder["id"]] = founder
	legitimacy_sources["tradition"] = 0.6
	legitimacy_sources["charisma"]  = founder.get("reputation", {}).get("charisma", 0.5)

# ── Person Management ─────────────────────────────────────────────────────────

func add_courtier(person: Dictionary) -> void:
	courtiers[person["id"]] = person
	key_person_ids.append(person["id"])

func remove_courtier(person_id: String) -> Dictionary:
	var p := courtiers.get(person_id, {})
	courtiers.erase(person_id)
	key_person_ids.erase(person_id)
	return p

func get_courtier(person_id: String) -> Dictionary:
	return courtiers.get(person_id, {})

func courtiers_in_role(role: String) -> Array:
	return courtiers.values().filter(func(p): return p.get("role") == role)

func assign_role(person_id: String, role: String) -> void:
	if courtiers.has(person_id):
		courtiers[person_id]["role"] = role

# ── Succession ────────────────────────────────────────────────────────────────

func get_heir() -> Dictionary:
	## Returns the best succession candidate based on succession_rule.
	var candidates := successor_candidates.filter(func(pid): return courtiers.has(pid))
	if candidates.is_empty():
		return {}
	match succession_rule:
		"primogeniture":
			## Oldest child first
			var children := candidates.filter(func(pid):
				var parent_ids := lineage.get(pid, {}).get("parent_ids", [])
				return ruler.get("id", "") in parent_ids
			)
			return courtiers.get(children[0], {}) if not children.is_empty() else {}
		"merit":
			## Highest competence
			candidates.sort_custom(func(a, b):
				var ca := courtiers.get(a, {}).get("reputation", {}).get("competence", 0.0)
				var cb := courtiers.get(b, {}).get("reputation", {}).get("competence", 0.0)
				return ca > cb
			)
			return courtiers.get(candidates[0], {})
		_:
			return courtiers.get(candidates[0], {})

func succeed(person_id: String) -> void:
	## Transition ruler to a new person.
	var old_ruler := ruler.duplicate()
	ruler = courtiers.get(person_id, ruler)
	_record_memory("succession", {
		"from": old_ruler.get("name", ""),
		"to":   ruler.get("name", ""),
	}, 0.9)
	## Legitimacy transfer — partial
	var inherited_leg := effective_legitimacy("dynastic") * 0.7
	for key in legitimacy_sources:
		legitimacy_sources[key] *= 0.7
	legitimacy_sources["tradition"] += 0.3   # Dynasties restore tradition on succession

# ── Faction Pressure ──────────────────────────────────────────────────────────

func update_faction_pressure(tick: int) -> void:
	## Pressure evolves based on legitimacy, karma, and recent events
	var leg := effective_legitimacy()
	## Dissidents grow when legitimacy is weak
	faction_pressure[Faction.DISSIDENTS] = clampf(
		faction_pressure[Faction.DISSIDENTS] + (0.3 - leg) * 0.05, 0.0, 1.0
	)
	## Loyalists grow when legitimacy is strong
	faction_pressure[Faction.LOYALISTS] = clampf(
		faction_pressure[Faction.LOYALISTS] + (leg - 0.5) * 0.03, 0.0, 1.0
	)
	## Rebels emerge at very low legitimacy
	if leg < 0.2:
		faction_pressure[Faction.REBELS] = clampf(
			faction_pressure[Faction.REBELS] + 0.05, 0.0, 1.0
		)
	else:
		faction_pressure[Faction.REBELS] = maxf(
			faction_pressure[Faction.REBELS] - 0.02, 0.0
		)

func dominant_faction() -> Faction:
	var best := Faction.LOYALISTS
	var best_val := -1.0
	for f in faction_pressure:
		if faction_pressure[f] > best_val:
			best_val = faction_pressure[f]
			best = f as Faction
	return best

# ── Events — called when significant things happen ────────────────────────────

func on_military_victory(army_id: String, significance: float) -> void:
	boost_legitimacy("performance", significance * 0.15)
	boost_legitimacy("charisma",    significance * 0.1)
	## Glory Hounds satisfied
	faction_pressure[Faction.GLORY_HOUNDS] = maxf(
		faction_pressure[Faction.GLORY_HOUNDS] - significance * 0.2, 0.0
	)
	_record_memory("military_victory", { "army_id": army_id }, significance)

func on_city_founded(city_id: String) -> void:
	boost_legitimacy("performance", 0.05)
	faction_pressure[Faction.GLORY_HOUNDS] = maxf(
		faction_pressure[Faction.GLORY_HOUNDS] - 0.1, 0.0
	)
	_record_memory("city_founded", { "city_id": city_id }, 0.5)

# ── Serialization ─────────────────────────────────────────────────────────────

func _to_dict() -> Dictionary:
	var base := super._to_dict()
	base.merge({
		"ruling_civ_id":    ruling_civ_id,
		"succession_rule":  succession_rule,
		"ruler_name":       ruler.get("name", ""),
		"ruler_id":         ruler.get("id", ""),
		"courtier_count":   courtiers.size(),
		"faction_pressure": faction_pressure,
		"dominant_faction": FACTION_NAMES[dominant_faction()],
	})
	return base
