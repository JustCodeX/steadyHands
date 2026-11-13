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
#include "StatusLed.h"
#include "TiltSensor.h"

namespace {

sh::TiltSensor tiltSensor;
sh::KnobInput knobInput;
sh::ButtonPanel buttonPanel;
sh::DistanceSensor distanceSensor;
sh::StatusLed statusLed;
sh::BridgeLink bridgeLink(buttonPanel, statusLed, sh::cfg::FRAME_HZ);
sh::Firmware firmware;

uint32_t lastReportMs = 0;

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
  Monitor.print(" dist=");
  Monitor.println(f.distanceMm);
}

}  // namespace

void setup() {
  // The Bridge must come first: it owns the serial link and provides Monitor.
  firmware.add(bridgeLink);
  firmware.add(statusLed);
  firmware.add(tiltSensor);
  firmware.add(knobInput);
  firmware.add(buttonPanel);
  firmware.add(distanceSensor);

  bridgeLink.addSource(tiltSensor);
  bridgeLink.addSource(knobInput);
  bridgeLink.addSource(buttonPanel);
  bridgeLink.addSource(distanceSensor);

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
  }
}
