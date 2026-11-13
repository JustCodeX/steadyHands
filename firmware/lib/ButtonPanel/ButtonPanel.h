// Modulino Buttons: three buttons A, B, C and their LEDs.
#pragma once
#include <Arduino_Modulino.h>
#include "Config.h"
#include "InputSource.h"

namespace sh {

class ButtonPanel : public InputSource {
public:
  const char* name() const override { return "buttons"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return found_; }
  void fill(InputFrame& frame) override;

  // Bit 0 = LED A, bit 1 = LED B, bit 2 = LED C.
  void setLeds(uint8_t mask);
  uint8_t mask() const { return mask_; }

private:
  ModulinoButtons buttons_;
  bool found_ = false;
  uint8_t mask_ = 0;
  uint8_t ledMask_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
