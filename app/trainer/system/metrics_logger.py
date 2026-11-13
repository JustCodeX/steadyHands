"""Logs numbers only: command latency, game events, CPU and RAM per state.

Never logs transcripts or audio. Output is a CSV for docs/measurements.md.
"""
from __future__ import annotations

import csv
import logging
import os
import time
from pathlib import Path

from ..core.config import SystemConfig
from ..core.events import CommandEvent, GameEvent, GameSnapshot, GameState, MisheardEvent, VoiceStateChanged
from ..core.service import Service

log = logging.getLogger(__name__)


def read_cpu_times() -> tuple[int, int] | None:
    """(busy, total) jiffies from /proc/stat, or None where there is no /proc."""
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        values = [int(v) for v in parts[1:9]]
        idle = values[3] + values[4]
        total = sum(values)
        return total - idle, total
    except (OSError, ValueError, IndexError):
        return None


def read_mem() -> tuple[int, int] | None:
    """(MemAvailable MB, process RSS MB) or None."""
    try:
        avail = rss = None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) // 1024
                    break
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) // 1024
                    break
        if avail is None or rss is None:
            return None
        return avail, rss
    except (OSError, ValueError):
        return None


class MetricsLogger(Service):
    name = "metrics"

    def __init__(self, bus, cfg: SystemConfig) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self._state = GameState.MENU
        self._voice = "OFF"
        self._file = None
        self._writer = None
        self._last_sample = 0.0
        self._last_cpu = read_cpu_times()
        self.latencies_ms: list[float] = []
        bus.subscribe(CommandEvent, self._on_command)
        bus.subscribe(MisheardEvent, self._on_misheard)
        bus.subscribe(GameEvent, self._on_game_event)
        bus.subscribe(GameSnapshot, self._on_snapshot)
        bus.subscribe(VoiceStateChanged, self._on_voice)

    def start(self) -> None:
        path = Path(self.cfg.metrics_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists() or path.stat().st_size == 0
        self._file = open(path, "a", newline="")
        self._writer = csv.writer(self._file)
        if new:
            self._writer.writerow(["wall_time", "kind", "value", "game_state", "voice_state"])
        log.info("metrics -> %s", path)

    def stop(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def row(self, kind: str, value) -> None:
        if self._writer is None:
            return
        self._writer.writerow([f"{time.time():.3f}", kind, value, self._state.value, self._voice])
        self._file.flush()

    def _on_command(self, ev: CommandEvent) -> None:
        if ev.speech_end_t is not None:
            ms = (time.monotonic() - ev.speech_end_t) * 1000.0
            self.latencies_ms.append(ms)
            self.row("command_latency_ms", f"{ms:.0f}")
        self.row("command", ev.word)

    def _on_misheard(self, ev: MisheardEvent) -> None:
        self.row("misheard", ev.reason)

    def _on_game_event(self, ev: GameEvent) -> None:
        self.row("game_event", ev.kind)

    def _on_snapshot(self, snap: GameSnapshot) -> None:
        self._state = snap.state

    def _on_voice(self, ev: VoiceStateChanged) -> None:
        self._voice = ev.state.name

    def tick(self, dt: float) -> None:
        now = time.monotonic()
        if now - self._last_sample < self.cfg.sample_interval_s:
            return
        self._last_sample = now
        cpu = read_cpu_times()
        if cpu and self._last_cpu:
            busy = cpu[0] - self._last_cpu[0]
            total = cpu[1] - self._last_cpu[1]
            if total > 0:
                self.row("cpu_percent", f"{100.0 * busy / total:.1f}")
        self._last_cpu = cpu
        mem = read_mem()
        if mem:
            self.row("mem_available_mb", mem[0])
            self.row("process_rss_mb", mem[1])

    def latency_summary(self) -> dict[str, float]:
        if not self.latencies_ms:
            return {}
        s = sorted(self.latencies_ms)
        return {"n": len(s), "median_ms": s[len(s) // 2], "worst_ms": s[-1]}
