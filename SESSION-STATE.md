# Session-Stand 13. November 2026, ~16:00

Übergabe für eine neue Claude-Session. Projekt: **Steady Hands** — Chirurgie-Trainer
auf dem Arduino UNO Q für den Speech-to-Speech-Hackathon (Ende: 14. Nov, 12:00).
Plan in [PLAN.md](PLAN.md), Verkabelung in [WIRING.md](WIRING.md).

## Git

- Branch: **`code/mcu-and-linux-skeleton`** ist ausgecheckt (Branch der Partner,
  komplettes Projekt: MCU-Firmware, Linux-App, 3 Levels, Tests, Setup-Skripte).
- `main` ist dahinter. **Zwei lokale Commits, noch nicht gepusht:**
  `a2344a6` (xset → x11-xserver-utils in board_setup.sh) und
  `b4b6817` (increment1-Messwerte in docs/measurements.md + WIRING.md gemergt).
- Untracked, bewusst: `increment1/` (s. u.), `promptpimps-unoq.code-workspace`
  (Multi-Root-Workspace: Repo-Root + firmware/, weil das PlatformIO-Plugin
  `platformio.ini` im Workspace-Ordner-Root braucht), `SESSION-STATE.md`.

## Board „geil“ (UNO Q, Serial 2510574293)

- **Zugang: SSH** `arduino@192.168.1.155`, Key `~/.ssh/id_ed25519_2026-11-13`
  ist autorisiert (auch im ssh-agent). WLAN „hackathon“.
- **adb ist bewusst deaktiviert** (`systemctl disable adbd`, durch board_setup):
  USB-adb kippt den einzigen USB-C-Port in Device-Mode und wirft den Hub raus.
  Alle Skripte können SSH: `BOARD_SSH=arduino@192.168.1.155`.
- Ein root-Service `steadyhands-usb-host.service` hält den Port in Host-Mode
  (Type-C-Negotiation kippt ihn sonst ~16 s nach Boot).
- Hardware am Hub: Elecrow 7"-Monitor (HDMI; **meldet 1920×1080**, nicht die
  1024×600 aus WIRING.md — Renderer setzt trotzdem 1024×600), JBL Tune 530C
  USB-Headset (= `plughw:0,0`, kann **kein natives 16 kHz** → immer `plughw:`,
  nie `hw:`), Netzteil.
- Autologin (lightdm) + Autostart sind eingerichtet: **Boot → Trainer läuft
  vollautomatisch** (verifiziert: Boot 15:18:14, App komplett oben 15:18:50,
  MCU-Link verbunden). `arduino` ist in der Gruppe `arduino-router`.
- Disk: ~2,7 GB frei (72 %). RAM: ~3 GB verfügbar.
- Aufräumbar bei Platznot: `~/trainer-app` + `~/trainer-venv` (411 MB, mein
  Inkrement-1-Setup; erst löschen, wenn Partner-Setup sicher bleibt).

## Partner-App (der aktive Stand)

- Liegt auf dem Board unter `~/promptpimps-unoq` (app/ + levels/), venv
  `app/.venv`, Modelle in `app/models/` (Vosk small en + Piper lessac-medium),
  219 vorgerenderte Clips in `app/assets/clips/`.
- Start: `app/run.sh`; Log: `app/logs/trainer.log`; Metriken:
  `app/logs/metrics.csv`. Autostart über `~/.config/autostart/steadyhands.desktop`.
- Sync vom Mac: `BOARD_SSH=arduino@192.168.1.155 app/tools/sync_to_board.sh`
  (schont .venv/models/logs/clips auf dem Board).
- STT: **Vosk mit grammatik-beschränktem Vokabular** (21 Phrasen) — strukturell
  immun gegen das „forceps“→„four steps“-Problem. Renderer: pygame auf X (:0).

## Firmware: geflasht und verifiziert

Die Partner-Firmware ist auf der MCU (Flash 15:33 Uhr, `board.sh upload` über
SSH, 4:34 Min; RAM 22 %, Flash 16,6 %). `trainer.log` meldet seitdem
**„MCU frames arriving"** — die Kette Modulinos → MCU → RouterBridge → McuLink
→ GameEngine ist durchgängig. PlatformIO ist jetzt auf dem Board installiert
(`~/.platformio/penv`), weitere Builds dauern Sekunden.

**Remote nachverifiziert (~15:40):** Der MCU-`status`-RPC meldet
`sensorsOk = 0b111` — **TILT, KNOB, BUTTONS antworten**; DISTANCE fehlt
erwartungsgemäß (optionales Stretch-Modul, nicht verbaut). MCU läuft seit
15:33:26 ohne Reset (millis-Rückrechnung), kein einziges „frames stopped" im
Log. Trick dafür: zweiter Bridge-Client darf parallel zur App `call("ping")` /
`call("status")` machen — nur kein eigenes `provide("input")` registrieren.

Offen: Buttons/Tilt **physisch im Spiel** noch nicht nachgetestet (braucht
jemanden am Gerät). Falls Buttons trotz ankommender Frames nichts tun:
Button-Bitmaske in den `input`-Frames prüfen.

Metriken (Idle, Median): RSS 287 MB, 2,2 GB RAM verfügbar, CPU ~25 %.

## increment1/ (mein isolierter Vorarbeits-Ordner, heute entstanden)

Eigenständiges „gesprochenes Wort → gesprochene Antwort“ mit Whistle (Cactus),
Framebuffer-Avatar, VAD, Messwerten. **Vom Partner-Branch fachlich überholt.**
Die drei Gold-Befunde (Messwerte/Noise-Floor, Threshold-0,75-Fehlauslöser,
1920×1080-EDID) sind **in `docs/measurements.md` und WIRING.md gemergt**
(Commit `b4b6817`). Der Ordner kann archiviert oder gelöscht werden — noch da,
weil noch nützlich: `tools/applab.py` (App-Labs-Orchestrator-REST auf
127.0.0.1:8800), `tools/assistant-ctl.sh` (PID-File-Pattern), PlatformIO-
Custom-Targets + VS-Code-Tasks.

## Wichtige Eigenheiten (erspart Debugging)

- `pio run` baut auf macOS **nicht** (arduinoq-Platform ist Linux-only) —
  immer über `tools/board.sh`, der auf dem Board baut.
- `pkill -f <python-skript>` über SSH killt die eigene SSH-Session (Pattern
  matcht die eigene Kommandozeile). PID-File benutzen —
  `increment1/tools/assistant-ctl.sh` zeigt wie.
- Board-DNS liefert teils nur IPv6 ohne Route: Downloads mit `curl -4`.
- Python 3.13 auf dem Board: kein `audioop` mehr; System-Python ohne pip
  (Bootstrap über Debians pip-Wheel, siehe board_setup.sh Schritt 3).
- App Lab auf dem Mac keinesfalls eine App starten lassen: **flasht die MCU um**
  und überschreibt unsere Firmware (PLAN.md D1).
- Es sind ständig fremde UNO Qs im Netz sichtbar (ArminArduinoQ, Brockmann,
  JustuBoard, TestBord …) — vor jedem Deploy Serial/IP prüfen: **2510574293 /
  192.168.1.155**.

## Sinnvolle nächste Schritte

1. ~~Firmware-Upload prüfen~~ ✅ (sensorsOk 0b111) — **Buttons/Tilt physisch
   im Spiel testen** (jemand ans Gerät).
2. ~~xset-Fix committen~~ ✅ `a2344a6`. ~~Messwerte mergen~~ ✅ `b4b6817`.
   Beide Commits **pushen**, sobald mit den Partnern abgestimmt.
3. increment1/ archivieren oder löschen (Befunde sind gemergt; applab.py &
   Co. vorher rausziehen, falls behalten).
4. P6-Messreihe: 20 gesprochene Kommandos, Median/Worst aus metrics.csv.
5. Threshold-Härtetest im Hallenlärm (Co-op-Fehlauslöser; Matcher-Default
   steht noch auf 0,75 — Befund in docs/measurements.md).
6. Energie-Messungen mit dem PeakTech (WIRING.md), Kriterien-Tabelle füllen.
