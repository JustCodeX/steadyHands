// On-board RGB LED 4 shows what the voice system is doing.
#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Module.h"

namespace sh {

// Must match VoiceState in app/trainer/core/events.py.
enum class VoiceState : uint8_t { Off = 0, Listening = 1, Processing = 2, Speaking = 3 };

class StatusLed : public Module {
public:
  const char* name() const override { return "status_led"; }
  bool begin() override;
  void update(uint32_t nowMs) override;

  void show(VoiceState state);
  VoiceState state() const { return state_; }

private:
  void setRgb(bool r, bool g, bool b);
  void write(pin_size_t pin, bool on);

  VoiceState state_ = VoiceState::Off;
  bool pulseOn_ = true;
  uint32_t lastPulseMs_ = 0;
};

}  // namespace sh
