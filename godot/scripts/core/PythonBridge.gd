## PythonBridge.gd
## ─────────────────────────────────────────────────────────────────────────────
## Thread-safe Unix Domain Socket client.
## Runs I/O on a background thread; dispatches received commands to the
## main thread via call_deferred / signals.
##
## All game systems call:
##   bridge.send_event(topic, payload)   — fire-and-forget
##   bridge.send_event(topic, payload)   — for all domains
##
## All incoming commands are emitted as:
##   command_received(domain, topic, payload, msg_id)
## ─────────────────────────────────────────────────────────────────────────────

extends Node

# ── Signals ───────────────────────────────────────────────────────────────────

signal command_received(domain: String, topic: String, payload: Dictionary, msg_id: String)
signal bridge_ready()
signal bridge_disconnected()

# ── Config ────────────────────────────────────────────────────────────────────

const SOCKET_PATH         := "/tmp/palimpsest.sock"
const RECONNECT_DELAY_MS  := 2000
const HANDSHAKE_VERSION   := "0.2"

# ── State ─────────────────────────────────────────────────────────────────────

var _unix_socket: StreamPeerUnix
var _thread:      Thread
var _mutex:       Mutex
var _outbox:      Array[String]
var _running:     bool = false
var _connected:   bool = false
var _current_tick: int = 0
var _current_phase: String = "planning"

# ── Lifecycle ─────────────────────────────────────────────────────────────────

func _ready() -> void:
	_mutex  = Mutex.new()
	_outbox = []
	_thread = Thread.new()
	_running = true
	_thread.start(_socket_loop)

func _exit_tree() -> void:
	_running = false
	_thread.wait_to_finish()
	if _unix_socket:
		_unix_socket.disconnect_from_host()

# ── Public API ────────────────────────────────────────────────────────────────

## Primary send method — used by all game systems.
func send_event(topic: String, payload: Dictionary = {}) -> void:
	_enqueue(_build_envelope("event", topic, payload))

func is_bridge_connected() -> bool:
	return _connected

## Update internal tick/phase so envelopes carry correct metadata.
func set_context(tick: int, phase: String) -> void:
	_current_tick  = tick
	_current_phase = phase

# ── Internal — Envelope ───────────────────────────────────────────────────────

func _build_envelope(type: String, topic: String, payload: Dictionary) -> String:
	var domain := topic.split(".")[0] if "." in topic else "system"
	var msg := {
		"id":      _uuid(),
		"type":    type,
		"domain":  domain,
		"topic":   topic,
		"payload": payload,
		"phase":   _current_phase,
		"tick":    _current_tick,
	}
	return JSON.stringify(msg) + "\n"

func _enqueue(line: String) -> void:
	_mutex.lock()
	_outbox.append(line)
	_mutex.unlock()

# ── Internal — Socket Loop (background thread) ────────────────────────────────

func _socket_loop() -> void:
	while _running:
		if not _connected:
			_try_connect()
			if not _connected:
				OS.delay_msec(RECONNECT_DELAY_MS)
				continue

		## Flush outbox
		_mutex.lock()
		var pending := _outbox.duplicate()
		_outbox.clear()
		_mutex.unlock()

		for line: String in pending:
			var err := _unix_socket.put_data(line.to_utf8_buffer())
			if err != OK:
				push_warning("PythonBridge: send error %d" % err)
				_connected = false
				break

		## Read incoming
		var available := _unix_socket.get_available_bytes()
		if available > 0:
			var result := _unix_socket.get_partial_data(available)
			if result[0] == OK:
				_process_incoming(result[1].get_string_from_utf8())
			else:
				_connected = false

		OS.delay_msec(16)

	_connected = false

func _try_connect() -> void:
	_unix_socket = StreamPeerUnix.new()
	if _unix_socket.connect_to_path(SOCKET_PATH) != OK:
		return
	_connected = true
	## Send handshake
	_enqueue(_build_envelope("event", "system.handshake", {
		"version":      HANDSHAKE_VERSION,
		"capabilities": ["ai", "analytics", "procgen", "beliefs"],
	}))

func _process_incoming(raw: String) -> void:
	for line in raw.split("\n", false):
		line = line.strip_edges()
		if line.is_empty():
			continue
		var parsed = JSON.parse_string(line)
		if parsed == null:
			push_warning("PythonBridge: malformed JSON: " + line.left(80))
			continue
		_dispatch(parsed)

func _dispatch(msg: Dictionary) -> void:
	var topic:  String = msg.get("topic", "")
	var domain: String = msg.get("domain", "system")
	var payload         = msg.get("payload", {})
	var msg_id: String = msg.get("id", "")

	if topic == "system.ready":
		call_deferred("emit_signal", "bridge_ready")
		return

	var type: String = msg.get("type", "")
	if type in ["command", "response"]:
		call_deferred("emit_signal", "command_received", domain, topic, payload, msg_id)

# ── Utility ───────────────────────────────────────────────────────────────────

func _uuid() -> String:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	return "%08x-%04x-4%03x-%04x-%012x" % [
		rng.randi(),
		rng.randi() & 0xFFFF,
		rng.randi() & 0x0FFF,
		(rng.randi() & 0x3FFF) | 0x8000,
		rng.randi() & 0xFFFFFFFFFFFF,
	]
