## TurnManager.gd
## ─────────────────────────────────────────────────────────────────────────────
## Controls the Planning ↔ Execution phase state machine.
##
## Planning Phase  — turn-based, no time pressure.
##   All orders are queued. Python AI resolves its decisions.
##   Phase ends when the player confirms (End Turn) and all AI
##   planning_done commands have been received.
##
## Execution Phase — real-time.
##   Orders execute; units move; combat resolves; events fire.
##   Phase ends when the execution timer expires.
##   Timer duration is configurable (Short / Medium / Long / Unlimited).
## ─────────────────────────────────────────────────────────────────────────────

extends Node

# ── Signals ───────────────────────────────────────────────────────────────────

signal planning_phase_started(tick: int)
signal execution_phase_started(tick: int)
signal execution_phase_ended(tick: int)
signal turn_completed(tick: int)
signal execution_timer_updated(seconds_remaining: float)

# ── Phase enum ────────────────────────────────────────────────────────────────

enum Phase { PLANNING, EXECUTION, RESOLVING }

enum ExecutionSpeed {
	SHORT     = 0,   # 45 seconds
	MEDIUM    = 1,   # 180 seconds  (default)
	LONG      = 2,   # 480 seconds
	UNLIMITED = 3,   # No timer — manual advance
}

# ── Config ────────────────────────────────────────────────────────────────────

const EXECUTION_DURATIONS := {
	ExecutionSpeed.SHORT:     45.0,
	ExecutionSpeed.MEDIUM:    180.0,
	ExecutionSpeed.LONG:      480.0,
	ExecutionSpeed.UNLIMITED: INF,
}

const AI_PLANNING_TIMEOUT := 5.0   # seconds to wait for Python ai.planning_done

# ── State ─────────────────────────────────────────────────────────────────────

var current_phase:   Phase = Phase.PLANNING
var execution_speed: ExecutionSpeed = ExecutionSpeed.MEDIUM
var tick:            int = 0
var player_ready:    bool = false
var ai_ready:        bool = false

var _execution_timer: float = 0.0
var _ai_timeout_timer: float = 0.0
var _execution_duration: float = 0.0

# ── Autoload reference ────────────────────────────────────────────────────────
## Set by GameWorld after scene is ready.
var bridge: Node = null

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_enter_planning_phase()

func _process(delta: float) -> void:
	match current_phase:
		Phase.PLANNING:
			_tick_ai_timeout(delta)
		Phase.EXECUTION:
			_tick_execution_timer(delta)
		Phase.RESOLVING:
			pass

# ── Public API ────────────────────────────────────────────────────────────────

## Called by UI "End Turn" button — player has confirmed their orders.
func player_end_turn() -> void:
	if current_phase != Phase.PLANNING:
		return
	player_ready = true
	_try_start_execution()

## Called by bridge when Python sends ai.planning_done.
func ai_planning_done() -> void:
	ai_ready = true
	_try_start_execution()

## Called by UI "Advance" button in Unlimited mode, or externally.
func advance_execution() -> void:
	if current_phase == Phase.EXECUTION and execution_speed == ExecutionSpeed.UNLIMITED:
		_end_execution_phase()

func set_execution_speed(speed: ExecutionSpeed) -> void:
	execution_speed = speed
	_execution_duration = EXECUTION_DURATIONS[speed]

func phase_name() -> String:
	match current_phase:
		Phase.PLANNING:   return "PLANNING"
		Phase.EXECUTION:  return "EXECUTION"
		Phase.RESOLVING:  return "RESOLVING"
		_: return "UNKNOWN"

func seconds_remaining() -> float:
	return maxf(_execution_timer, 0.0)

# ── Phase Transitions ─────────────────────────────────────────────────────────

func _enter_planning_phase() -> void:
	current_phase = Phase.PLANNING
	player_ready  = false
	ai_ready      = false
	_ai_timeout_timer = 0.0
	planning_phase_started.emit(tick)
	## Signal Python to begin AI planning
	if bridge:
		bridge.send_event("phase.planning_start", _build_phase_payload())

func _try_start_execution() -> void:
	if player_ready and ai_ready:
		_enter_execution_phase()

func _enter_execution_phase() -> void:
	current_phase      = Phase.EXECUTION
	_execution_timer   = EXECUTION_DURATIONS[execution_speed]
	_execution_duration = _execution_timer
	execution_phase_started.emit(tick)
	if bridge:
		bridge.send_event("phase.execution_start", { "tick": tick })

func _end_execution_phase() -> void:
	current_phase = Phase.RESOLVING
	execution_phase_ended.emit(tick)
	_resolve_turn()

func _resolve_turn() -> void:
	tick += 1
	if bridge:
		bridge.send_event("phase.turn_end", { "tick": tick })
	turn_completed.emit(tick)
	_enter_planning_phase()

# ── Timers ────────────────────────────────────────────────────────────────────

func _tick_execution_timer(delta: float) -> void:
	if execution_speed == ExecutionSpeed.UNLIMITED:
		return
	_execution_timer -= delta
	execution_timer_updated.emit(_execution_timer)
	if _execution_timer <= 0.0:
		_end_execution_phase()

func _tick_ai_timeout(delta: float) -> void:
	## If player is waiting and AI hasn't responded, force-ready after timeout.
	if player_ready and not ai_ready:
		_ai_timeout_timer += delta
		if _ai_timeout_timer >= AI_PLANNING_TIMEOUT:
			push_warning("TurnManager: AI planning timeout — forcing ai_ready")
			ai_ready = true
			_try_start_execution()

# ── Payload Builder ───────────────────────────────────────────────────────────

func _build_phase_payload() -> Dictionary:
	## Populated by GameWorld before sending — injected via bridge callback.
	## Here we return the base; GameWorld enriches it.
	return { "tick": tick, "phase": "planning" }
