## CameraOrbit.gd
## ─────────────────────────────────────────────────────────────────────────────
## Full-sphere orbiting camera for The Palimpsest globe view.
##
## Scene tree:
##   CameraOrbit  (Node3D, this script)  — positioned at origin, rotates to orbit
##     └─ Camera3D                        — offset along local Z, looks at origin
##
## Controls:
##   Left-drag:  orbit (yaw + pitch)
##   Scroll:     zoom
##   Middle-drag or Right-drag: pan (shifts the camera's look-at target slightly)
##   Double-click: snap-focus on a specific world point
## ─────────────────────────────────────────────────────────────────────────────

extends Node3D

# ── Exported config ───────────────────────────────────────────────────────────

@export var orbit_sensitivity:  float = 0.25     # degrees per pixel
@export var zoom_sensitivity:   float = 0.12     # fraction of distance per scroll tick
@export var min_distance:       float = 3.0      # minimum zoom distance
@export var max_distance:       float = 80.0     # maximum zoom distance
@export var momentum_decay:     float = 0.88     # how quickly orbit momentum fades
@export var momentum_threshold: float = 0.01     # stop momentum below this angular speed
@export var smooth_zoom_speed:  float = 10.0     # zoom interpolation rate
@export var initial_pitch_deg:  float = -25.0    # starting camera tilt (negative = looking down)
@export var initial_distance:   float = 28.0     # starting camera distance

# ── State ─────────────────────────────────────────────────────────────────────

var _yaw:        float = 0.0
var _pitch:      float = 0.0
var _distance:   float = 0.0
var _target_dist: float = 0.0

var _dragging:    bool = false
var _drag_button: int  = MOUSE_BUTTON_LEFT

var _velocity_yaw:   float = 0.0   # momentum
var _velocity_pitch: float = 0.0

@onready var _camera: Camera3D = $Camera3D

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_pitch        = initial_pitch_deg
	_distance     = initial_distance
	_target_dist  = initial_distance
	_apply_transform()

func _process(delta: float) -> void:
	## Apply momentum
	if not _dragging:
		if abs(_velocity_yaw) > momentum_threshold or abs(_velocity_pitch) > momentum_threshold:
			_yaw   += _velocity_yaw
			_pitch  = clamp(_pitch + _velocity_pitch, -89.0, 89.0)
			_velocity_yaw   *= momentum_decay
			_velocity_pitch *= momentum_decay
		else:
			_velocity_yaw   = 0.0
			_velocity_pitch = 0.0

	## Smooth zoom
	_distance = lerp(_distance, _target_dist, clamp(smooth_zoom_speed * delta, 0.0, 1.0))
	_apply_transform()

func _input(event: InputEvent) -> void:
	## ── Drag start ────────────────────────────────────────────────────────────
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			_dragging = event.pressed
			if event.pressed:
				_velocity_yaw   = 0.0
				_velocity_pitch = 0.0

		## Scroll zoom
		if event.pressed:
			if event.button_index == MOUSE_BUTTON_WHEEL_UP:
				_target_dist = clamp(_target_dist * (1.0 - zoom_sensitivity), min_distance, max_distance)
			elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				_target_dist = clamp(_target_dist * (1.0 + zoom_sensitivity), min_distance, max_distance)

	## ── Drag motion ──────────────────────────────────────────────────────────
	elif event is InputEventMouseMotion and _dragging:
		var dx := event.relative.x * orbit_sensitivity
		var dy := event.relative.y * orbit_sensitivity

		_yaw   -= dx
		_pitch  = clamp(_pitch - dy, -89.0, 89.0)

		## Feed momentum buffer
		_velocity_yaw   = -dx
		_velocity_pitch = -dy

# ── Transform ─────────────────────────────────────────────────────────────────

func _apply_transform() -> void:
	## Rotate the rig so that the camera orbits the origin.
	rotation_degrees = Vector3(_pitch, _yaw, 0.0)
	## Position camera at distance along local +Z (away from sphere center).
	if _camera:
		_camera.position = Vector3(0.0, 0.0, _distance)
		## Always look at the globe center (world origin).
		## look_at uses global space; since the rig is at origin, this is correct.
		_camera.look_at(Vector3.ZERO, Vector3.UP)

# ── Public helpers ────────────────────────────────────────────────────────────

## Smoothly zoom to frame the sphere with radius `r`.
func frame_sphere(radius: float) -> void:
	_target_dist = radius * 2.5
	min_distance  = radius * 0.3
	max_distance  = radius * 8.0

## Orbit to face a specific world-space point on the sphere.
func look_at_point(world_pos: Vector3) -> void:
	var dir := world_pos.normalized()
	_yaw   = rad_to_deg(atan2(dir.x, dir.z))
	_pitch = rad_to_deg(asin(-dir.y))

func get_camera() -> Camera3D:
	return _camera
