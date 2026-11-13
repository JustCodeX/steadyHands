#include "Alarm.h"

namespace sh {

bool Alarm::begin() {
  pinMode(ledPin_, OUTPUT);
  pinMode(hornPin_, OUTPUT);
  off();
  return true;
}

void Alarm::trigger(uint16_t durationMs) {
  if (durationMs == 0) {
    off();
    return;
  }
  if (durationMs > cfg::ALARM_MAX_MS) durationMs = cfg::ALARM_MAX_MS;
  on(durationMs);
  offAtMs_ = millis() + durationMs;
}

void Alarm::update(uint32_t nowMs) {
  if (active_ && static_cast<int32_t>(nowMs - offAtMs_) >= 0) off();
}

void Alarm::on(uint16_t durationMs) {
  digitalWrite(ledPin_, HIGH);
  if (hornPassive_) {
    tone(hornPin_, cfg::HORN_TONE_HZ, durationMs);
  } else {
    digitalWrite(hornPin_, HIGH);
  }
  active_ = true;
}

void Alarm::off() {
  digitalWrite(ledPin_, LOW);
  if (hornPassive_) noTone(hornPin_);
  digitalWrite(hornPin_, LOW);
  active_ = false;
}

}  // namespace sh
