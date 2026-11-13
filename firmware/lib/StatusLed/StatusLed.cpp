#include "StatusLed.h"

namespace sh {

bool StatusLed::begin() {
  pinMode(LED4_R, OUTPUT);
  pinMode(LED4_G, OUTPUT);
  pinMode(LED4_B, OUTPUT);
  show(VoiceState::Off);
  return true;
}

void StatusLed::write(pin_size_t pin, bool on) {
  digitalWrite(pin, (on != cfg::RGB_ACTIVE_LOW) ? HIGH : LOW);
}

void StatusLed::setRgb(bool r, bool g, bool b) {
  write(LED4_R, r);
  write(LED4_G, g);
  write(LED4_B, b);
}

void StatusLed::show(VoiceState state) {
  state_ = state;
  pulseOn_ = true;
  switch (state) {
    case VoiceState::Off: setRgb(false, false, false); break;
    case VoiceState::Listening: setRgb(false, true, false); break;   // green
    case VoiceState::Processing: setRgb(true, true, false); break;   // yellow
    case VoiceState::Speaking: setRgb(false, false, true); break;    // blue
  }
}

void StatusLed::update(uint32_t nowMs) {
  // Listening pulses so the player can tell it apart from a stuck LED.
  if (state_ != VoiceState::Listening) return;
  if (nowMs - lastPulseMs_ < cfg::RGB_PULSE_MS) return;
  lastPulseMs_ = nowMs;
  pulseOn_ = !pulseOn_;
  setRgb(false, pulseOn_, false);
}

}  // namespace sh
