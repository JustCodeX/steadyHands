"""Receives the instrument's position from the second board over the network.

The two Modulino Distance sensors sit on the hand-held remote, which has its
own UNO Q: one board does the sensing, this one runs the game. The remote
sends one small UDP datagram per frame (see app/tools/remote_sender.py); this
service turns them into InputFrame events with source "remote", so the game
cannot tell where the movement came from.

UDP, not TCP: a dropped frame is worthless by the time it would be resent, and
the game only ever looks at the difference between two frames anyway.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time

from ..core.config import RemoteConfig
from ..core.events import InputFrame, McuStatus
from ..core.service import Service

log = logging.getLogger(__name__)


class RemoteInput(Service):
    name = "remote_input"

    def __init__(self, bus, cfg: RemoteConfig) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_packet_t: float | None = None
        self._connected = False
        self.packets = 0

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.cfg.bind_host, self.cfg.port))
            sock.settimeout(0.5)
        except OSError as exc:
            log.error("cannot listen for the remote on %s:%d: %s", self.cfg.bind_host, self.cfg.port, exc)
            return
        self._sock = sock
        self._thread = threading.Thread(target=self._run, name="remote_input", daemon=True)
        self._thread.start()
        log.info("listening for the remote on %s:%d", self.cfg.bind_host, self.cfg.port)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def tick(self, dt: float) -> None:
        now = time.monotonic()
        alive = self._last_packet_t is not None and now - self._last_packet_t < self.cfg.timeout_s
        if alive != self._connected:
            self._connected = alive
            log.info("remote %s", "connected" if alive else "silent")
            self.bus.publish(McuStatus(connected=alive, detail="remote" if alive else "remote silent"))

    # --- receiving -----------------------------------------------------------

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            frame = self._parse(data)
            if frame is None:
                continue
            self._last_packet_t = time.monotonic()
            self.packets += 1
            self.bus.publish(frame)

    def _parse(self, data: bytes) -> InputFrame | None:
        """{"x": <mm>, "y": <mm>, "ok": <sensor bits>, "b": <buttons>, "seq": <n>}

        The buttons are the remote's own: holding one freezes the tool, see
        GameEngine._move_absolute. They never reach the game's button handling.
        """
        try:
            msg = json.loads(data.decode("utf-8"))
            return InputFrame(
                distance_mm=int(msg.get("x", 0)),
                distance_y_mm=int(msg.get("y", 0)),
                sensors_ok=int(msg.get("ok", 0)),
                buttons=int(msg.get("b", 0)),
                seq=int(msg.get("seq", 0)),
                source="remote",
            )
        except (ValueError, UnicodeDecodeError, AttributeError) as exc:
            log.debug("bad remote packet: %s", exc)
            return None
