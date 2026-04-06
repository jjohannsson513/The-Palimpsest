## WorldSphere.gd
## ─────────────────────────────────────────────────────────────────────────────
## Renders the Palimpsest world as a procedural sphere mesh built from
## Voronoi cell geometry received from the Python bridge.
##
## Each cell is fan-triangulated from its center, with vertices extruded
## outward along their normal by height * HEIGHT_EXTRUSION for 3D relief.
## Per-vertex colour encodes terrain type.
##
## Cell picking uses ray-sphere intersection followed by nearest-center lookup.
## ─────────────────────────────────────────────────────────────────────────────

class_name WorldSphere
extends Node3D

# ── Signals ───────────────────────────────────────────────────────────────────

signal cell_clicked(cell_id: int, cell_data: Dictionary)
signal cell_hovered(cell_id: int, cell_data: Dictionary)

# ── Terrain colour palette — 19 types, matches procgen/climate.py ─────────────

const TERRAIN_COLORS: Array[Color] = [
	Color(0.06, 0.13, 0.35),   #  0 DEEP_OCEAN
	Color(0.10, 0.22, 0.55),   #  1 OCEAN
	Color(0.18, 0.40, 0.65),   #  2 COASTAL
	Color(0.85, 0.90, 0.95),   #  3 POLAR_ICE
	Color(0.72, 0.78, 0.68),   #  4 TUNDRA
	Color(0.22, 0.38, 0.22),   #  5 TAIGA
	Color(0.40, 0.60, 0.28),   #  6 TEMPERATE
	Color(0.48, 0.72, 0.22),   #  7 GRASSLAND
	Color(0.72, 0.65, 0.28),   #  8 SAVANNA
	Color(0.55, 0.72, 0.28),   #  9 MEDITERRANEAN
	Color(0.22, 0.52, 0.28),   # 10 MONSOON
	Color(0.10, 0.42, 0.16),   # 11 TROPICAL
	Color(0.78, 0.68, 0.35),   # 12 DESERT
	Color(0.85, 0.72, 0.35),   # 13 ARID_DESERT
	Color(0.70, 0.60, 0.30),   # 14 XERIC
	Color(0.62, 0.58, 0.28),   # 15 DRY_STEPPE
	Color(0.52, 0.48, 0.42),   # 16 MONTANE
	Color(0.75, 0.72, 0.70),   # 17 MONTANE_IMPASSABLE
	Color(0.38, 0.32, 0.28),   # 18 WASTELANDS
]

# ── Config ────────────────────────────────────────────────────────────────────

@export var height_extrusion: float = 0.08   # Godot units per height unit
@export var ocean_depth:      float = 0.04   # inward depression for deep ocean

# ── Internal state ────────────────────────────────────────────────────────────

var sphere_radius: float = 10.0
var num_cells:     int   = 0
var sea_level:     float = 0.0

## cell_id → { id, center[3], vertices[], neighbors[], terrain, height, … }
var _cells: Dictionary = {}
## cell_id → center as Vector3, normalised (unit sphere)
var _centers_unit: Array[Vector3] = []

var _mesh_instance: MeshInstance3D
var _collision_shape: StaticBody3D
var _hovered_cell: int = -1

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_mesh_instance = MeshInstance3D.new()
	add_child(_mesh_instance)

func _input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var cell_id := _pick_cell(event.position)
		if cell_id >= 0:
			cell_clicked.emit(cell_id, _cells.get(cell_id, {}))

	elif event is InputEventMouseMotion:
		var cell_id := _pick_cell(event.position)
		if cell_id != _hovered_cell:
			_hovered_cell = cell_id
			if cell_id >= 0:
				cell_hovered.emit(cell_id, _cells.get(cell_id, {}))

# ── Public API ────────────────────────────────────────────────────────────────

func apply_world_data(data: Dictionary) -> void:
	sphere_radius = data.get("sphere_radius", 10.0)
	num_cells     = data.get("num_cells", 0)
	sea_level     = data.get("sea_level", 0.0)

	_cells.clear()
	_centers_unit.clear()

	for cell in data.get("cells", []):
		var cid: int = cell["id"]
		_cells[cid]  = cell
		var c := Vector3(cell["center"][0], cell["center"][1], cell["center"][2])
		_centers_unit.append(c.normalized())

	_build_mesh()

func get_cell(cell_id: int) -> Dictionary:
	return _cells.get(cell_id, {})

func get_cell_world_position(cell_id: int) -> Vector3:
	if cell_id < 0 or cell_id >= _centers_unit.size():
		return Vector3.ZERO
	return _centers_unit[cell_id] * sphere_radius

func set_cell_highlight(cell_id: int, color: Color) -> void:
	## TODO: implement per-cell overlay via MultiMesh or shader
	pass

# ── Mesh builder ──────────────────────────────────────────────────────────────

func _build_mesh() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for cell_id in _cells:
		var cell: Dictionary = _cells[cell_id]
		var verts_raw: Array = cell.get("vertices", [])
		if verts_raw.size() < 3:
			continue

		var terrain: int  = cell.get("terrain", 0)
		var height:  float = cell.get("height", 0.0)
		var color: Color   = TERRAIN_COLORS[clamp(terrain, 0, TERRAIN_COLORS.size() - 1)]

		# Extrusion: positive height = raised, negative = depressed
		# Ocean cells are slightly inset; land cells raised by height
		var extrusion := 0.0
		if height >= sea_level:
			extrusion = (height - sea_level) * height_extrusion
		else:
			extrusion = (height - sea_level) * ocean_depth

		# Cell center — on sphere surface + extrusion
		var center_unit := Vector3(
			cell["center"][0], cell["center"][1], cell["center"][2]
		).normalized()
		var center := center_unit * (sphere_radius + extrusion)

		# Polygon vertices
		var poly: Array[Vector3] = []
		for v in verts_raw:
			var vu := Vector3(v[0], v[1], v[2]).normalized()
			poly.append(vu * (sphere_radius + extrusion))

		# Fan triangulation: center + (poly[i], poly[(i+1)%n])
		for i in range(poly.size()):
			var a := poly[i]
			var b := poly[(i + 1) % poly.size()]
			# Normal for this face (outward from sphere center)
			var normal := (a + b + center).normalized()
			st.set_color(color)
			st.set_normal(normal)
			st.add_vertex(center)
			st.set_normal(a.normalized())
			st.add_vertex(a)
			st.set_normal(b.normalized())
			st.add_vertex(b)

	st.generate_normals()
	var mesh := st.commit()
	_mesh_instance.mesh = mesh

	## Assign a simple vertex-color material
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
	_mesh_instance.material_override = mat

# ── Cell picking ──────────────────────────────────────────────────────────────

func _pick_cell(screen_pos: Vector2) -> int:
	## Ray-sphere intersection, then nearest cell center lookup.
	var camera := get_viewport().get_camera_3d()
	if camera == null:
		return -1

	var origin    := camera.project_ray_origin(screen_pos)
	var direction := camera.project_ray_normal(screen_pos)

	var hit := _ray_sphere_intersect(origin, direction, Vector3.ZERO, sphere_radius)
	if hit == null:
		return -1

	## Find cell whose unit-center has maximum dot with hit direction
	var hit_dir := (hit as Vector3).normalized()
	var best_id  := -1
	var best_dot := -2.0

	for i in range(_centers_unit.size()):
		var d := _centers_unit[i].dot(hit_dir)
		if d > best_dot:
			best_dot = d
			best_id  = i

	return best_id


func _ray_sphere_intersect(
	origin:    Vector3,
	direction: Vector3,
	center:    Vector3,
	radius:    float,
) -> Variant:
	## Returns the nearest intersection point on the sphere, or null if no hit.
	var oc := origin - center
	var a  := direction.dot(direction)
	var b  := 2.0 * oc.dot(direction)
	var c  := oc.dot(oc) - radius * radius
	var disc := b * b - 4.0 * a * c

	if disc < 0.0:
		return null

	var t := (-b - sqrt(disc)) / (2.0 * a)
	if t < 0.0:
		t = (-b + sqrt(disc)) / (2.0 * a)
	if t < 0.0:
		return null

	return origin + direction * t
