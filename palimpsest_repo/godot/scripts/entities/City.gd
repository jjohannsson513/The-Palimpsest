## City.gd
## ─────────────────────────────────────────────────────────────────────────────
## City is a civic Institution — an anchored entity that accumulates yields,
## population, civic identity, and buildings over time.
##
## Settlement → Town → City → Metropolis (GDD §5)
## ─────────────────────────────────────────────────────────────────────────────

class_name City
extends Institution

# ── City Tier ─────────────────────────────────────────────────────────────────

enum Tier { SETTLEMENT = 0, TOWN = 1, CITY = 2, METROPOLIS = 3 }

const TIER_THRESHOLDS := {
	Tier.SETTLEMENT: 0,
	Tier.TOWN:       50,
	Tier.CITY:       200,
	Tier.METROPOLIS: 600,
}

const TIER_BUILDING_SLOTS := {
	Tier.SETTLEMENT: 2,
	Tier.TOWN:       5,
	Tier.CITY:       10,
	Tier.METROPOLIS: 16,
}

const TIER_NAMES := {
	Tier.SETTLEMENT: "Settlement",
	Tier.TOWN:       "Town",
	Tier.CITY:       "City",
	Tier.METROPOLIS: "Metropolis",
}

# ── Civic Identity ────────────────────────────────────────────────────────────
## Not chosen — emerges from what gets built, wars, beliefs, governors.
## Values are float weights [0–1]; sum can exceed 1.0.

enum CivicIdentityFlavor {
	MERCANTILE     = 0,
	MILITARIZED    = 1,
	SACRED         = 2,
	SCHOLARLY      = 3,
	FRONTIER       = 4,
	DECADENT       = 5,
	ADMINISTRATIVE = 6,
}

const IDENTITY_NAMES := {
	CivicIdentityFlavor.MERCANTILE:     "Mercantile",
	CivicIdentityFlavor.MILITARIZED:    "Militarized",
	CivicIdentityFlavor.SACRED:         "Sacred",
	CivicIdentityFlavor.SCHOLARLY:      "Scholarly",
	CivicIdentityFlavor.FRONTIER:       "Frontier",
	CivicIdentityFlavor.DECADENT:       "Decadent",
	CivicIdentityFlavor.ADMINISTRATIVE: "Administrative",
}

# ── Properties ────────────────────────────────────────────────────────────────

@export var tier: Tier = Tier.SETTLEMENT
@export var population: int = 1
@export var development: int = 1      # Investment multiplier
@export var anchor_cell: int = -1    # cell_id on the sphere
@export var border_tiles: Array = []  # Array of { q, r }

## Civic identity vector — float per flavor
@export var civic_identity: Dictionary = {
	CivicIdentityFlavor.MERCANTILE:     0.0,
	CivicIdentityFlavor.MILITARIZED:    0.0,
	CivicIdentityFlavor.SACRED:         0.0,
	CivicIdentityFlavor.SCHOLARLY:      0.0,
	CivicIdentityFlavor.FRONTIER:       0.3,   # All settlements start frontier
	CivicIdentityFlavor.DECADENT:       0.0,
	CivicIdentityFlavor.ADMINISTRATIVE: 0.0,
}

@export var governor_person_id: String = ""
@export var buildings: Array[String] = []
@export var production_queue: Array = []    # { type, subject, progress, cost }
@export var food_surplus: float = 0.0
@export var growth_progress: float = 0.0   # Accumulates toward next population

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _init() -> void:
	type_tags = ["civic", "anchored"]

# ── Public API ────────────────────────────────────────────────────────────────

func setup_city(p_id: String, p_civ_id: int, p_anchor_cell: int) -> void:
	setup(p_id, ["civic", "anchored"], Institution.Scale.REGIONAL)
	civ_id      = p_civ_id
	anchor_cell = p_anchor_cell
	territory   = [p_anchor_cell]
	label       = "New Settlement"
	organization = 1.0
	legitimacy_sources["tradition"]  = 0.2
	legitimacy_sources["performance"] = 0.5

func tier_name() -> String:
	return TIER_NAMES[tier]

func building_slots_total() -> int:
	return TIER_BUILDING_SLOTS[tier]

func building_slots_used() -> int:
	return buildings.size()

func building_slots_free() -> int:
	return building_slots_total() - building_slots_used()

## Pop × Dev score drives tier progression.
func progression_score() -> int:
	return population * development

func try_tier_up() -> bool:
	var next_tier := tier + 1 as Tier
	if next_tier > Tier.METROPOLIS:
		return false
	if progression_score() >= TIER_THRESHOLDS[next_tier]:
		tier = next_tier
		## Tier-up boosts tradition legitimacy
		boost_legitimacy("performance", 0.1)
		_record_memory("tier_up", { "new_tier": TIER_NAMES[tier] }, 0.8)
		return true
	return false

## Called each Planning Phase to accumulate food and grow population.
func process_turn_growth(net_food: float) -> void:
	food_surplus = net_food
	if food_surplus > 0:
		growth_progress += food_surplus * 0.1
		if growth_progress >= float(population) * 10.0:
			population += 1
			growth_progress = 0.0
			_record_memory("population_growth", { "new_pop": population }, 0.3)
	elif food_surplus < 0:
		## Starvation — damage organization and legitimacy
		apply_org_shock(0.05, "starvation")
		boost_legitimacy("performance", -0.05)

## Nudge civic identity based on a building or event.
func shift_identity(flavor: CivicIdentityFlavor, amount: float) -> void:
	civic_identity[flavor] = clampf(civic_identity.get(flavor, 0.0) + amount, 0.0, 1.0)
	## Gradually decay all other flavors to maintain relative weighting
	for f in civic_identity:
		if f != flavor:
			civic_identity[f] = maxf(civic_identity[f] - amount * 0.1, 0.0)

func dominant_identity() -> CivicIdentityFlavor:
	var best := CivicIdentityFlavor.FRONTIER
	var best_val := -1.0
	for f in civic_identity:
		if civic_identity[f] > best_val:
			best_val = civic_identity[f]
			best = f as CivicIdentityFlavor
	return best

## Compute total yields for this city (base terrain + buildings + identity).
func compute_yields(world_map: TileMap) -> Dictionary:
	var yields := { "food": 0.0, "production": 0.0, "culture": 0.0,
	                "conviction": 0.0, "research": 0.0, "trade_value": 0.0, "manpower": 0 }
	## Sum terrain yields across territory tiles
	## (world_map is passed in to avoid circular deps)
	for tile in territory:
		var axial := Vector2i(tile["q"], tile["r"]) if tile is Dictionary else tile
		var ty: Dictionary = world_map.get_tile_yield(axial) if world_map.has_method("get_tile_yield") else {}
		yields["food"]       += ty.get("food", 0)
		yields["production"] += ty.get("production", 0)
		yields["culture"]    += ty.get("culture", 0)
	## Manpower is proportional to population
	yields["manpower"] = population * 10
	## Identity bonuses
	yields["trade_value"] += civic_identity.get(CivicIdentityFlavor.MERCANTILE, 0.0) * 3.0
	yields["research"]    += civic_identity.get(CivicIdentityFlavor.SCHOLARLY, 0.0) * 2.0
	yields["conviction"]  += civic_identity.get(CivicIdentityFlavor.SACRED, 0.0) * 2.0
	yields["production"]  += civic_identity.get(CivicIdentityFlavor.MILITARIZED, 0.0) * 1.0
	return yields

func _to_dict() -> Dictionary:
	var base := super._to_dict()
	base.merge({
		"tier":            tier,
		"population":      population,
		"development":     development,
		"progression":     progression_score(),
		"anchor_cell":     anchor_cell,
		"civic_identity":  civic_identity,
		"governor":        governor_person_id,
		"buildings":       buildings,
		"building_slots":  building_slots_total(),
	})
	return base
