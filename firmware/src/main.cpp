// Steady Hands MCU firmware: reads the Modulinos, filters the tilt, streams
// input frames to Linux over the Bridge, and drives the button LEDs and the
// on-board voice-state LED. All behaviour lives in the modules under lib/.
#include <Arduino.h>
#include <Arduino_Modulino.h>
#include <Wire.h>

#include "BridgeLink.h"
#include "ButtonPanel.h"
#include "Config.h"
#include "DistanceSensor.h"
#include "Firmware.h"
#include "KnobInput.h"
#include "PositionSensor.h"
#include "StatusLed.h"
#include "TiltSensor.h"

namespace {

sh::TiltSensor tiltSensor;
sh::PositionSensor positionSensor;
sh::KnobInput knobInput;
sh::ButtonPanel buttonPanel;
sh::DistanceSensor distanceSensor;
sh::StatusLed statusLed;
sh::BridgeLink bridgeLink(buttonPanel, statusLed, sh::cfg::FRAME_HZ);
sh::Firmware firmware;

uint32_t lastReportMs = 0;

// Which addresses answer on a bus — the only way to tell "sensor not wired"
// from "sensor wired but the driver refused it". Only ever call this on a bus
// that begin() has initialised: transfers on a deferred-init device fault.
void scanBus(const char* label, TwoWire& wire) {
  if (!Monitor) return;
  Monitor.print(label);
  uint8_t found = 0;
  for (uint8_t addr = 0x08; addr < 0x78; ++addr) {
    wire.beginTransmission(addr);
    if (wire.endTransmission() == 0) {
      Monitor.print(" 0x");
      Monitor.print(addr, HEX);
      ++found;
    }
  }
  if (!found) Monitor.print(" (nothing)");
  Monitor.println();
}

void report() {
  // Monitor only costs something while a monitor client is attached.
  if (!Monitor) return;
  const sh::InputFrame& f = bridgeLink.lastFrame();
  Monitor.print("frames=");
  Monitor.print(bridgeLink.framesSent());
  Monitor.print(" sensors=0x");
  Monitor.print(f.sensorsOk, HEX);
  Monitor.print(" tilt=");
  Monitor.print(f.tiltX, 2);
  Monitor.print(",");
  Monitor.print(f.tiltY, 2);
  Monitor.print(" knob=");
  Monitor.print(f.knob);
  Monitor.print(" buttons=0x");
  Monitor.print(f.buttons, HEX);
  Monitor.print(" distX=");
  Monitor.print(f.distanceMm);
  Monitor.print(" distY=");
  Monitor.print(f.distanceYMm);
  if (sh::cfg::CONTROL_MODE == 2) {
    Monitor.print(" tofX=");
    Monitor.print(positionSensor.foundX() ? "ok" : "MISSING");
    Monitor.print(" tofY=");
    Monitor.print(positionSensor.foundY() ? "ok" : "MISSING");
  }
  Monitor.println();
}

}  // namespace

void setup() {
  // The Bridge must come first: it owns the serial link and provides Monitor.
  firmware.add(bridgeLink);
  firmware.add(statusLed);
  firmware.add(knobInput);
  firmware.add(buttonPanel);
  if (sh::cfg::CONTROL_MODE == 2) {
    // PositionSensor owns both ToF chips (Qwiic + header bus); the plain
    // DistanceSensor must not also claim 0x29 on the Qwiic chain.
    firmware.add(positionSensor);
    bridgeLink.addSource(positionSensor);
  } else {
    firmware.add(tiltSensor);
    firmware.add(distanceSensor);
    bridgeLink.addSource(tiltSensor);
    bridgeLink.addSource(distanceSensor);
  }
  bridgeLink.addSource(knobInput);
  bridgeLink.addSource(buttonPanel);

  Modulino.begin(Wire1);  // UNO Q Qwiic connector
  Wire1.setClock(sh::cfg::I2C_CLOCK_HZ);

  firmware.begin();
  Monitor.begin(115200);
  if (Monitor) {
    Monitor.println("Steady Hands MCU firmware");
    for (size_t i = 0; i < firmware.count(); ++i) {
      sh::Module* m = firmware.at(i);
      Monitor.print("  ");
      Monitor.print(m->name());
      Monitor.println(m->ok() ? ": ok" : ": not found (will retry)");
    }
  }
}

void loop() {
  const uint32_t now = millis();
  firmware.update(now);
  if (now - lastReportMs >= 1000) {
    lastReportMs = now;
    report();
    // Only every tenth report: the scan walks 112 addresses, and that is a lot
    // of traffic on a bus someone is about to plug a module into.
    static uint8_t scanTick = 0;
    if (sh::cfg::CONTROL_MODE == 2 && !positionSensor.ok() && (++scanTick % 10) == 0) {
      scanBus("  i2c Wire1 (Qwiic):", Wire1);
      Monitor.print(positionSensor.viaHub() ? "  via Modulino Hub" : "  plain chain");
      if (positionSensor.clash()) Monitor.print("  CLASH: two chips on 0x29");
      Monitor.print("   tof ids: X=0x");
      Monitor.print(positionSensor.idX(), HEX);
      Monitor.print(" Y=0x");
      Monitor.print(positionSensor.idY(), HEX);
      Monitor.println("   (EBAA = VL53L4CD, ECAA = VL53L4ED, E8AA = two chips colliding)");
    }
  }
}
