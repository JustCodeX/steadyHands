// Modulino Knob: rotary position and push button.
#pragma once
#include <Arduino_Modulino.h>
#include "Config.h"
#include "InputSource.h"

namespace sh {

class KnobInput : public InputSource {
public:
  const char* name() const override { return "knob"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return found_; }
  void fill(InputFrame& frame) override;

  int16_t position() const { return position_; }
  bool pressed() const { return pressed_; }

private:
  ModulinoKnob knob_;
  bool found_ = false;
  int16_t position_ = 0;
  bool pressed_ = false;
  uint32_t lastPollMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
