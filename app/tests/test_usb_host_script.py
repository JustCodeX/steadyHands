"""The root service script that keeps the hub's devices connected (setup/usb-host-mode.sh).

Run here against stand-in files for the kernel's role switch and hub port states."""
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "setup" / "usb-host-mode.sh"


class Board:
    def __init__(self, tmp_path, port_states, max_tries=3):
        self.role = tmp_path / "role"
        self.role.write_text("host\n")
        self.ports = {}
        for name, state in port_states.items():
            d = tmp_path / "hub" / name
            d.mkdir(parents=True)
            self.ports[name] = d / "state"
            self.ports[name].write_text(state + "\n")
        self.log = tmp_path / "log"
        env = {
            "PATH": "/usr/bin:/bin",
            "ROLE": str(self.role),
            "PORT_STATES": str(tmp_path / "hub" / "*" / "state"),
            "MAX_TRIES": str(max_tries),
            "POLL_S": "0.05",
            "DEVICE_S": "0.05",
            "SETTLE_S": "0.05",
        }
        self.proc = subprocess.Popen(["sh", str(SCRIPT)], env=env, stdout=self.log.open("w"), stderr=subprocess.STDOUT)

    def lines(self):
        return self.log.read_text().splitlines()

    def wait_for(self, text, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if any(text in line for line in self.lines()):
                return
            time.sleep(0.02)
        pytest.fail(f"{text!r} not logged; log: {self.lines()}")

    def stop(self):
        self.proc.kill()
        self.proc.wait()


@pytest.fixture
def board(tmp_path):
    made = []

    def make(port_states, **kwargs):
        made.append(Board(tmp_path, port_states, **kwargs))
        return made[-1]

    yield make
    for b in made:
        b.stop()


def test_device_mode_is_switched_back_to_host(board):
    b = board({"1-1-port3": "configured"})
    b.role.write_text("device\n")
    end = time.monotonic() + 5.0
    while b.role.read_text().strip() != "host" and time.monotonic() < end:
        time.sleep(0.02)
    assert b.role.read_text().strip() == "host"
    assert b.lines() == []


def test_healthy_and_empty_ports_cause_no_restart(board):
    b = board({"1-1-port2": "not attached", "1-1-port4": "configured"})
    time.sleep(0.6)
    assert b.lines() == []
    assert b.role.read_text().strip() == "host"


def test_failed_port_is_restarted_until_it_connects(board):
    b = board({"1-1-port1": "default", "1-1-port3": "default", "1-1-port2": "not attached"}, max_tries=50)
    b.wait_for("port restart 2 of 50")
    assert "1-1-port1 1-1-port3" in b.lines()[0] and "1-1-port2" not in b.lines()[0]
    for name in ("1-1-port1", "1-1-port3"):
        b.ports[name].write_text("configured\n")
    b.wait_for("no failed hub port left after")
    count = len(b.lines())
    time.sleep(0.4)
    assert len(b.lines()) == count  # quiet again
    assert b.role.read_text().strip() == "host"


def test_gives_up_after_max_tries_and_stays_quiet(board):
    b = board({"1-1-port3": "default"}, max_tries=3)
    b.wait_for("gave up after 3 port restart(s); still failed: 1-1-port3")
    time.sleep(0.4)
    assert sum("port restart" in line and "of 3" in line for line in b.lines()) == 3
    assert b.lines()[-1].startswith("steadyhands-usb: gave up")
    assert b.role.read_text().strip() == "host"
