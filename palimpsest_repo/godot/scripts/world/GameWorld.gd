## GameWorld.gd  (v0.3 — spherical Voronoi, cell_id positions)
extends Node3D

@onready var bridge:       Node        = $PythonBridge
@onready var turn_mgr:     Node        = $TurnManager
@onready var world_sphere: Node        = $WorldSphere
@onready var camera_orbit: Node3D      = $CameraOrbit

signal institution_registered(institution)
signal city_founded(city)
signal army_moved(army)
signal analytics_report(metric, value)

var _cells:       Dictionary = {}
var _adjacency:   Dictionary = {}
var _sphere_radius: float    = 10.0
var _institutions: Dictionary = {}
var _cities:       Dictionary = {}
var _armies:       Dictionary = {}
var _dynasties:    Dictionary = {}
var _beliefs:      Dictionary = {}
var _civs:         Dictionary = {}
var _human_civ_id: int = 0

func _ready() -> void:
	bridge.bridge_ready.connect(_on_bridge_ready)
	bridge.command_received.connect(_on_command_received)
	bridge.bridge_disconnected.connect(func(): turn_mgr.ai_planning_done())
	turn_mgr.bridge = bridge
	turn_mgr.planning_phase_started.connect(_on_planning_started)
	turn_mgr.turn_completed.connect(_on_turn_completed)
	world_sphere.cell_clicked.connect(_on_cell_clicked)

func _process(delta):
	if turn_mgr.current_phase == turn_mgr.Phase.EXECUTION:
		pass  # real-time execution stub

func get_cell(cid: int) -> Dictionary: return _cells.get(cid, {})
func cell_neighbors(cid: int) -> Array: return _adjacency.get(cid, [])

func cell_distance(a: int, b: int) -> int:
	if a == b: return 0
	var visited := { a: true }; var queue := [[a, 0]]
	while queue:
		var cur := queue.pop_front()
		var cid: int = cur[0]; var dist: int = cur[1]
		for n in _adjacency.get(cid, []):
			if n == b: return dist + 1
			if not visited.has(n): visited[n] = true; queue.append([n, dist + 1])
	return 9999

func is_land(cid: int) -> bool: return not _cells.get(cid, {}).get("is_oceanic", true)

func register(inst) -> void:
	_institutions[inst.id] = inst
	if inst.get_class() == "City" or "civic" in inst.type_tags: _cities[inst.id] = inst
	elif inst.get_class() == "Army" or "military" in inst.type_tags: _armies[inst.id] = inst
	elif "dynastic" in inst.type_tags: _dynasties[inst.id] = inst
	institution_registered.emit(inst)
	bridge.send_event("institution.created", inst._to_dict())

func unregister(id: String) -> void:
	if not _institutions.has(id): return
	_institutions.erase(id); _cities.erase(id); _armies.erase(id); _dynasties.erase(id)

func found_city(civ_id: int, cell_id: int, name: String):
	var city_id := "city_%d_%d" % [civ_id, _cities.size()]
	var city    := City.new()
	city.setup_city(city_id, civ_id, cell_id)
	city.label = name; city.founded_tick = turn_mgr.tick
	register(city); city_founded.emit(city)
	return city

func create_army(civ_id: int, cell_id: int, lbl: String = ""):
	var aid  := "army_%d_%d" % [civ_id, _armies.size()]
	var army := Army.new()
	army.setup_army(aid, civ_id, cell_id)
	army.label = lbl if lbl else "Army"; army.founded_tick = turn_mgr.tick
	register(army); return army

func move_army(army_id: String, target: int) -> bool:
	var army = _armies.get(army_id)
	if not army or not army.can_act(): return false
	if cell_distance(army.position, target) > army.moves_per_turn(): return false
	army.position = target
	bridge.send_event("institution.changed", {"id": army_id, "delta": {"cell_id": target}})
	army_moved.emit(army); return true

func _on_bridge_ready() -> void:
	bridge.send_event("system.handshake", {"version": "0.3", "capabilities": ["ai","analytics","procgen","beliefs"]})

func _on_command_received(domain, topic, payload, _id) -> void:
	match topic:
		"procgen.apply_map":        _apply_world(payload)
		"procgen.apply_institutions": _apply_starting_institutions(payload)
		"ai.planning_done":         turn_mgr.ai_planning_done()
		"ai.institution_order":     _apply_institution_order(payload)
		"analytics.report":         analytics_report.emit(payload.get("metric",""), payload.get("value"))

func _apply_world(payload: Dictionary) -> void:
	_sphere_radius = payload.get("sphere_radius", 10.0)
	_cells.clear(); _adjacency.clear()
	for cell in payload.get("cells", []):
		var cid: int = cell["id"]
		_cells[cid] = cell; _adjacency[cid] = cell.get("neighbors", [])
	world_sphere.apply_world_data(payload)
	camera_orbit.frame_sphere(_sphere_radius)

func _apply_starting_institutions(payload: Dictionary) -> void:
	for cd in payload.get("civs", []):
		var cid: int = cd["id"]; _civs[cid] = cd
		var dynasty := Dynasty.new()
		dynasty.setup_dynasty("dynasty_%d" % cid, cid, cd.get("ruler", {"id":"r%d"%cid,"name":"Founder"}))
		dynasty.label = cd.get("dynasty_name", "House Unknown"); register(dynasty)
		var bs := BeliefSystem.new(); bs.setup_beliefs(cid, cd.get("pantheon", {})); _beliefs[cid] = bs
		var sc: int = cd.get("start_cell_id", 0)
		var army := create_army(cid, sc, "Settlers of " + cd.get("name",""))
		army.units.append({"unit_id":"settler_%d"%cid,"type":"settler","health":1.0,"moves_left":2,"experience":0,"traits":[]})
		army.units.append({"unit_id":"warrior_%d"%cid,"type":"warrior","health":1.0,"moves_left":2,"experience":0,"traits":[]})

func _on_planning_started(tick: int) -> void:
	bridge.set_context(tick, "planning")
	bridge.send_event("phase.planning_start", _build_world_state(tick))

func _on_turn_completed(tick: int) -> void:
	for id in _institutions: _institutions[id].recover_organization(0.02); _institutions[id].decay_legitimacy(0.003)
	for id in _dynasties: _dynasties[id].update_faction_pressure(tick)
	bridge.send_event("phase.turn_end", {"tick": tick})

func _apply_institution_order(payload: Dictionary) -> void:
	var iid: String = payload.get("institution_id","")
	match payload.get("order_type",""):
		"move":        move_army(iid, payload.get("cell_id",-1))
		"found_city":
			var army = _armies.get(iid)
			if army: found_city(army.civ_id, army.position, payload.get("name","Settlement")); unregister(iid)
		"set_stance":
			var army = _armies.get(iid)
			if army: army.stance = payload.get("stance", 2)  # DEFENSIVE

func _on_cell_clicked(cid: int, data: Dictionary) -> void:
	bridge.send_event("map.tile_selected", {"cell_id":cid,"terrain":data.get("terrain",-1),"height":data.get("height",0.0)})

func _build_world_state(tick: int) -> Dictionary:
	return {
		"tick": tick, "civs": _civs, "human_civ": _human_civ_id,
		"cities": _cities.values().map(func(c): return c._to_dict()),
		"armies": _armies.values().map(func(a): return a._to_dict()),
		"dynasties": _dynasties.values().map(func(d): return d._to_dict()),
	}
