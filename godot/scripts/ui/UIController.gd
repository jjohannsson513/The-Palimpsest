## UIController.gd
## ─────────────────────────────────────────────────────────────────────────────
## Manages the HUD overlay: phase label, turn counter, execution timer bar,
## End Turn button, cell inspector panel, and analytics overlay.
##
## Subscribes to signals from TurnManager, GameWorld, and WorldSphere.
## Never touches game state directly — display only.
##
## Expected scene structure under UIController (CanvasLayer):
##   HUD (Control)
##     PhaseLabel (Label)
##     TurnLabel (Label)
##     TimerBar (ProgressBar)
##     EndTurnButton (Button)
##     SpeedSelector (OptionButton)
##   CellInspector (PanelContainer)
##     InspectorLabel (Label)
##   AnalyticsOverlay (PanelContainer)
##     AnalyticsLabel (Label)
## ─────────────────────────────────────────────────────────────────────────────

extends CanvasLayer

# ── Node references ───────────────────────────────────────────────────────────

@onready var phase_label:        Label          = $HUD/PhaseLabel
@onready var turn_label:         Label          = $HUD/TurnLabel
@onready var timer_bar:          ProgressBar    = $HUD/TimerBar
@onready var end_turn_btn:       Button         = $HUD/EndTurnButton
@onready var speed_selector:     OptionButton   = $HUD/SpeedSelector
@onready var cell_inspector:     PanelContainer = $CellInspector
@onready var inspector_label:    Label          = $CellInspector/InspectorLabel
@onready var analytics_overlay:  PanelContainer = $AnalyticsOverlay
@onready var analytics_label:    Label          = $AnalyticsOverlay/AnalyticsLabel

# ── External refs (set by GameWorld after _ready) ─────────────────────────────

var turn_manager: Node = null
var game_world:   Node = null
var world_sphere: Node = null

# ── Phase colour scheme ───────────────────────────────────────────────────────

const PHASE_COLORS := {
    "PLANNING":  Color(0.25, 0.55, 0.85),   # blue
    "EXECUTION": Color(0.85, 0.40, 0.20),   # orange
    "RESOLVING": Color(0.60, 0.60, 0.60),   # grey
}

# ── Observation mode ──────────────────────────────────────────────────────────

var _observe_mode: bool = false

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
    _setup_speed_selector()
    cell_inspector.hide()
    analytics_overlay.hide()
    _refresh_phase_label("PLANNING", 0)

func connect_to_systems(tm: Node, gw: Node, ws: Node) -> void:
    turn_manager = tm
    game_world   = gw
    world_sphere = ws

    tm.planning_phase_started.connect(_on_planning_started)
    tm.execution_phase_started.connect(_on_execution_started)
    tm.execution_phase_ended.connect(_on_execution_ended)
    tm.turn_completed.connect(_on_turn_completed)
    tm.execution_timer_updated.connect(_on_timer_updated)

    gw.analytics_report.connect(_on_analytics_report)
    ws.cell_clicked.connect(_on_cell_clicked)

func _input(event: InputEvent) -> void:
    if event.is_action_pressed("toggle_observe"):
        _toggle_observe_mode()

# ── Phase handlers ────────────────────────────────────────────────────────────

func _on_planning_started(tick: int) -> void:
    _refresh_phase_label("PLANNING", tick)
    end_turn_btn.disabled  = _observe_mode
    end_turn_btn.text      = "End Turn"
    timer_bar.value        = 0.0
    analytics_overlay.hide()

func _on_execution_started(tick: int) -> void:
    _refresh_phase_label("EXECUTION", tick)
    end_turn_btn.disabled  = true

func _on_execution_ended(_tick: int) -> void:
    _refresh_phase_label("RESOLVING", _tick)

func _on_turn_completed(tick: int) -> void:
    turn_label.text = "Turn  %d" % tick

func _on_timer_updated(seconds_remaining: float) -> void:
    if turn_manager == null:
        return
    var total := turn_manager.EXECUTION_DURATIONS.get(turn_manager.execution_speed, 180.0)
    if total > 0 and total < INF:
        timer_bar.value = (seconds_remaining / total) * 100.0

# ── Cell inspector ────────────────────────────────────────────────────────────

const TERRAIN_NAMES := [
    "Deep Ocean","Ocean","Coastal","Polar Ice","Tundra","Taiga",
    "Temperate","Grassland","Savanna","Mediterranean","Monsoon","Tropical",
    "Desert","Arid Desert","Xeric","Dry Steppe","Montane","Impassable Mtns","Wastelands",
]

func _on_cell_clicked(cell_id: int, data: Dictionary) -> void:
    if data.is_empty():
        cell_inspector.hide()
        return

    var terrain  := data.get("terrain", -1)
    var height   := data.get("height",  0.0)
    var t_name   := TERRAIN_NAMES[clamp(terrain, 0, TERRAIN_NAMES.size() - 1)] if terrain >= 0 else "Unknown"
    var nat_res  := data.get("resource_natural",   "(none)")
    var strat_res := data.get("resource_strategic", "(none)")
    var lux_res  := data.get("resource_luxury",    "(none)")
    var owner    := data.get("owner_institution_id", "(unclaimed)")
    var temp     := "%.2f" % data.get("temperature", 0.0)
    var moist    := "%.2f" % data.get("moisture", 0.0)

    inspector_label.text = (
        "Cell #%d\n" % cell_id
        + "Terrain:   %s\n" % t_name
        + "Height:    %+.3f\n" % height
        + "Temp/Moist: %s / %s\n" % [temp, moist]
        + "Natural:   %s\n" % (nat_res if nat_res else "(none)")
        + "Strategic: %s\n" % (strat_res if strat_res else "(none)")
        + "Luxury:    %s\n" % (lux_res if lux_res else "(none)")
        + "Owner:     %s" % owner
    )
    cell_inspector.show()

# ── Analytics overlay ─────────────────────────────────────────────────────────

func _on_analytics_report(metric: String, value: Variant) -> void:
    var text := analytics_label.text
    var line  := "\n%s:  %s" % [metric.replace("_", " ").capitalize(), str(value)]
    ## Keep only last 6 reports
    var lines := (text + line).split("\n")
    if lines.size() > 7:
        lines = lines.slice(lines.size() - 7)
    analytics_label.text = "\n".join(lines)
    analytics_overlay.show()

# ── End Turn button ───────────────────────────────────────────────────────────

func _on_end_turn_pressed() -> void:
    if turn_manager and not _observe_mode:
        turn_manager.player_end_turn()

# ── Speed selector ────────────────────────────────────────────────────────────

func _setup_speed_selector() -> void:
    speed_selector.clear()
    speed_selector.add_item("Short  (45s)",   0)
    speed_selector.add_item("Medium (3min)",  1)
    speed_selector.add_item("Long   (8min)",  2)
    speed_selector.add_item("Unlimited",      3)
    speed_selector.selected = 1   # Medium default

func _on_speed_changed(index: int) -> void:
    if turn_manager:
        turn_manager.set_execution_speed(index)

# ── Observe mode ──────────────────────────────────────────────────────────────

func _toggle_observe_mode() -> void:
    _observe_mode = not _observe_mode
    if _observe_mode:
        phase_label.modulate = Color(0.7, 0.5, 0.9)
        end_turn_btn.text    = "Observing"
        end_turn_btn.disabled = true
        ## Auto-advance turn in observe mode
        if turn_manager and turn_manager.current_phase == turn_manager.Phase.PLANNING:
            turn_manager.player_end_turn()
    else:
        phase_label.modulate = Color.WHITE
        end_turn_btn.disabled = false
        end_turn_btn.text    = "End Turn"

# ── Helpers ───────────────────────────────────────────────────────────────────

func _refresh_phase_label(phase_name: String, tick: int) -> void:
    phase_label.text     = phase_name
    phase_label.modulate = PHASE_COLORS.get(phase_name, Color.WHITE)
    turn_label.text      = "Turn  %d" % tick
