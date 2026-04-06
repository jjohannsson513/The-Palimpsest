"""
bridge/server.py
~~~~~~~~~~~~~~~~
Async Unix Domain Socket server.
Godot connects; messages route to domain handlers.
On handshake: runs full sphere+tectonic world generation and sends
the result in two messages (map + institutions).

Large payloads (sphere data can be 3–8 MB) are sent as single NDJSON
lines — UDS has no packet-size limit, only kernel buffer limits which
are typically 64 KB–4 MB. We flush after every write and rely on
asyncio's internal buffering for large writes.

Run:
    python -m palimpsest.python.bridge.server [--cells N] [--civs N] [--seed N]
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

SOCKET_PATH = Path("/tmp/palimpsest.sock")

# ── Config (overridable via CLI args) ─────────────────────────────────────────
_NUM_CELLS = 1000
_NUM_CIVS  = 6
_SEED      = 0   # 0 = random

# domain prefix → handler coroutine
_HANDLERS: dict[str, Callable] = {}


def register_handler(topic_prefix: str, handler: Callable) -> None:
    _HANDLERS[topic_prefix] = handler
    log.debug("Handler registered: %s", topic_prefix)


# ── Session ───────────────────────────────────────────────────────────────────

class GodotSession:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self._tick  = 0
        self._phase = "planning"
        self._buf   = b""

    async def send(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    async def send_ready(self) -> None:
        from palimpsest.python.bridge.protocol import Envelope, Topics
        await self.send(Envelope.command("system", Topics.SYSTEM_READY, {}).to_ndjson())

    async def run(self) -> None:
        log.info("Godot connected")
        async for line in self._readlines():
            await self._handle(line)
        log.info("Godot disconnected")

    async def _readlines(self):
        while True:
            try:
                chunk = await self.reader.read(65536)
            except (ConnectionResetError, asyncio.IncompleteReadError):
                break
            if not chunk:
                break
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if line.strip():
                    yield line.decode(errors="replace")

    async def _handle(self, line: str) -> None:
        try:
            msg: dict = json.loads(line)
        except json.JSONDecodeError as exc:
            log.warning("Bad JSON: %s — %.80s", exc, line)
            return

        topic       = msg.get("topic", "")
        self._tick  = msg.get("tick",  self._tick)
        self._phase = msg.get("phase", self._phase)

        log.debug("← %-35s tick=%-4d phase=%s", topic, self._tick, self._phase)

        if topic == "system.handshake":
            await self._on_handshake(msg)
            return

        for prefix, handler in _HANDLERS.items():
            if topic.startswith(prefix):
                try:
                    responses = await handler(msg, self)
                    for r in (responses or []):
                        await self.send(r)
                except Exception as exc:
                    log.exception("Handler %r raised: %s", prefix, exc)
                return

        log.debug("No handler for topic: %s", topic)

    async def _on_handshake(self, msg: dict) -> None:
        caps = msg.get("payload", {}).get("capabilities", [])
        ver  = msg.get("payload", {}).get("version", "?")
        log.info("Handshake from Godot: version=%s caps=%s", ver, caps)
        await self._send_world()
        await self.send_ready()

    async def _send_world(self) -> None:
        """
        Run the full world generation pipeline and send map + institutions.
        This runs in the event loop — for very large cell counts (>2000),
        consider offloading to a thread with asyncio.to_thread().
        """
        from palimpsest.python.bridge.protocol import Envelope, Topics
        from palimpsest.python.procgen         import generate_world
        from palimpsest.python.procgen.tectonics import TectonicConfig
        import random

        seed = _SEED if _SEED != 0 else random.randint(1, 2**31)
        log.info("Generating world: %d cells, %d civs, seed=%d …", _NUM_CELLS, _NUM_CIVS, seed)

        # Run tectonic sim in a thread so the event loop stays alive
        loop  = asyncio.get_running_loop()
        world = await loop.run_in_executor(
            None,
            lambda: generate_world(num_cells=_NUM_CELLS, num_civs=_NUM_CIVS, seed=seed)
        )

        log.info(
            "World ready: %d cells, %.1f%% ocean, %d civs",
            world["num_cells"],
            sum(1 for c in world["cells"] if c["is_oceanic"]) / max(world["num_cells"], 1) * 100,
            len(world["civs"]),
        )

        # Split into map payload and institution payload
        map_payload  = {k: v for k, v in world.items() if k != "civs"}
        inst_payload = {"civs": world["civs"]}

        map_cmd = Envelope.command("procgen", Topics.PROCGEN_APPLY_MAP, map_payload)
        await self.send(map_cmd.to_ndjson())
        log.info("Sent map payload (~%d KB)", len(map_cmd.to_ndjson()) // 1024)

        inst_cmd = Envelope.command("procgen", Topics.PROCGEN_APPLY_INSTS, inst_payload)
        await self.send(inst_cmd.to_ndjson())
        log.info("Sent institutions: %d civs", len(world["civs"]))


# ── Server ────────────────────────────────────────────────────────────────────

async def _serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    session = GodotSession(reader, writer)
    await session.run()
    writer.close()


async def main() -> None:
    global _NUM_CELLS, _NUM_CIVS, _SEED

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    )

    # Parse simple CLI args: --cells N --civs N --seed N
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--cells" and i + 1 < len(args): _NUM_CELLS = int(args[i + 1])
        if arg == "--civs"  and i + 1 < len(args): _NUM_CIVS  = int(args[i + 1])
        if arg == "--seed"  and i + 1 < len(args): _SEED      = int(args[i + 1])

    _register_all_handlers()

    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    server = await asyncio.start_unix_server(_serve, path=str(SOCKET_PATH))
    log.info(
        "Palimpsest bridge listening on %s  (cells=%d, civs=%d, seed=%s)",
        SOCKET_PATH, _NUM_CELLS, _NUM_CIVS, _SEED or "random",
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, server.close)

    async with server:
        await server.serve_forever()

    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    log.info("Bridge shut down cleanly")


def _register_all_handlers() -> None:
    from palimpsest.python.agents.council     import handle_ai
    from palimpsest.python.analytics.pipeline import handle_analytics
    from palimpsest.python.beliefs.karma      import handle_beliefs

    register_handler("phase.planning_start", handle_ai)
    register_handler("phase.turn_end",        handle_analytics)
    register_handler("institution.",           handle_analytics)
    register_handler("player.action",          handle_beliefs)
    register_handler("map.",                   handle_analytics)


if __name__ == "__main__":
    asyncio.run(main())
