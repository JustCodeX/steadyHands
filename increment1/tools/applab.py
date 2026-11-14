#!/usr/bin/env python3
"""Drive the UNO Q from the command line, the way Arduino App Lab does.

App Lab runs a control server ("orchestrator") on 127.0.0.1:8800 for the board
it is connected to. It needs no token and is up for as long as App Lab is, so
this talks to it directly. App Lab must be running and connected to a board.

  tools/applab.py apps                   apps on the board
  tools/applab.py models                 AI models, and which are installed
  tools/applab.py bricks                 available bricks
  tools/applab.py resources              CPU, RAM and disk on the board
  tools/applab.py logs <app-id> [n]      an app's recent Python logs
  tools/applab.py config                 where the board keeps apps and data
  tools/applab.py start <app-id>         run an app  (see the warning below)
  tools/applab.py stop <app-id>
  tools/applab.py get <path>             any GET endpoint, e.g. v1/apps

Warning: starting an App Lab app reflashes the MCU with that app's own sketch
and overwrites ours (PLAN.md, D1). `start` therefore asks before it runs;
`tools/board.sh upload` puts our sketch back.
"""

import json
import sys
import urllib.error
import urllib.request

ORCHESTRATOR = "http://127.0.0.1:8800"


class AppLabError(RuntimeError):
    pass


def request(path, method="GET"):
    url = f"{ORCHESTRATOR}/{path.lstrip('/')}"
    req = urllib.request.Request(url, method=method)
    try:
        return urllib.request.urlopen(req, timeout=60).read().decode()
    except urllib.error.HTTPError as exc:
        raise AppLabError(f"{method} {path} -> HTTP {exc.code}: {exc.read().decode()[:200]}") from exc
    except urllib.error.URLError as exc:
        raise AppLabError(
            f"no answer from App Lab on {ORCHESTRATOR} ({exc.reason}).\n"
            "Start Arduino App Lab and connect it to a board, then retry."
        ) from exc


def get_json(path):
    raw = request(path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def human_gb(n):
    return f"{n / 1024 ** 3:.2f} GB"


def read_sse(path, wanted):
    """Read an event stream until every wanted event has been seen.

    /v1/system/resources streams for as long as the connection is open, so
    reading it to completion would never return.
    """
    url = f"{ORCHESTRATOR}/{path.lstrip('/')}"
    events, name = {}, None
    try:
        stream = urllib.request.urlopen(url, timeout=30)
    except urllib.error.URLError as exc:
        raise AppLabError(
            f"no answer from App Lab on {ORCHESTRATOR} ({exc.reason}).\n"
            "Start Arduino App Lab and connect it to a board, then retry."
        ) from exc
    with stream:
        for raw in stream:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: ") and name:
                try:
                    events[name] = json.loads(line[6:])
                except json.JSONDecodeError:
                    events[name] = line[6:]
                if wanted <= events.keys():
                    break
    return events


def cmd_resources():
    ev = read_sse("v1/system/resources", {"mem", "cpu", "disk"})
    mem, cpu, disk = ev.get("mem", {}), ev.get("cpu", {}), ev.get("disk", {})
    if mem:
        used, total = mem.get("used", 0), mem.get("total", 0)
        free = total - used
        print(f"RAM   {human_gb(used)} / {human_gb(total)} used, {human_gb(free)} free")
    if cpu:
        print(f"CPU   {cpu.get('used_percent', 0):.1f}%")
    if disk:
        print(f"Disk  {human_gb(disk.get('used', 0))} / {human_gb(disk.get('total', 0))} used")
    if not ev:
        print("no data")


def cmd_apps():
    for a in get_json("v1/apps").get("apps", []):
        status = a.get("status", "-")
        print(f"{a.get('id','?')}\n    {a.get('name','?')}  [{status}]")


def cmd_models():
    for m in get_json("v1/models").get("models", []):
        mark = "installed" if m.get("installed") else "not installed"
        name = m.get("name", "?")
        size = m.get("size")
        size_s = f"  {size / 1024 ** 2:.0f} MB" if isinstance(size, (int, float)) else ""
        print(f"{m.get('id_decoded', m.get('id','?'))}\n    {name}  [{mark}]{size_s}")


def cmd_bricks():
    data = get_json("v1/bricks")
    items = data.get("bricks", data) if isinstance(data, dict) else data
    for b in items if isinstance(items, list) else []:
        print(f"{b.get('id','?')}\n    {b.get('name','?')} - {b.get('description','')[:90]}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "resources":
            cmd_resources()
        elif cmd == "apps":
            cmd_apps()
        elif cmd == "models":
            cmd_models()
        elif cmd == "bricks":
            cmd_bricks()
        elif cmd == "config":
            print(json.dumps(get_json("v1/config"), indent=2))
        elif cmd == "logs":
            if not rest:
                raise AppLabError("logs needs an app id")
            tail = rest[1] if len(rest) > 1 else "100"
            print(request(f"v1/apps/{rest[0]}/logs?tail={tail}"))
        elif cmd in ("start", "stop"):
            if not rest:
                raise AppLabError(f"{cmd} needs an app id")
            if cmd == "start":
                print(
                    "Starting an App Lab app reflashes the MCU and overwrites our\n"
                    "sketch (PLAN.md, D1). Run `tools/board.sh upload` afterwards.",
                    file=sys.stderr,
                )
                if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
                    print("cancelled", file=sys.stderr)
                    return 1
            print(request(f"v1/apps/{rest[0]}/{cmd}", method="POST") or "ok")
        elif cmd == "get":
            if not rest:
                raise AppLabError("get needs a path")
            print(request(rest[0]))
        else:
            raise AppLabError(f"unknown command {cmd!r}; see --help")
        return 0
    except AppLabError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
