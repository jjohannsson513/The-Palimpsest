## Army.gd
## ─────────────────────────────────────────────────────────────────────────────
## Army is a mobile military Institution.
## It manages a collection of unit groups, a command capacity, and a stance.
## Organization is the core military stat — not raw strength.
##
## Army composition: units are added individually and can be grouped.
## Command capacity exceeded → organization penalty.
## ─────────────────────────────────────────────────────────────────────────────

class_name Army
extends Institution

# ── Stances (GDD §6) ──────────────────────────────────────────────────────────

enum Stance {
	AGGRESSIVE = 0,   # Seek and engage all enemies
	CAUTIOUS   = 1,   # Engage but maintain max ranged distance
	DEFENSIVE  = 2,   # Hold position; react to nearby enemies
	RETREATING = 3,   # Avoid combat; flee
	GARRISON   = 4,   # Hold a specific tile; defensive bonuses
	PATROL     = 5,   # Waypoint patrol; engage within radius
}

const STANCE_NAMES := {
	Stance.AGGRESSIVE: "Aggressive",
	Stance.CAUTIOUS:   "Cautious",
	Stance.DEFENSIVE:  "Defensive",
	Stance.RETREATING: "Retreating",
	Stance.GARRISON:   "Garrison",
	Stance.PATROL:     "Patrol",
}

# ── Properties ────────────────────────────────────────────────────────────────

@export var stance:           Stance = Stance.DEFENSIVE
@export var position:         int = -1      # cell_id on the sphere
@export var waypoints:        Array[int] = []  # cell_id path for patrol/move
@export var command_capacity: int = 6          # Max units before disorg penalty
@export var commander_id:     String = ""      # Key person leading this army
@export var supply_range:     int = 5          # Tiles from friendly city
@export var in_supply:        bool = true

## Unit groups: Array of { group_id, unit_ids[], stance, type_filter }
@export var groups: Array = []

## Individual units: Array of {
##   unit_id, type, health, moves_left, experience, traits[]
## }
@export var units: Array = []

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _init() -> void:
	type_tags = ["military", "mobile"]

func setup_army(p_id: String, p_civ_id: int, p_pos: Vector2i) -> void:
	setup(p_id, ["military", "mobile"], Institution.Scale.REGIONAL)
	civ_id   = p_civ_id
	position = p_pos
	territory = [p_pos]
	organization = 1.0
	legitimacy_sources["tradition"]   = 0.3
	legitimacy_sources["performance"] = 0.5
	legitimacy_sources["charisma"]    = 0.4

# ── Unit Management ───────────────────────────────────────────────────────────

func add_unit(unit: Dictionary) -> void:
	units.append(unit)
	_check_capacity_penalty()

func remove_unit(unit_id: String) -> bool:
	for i in range(units.size()):
		if units[i]["unit_id"] == unit_id:
			units.remove_at(i)
			return true
	return false

func unit_count() -> int:
	return units.size()

func _check_capacity_penalty() -> void:
	var over := unit_count() - command_capacity
	if over > 0:
		## Gradual disorganization for each unit over cap
		var penalty := float(over) * 0.03
		apply_org_shock(penalty, "over_capacity")

# ── Movement ──────────────────────────────────────────────────────────────────

func move_to(target: int) -> void:
	position = target
	territory = [target]

func set_waypoints(path: Array) -> void:
	waypoints = path

func moves_per_turn() -> int:
	## Base moves reduced by poor organization and terrain (called per-unit)
	var base := 2
	if organization < 0.5:
		base = 1
	return base

# ── Combat ────────────────────────────────────────────────────────────────────

## Apply defeat consequences — large org shock, legitimacy hit.
func suffer_defeat(severity: float) -> void:
	apply_org_shock(severity * 0.4, "battlefield_defeat")
	boost_legitimacy("performance", -severity * 0.3)
	boost_legitimacy("charisma",    -severity * 0.15)
	_record_memory("defeat", { "severity": severity }, severity)
	## Retreating stance activates automatically on heavy defeat
	if severity > 0.5:
		stance = Stance.RETREATING

## Apply victory bonuses.
func register_victory(significance: float) -> void:
	recover_organization(significance * 0.1)
	boost_legitimacy("performance", significance * 0.2)
	## Commander gains charisma if attached
	if not commander_id.is_empty():
		boost_legitimacy("charisma", significance * 0.1)
	_record_memory("victory", { "significance": significance }, significance)

# ── Supply ────────────────────────────────────────────────────────────────────

func check_supply(friendly_city_tiles: Array) -> void:
	## friendly_city_tiles: Array of axial Vector2i of friendly city anchors
	in_supply = false
	for city_tile in friendly_city_tiles:
		var dist := _axial_distance(position, city_tile)
		if dist <= supply_range:
			in_supply = true
			break

func apply_attrition() -> void:
	if not in_supply:
		apply_org_shock(0.03, "supply_attrition")

func _axial_distance(a: Vector2i, b: Vector2i) -> int:
	return (abs(a.x - b.x) + abs(a.x + a.y - b.x - b.y) + abs(a.y - b.y)) / 2

# ── Serialization ─────────────────────────────────────────────────────────────

func _to_dict() -> Dictionary:
	var base := super._to_dict()
	base.merge({
		"stance":           stance,
		"stance_name":      STANCE_NAMES[stance],
		"cell_id":          position,
		"unit_count":       unit_count(),
		"command_capacity": command_capacity,
		"commander_id":     commander_id,
		"in_supply":        in_supply,
		"units":            units,
	})
	return base
