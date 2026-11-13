// Stand-in for the Arduino_LTR381RGB library (Modulino Light sensor).
//
// Modulino.h includes this header unconditionally. The real library's .cpp
// uses `Serial`, which on the UNO Q only exists in files that can see the
// RouterBridge headers, so it does not build under PlatformIO. We do not use
// the Modulino Light, so this stub declares just what ModulinoLight needs and
// `lib_ignore` keeps the real library out of the build.
#pragma once
#include <Arduino.h>
#include <Wire.h>

class LTR381RGBClass {
public:
  LTR381RGBClass(TwoWire& wire, uint8_t address) : wire_(&wire), address_(address) {}
  int begin() { return 0; }  // never present
  void end() {}
  int readAllSensors(int& r, int& g, int& b, int& rawlux, int& lux, int& ir) {
    r = g = b = rawlux = lux = ir = 0;
    return 0;
  }
  void getHSL(int, int, int, float& h, float& s, float& l) { h = s = l = 0.0f; }

private:
  TwoWire* wire_;
  uint8_t address_;
};
