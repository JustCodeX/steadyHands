// Horn and red LED, switched on together for a given time.
#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Module.h"

namespace sh {

class Alarm : public Module {
public:
  Alarm(uint8_t ledPin, uint8_t hornPin, bool hornPassive)
      : ledPin_(ledPin), hornPin_(hornPin), hornPassive_(hornPassive) {}

  const char* name() const override { return "alarm"; }
  bool begin() override;
  void update(uint32_t nowMs) override;

  // Horn and LED on for durationMs (clamped to ALARM_MAX_MS). 0 switches off.
  void trigger(uint16_t durationMs);
  bool active() const { return active_; }

private:
  void on(uint16_t durationMs);
  void off();

  uint8_t ledPin_;
  uint8_t hornPin_;
  bool hornPassive_;
  bool active_ = false;
  uint32_t offAtMs_ = 0;
};

}  // namespace sh
