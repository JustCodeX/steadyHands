// Modulino Distance (optional): hand height above the table.
#pragma once
#include <Arduino_Modulino.h>
#include "Config.h"
#include "InputSource.h"

namespace sh {

class DistanceSensor : public InputSource {
public:
  const char* name() const override { return "distance"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return found_; }
  void fill(InputFrame& frame) override;

  uint16_t distanceMm() const { return distanceMm_; }

private:
  ModulinoDistance sensor_;
  bool found_ = false;
  uint16_t distanceMm_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
