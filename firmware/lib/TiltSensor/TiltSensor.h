// Modulino Movement in the handheld instrument. Samples the accelerometer at
// SENSOR_HZ, low-pass filters X and Y, and reports them as tilt in g.
#pragma once
#include <Arduino_Modulino.h>
#include "Config.h"
#include "InputSource.h"
#include "LowPassFilter.h"

namespace sh {

class TiltSensor : public InputSource {
public:
  TiltSensor()
      : filterX_(cfg::TILT_CUTOFF_HZ, cfg::SENSOR_HZ), filterY_(cfg::TILT_CUTOFF_HZ, cfg::SENSOR_HZ) {}

  const char* name() const override { return "tilt"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return found_; }
  void fill(InputFrame& frame) override;

  float tiltX() const { return filterX_.value(); }
  float tiltY() const { return filterY_.value(); }

private:
  static float clampG(float g);

  ModulinoMovement imu_;
  LowPassFilter filterX_;
  LowPassFilter filterY_;
  bool found_ = false;
  uint32_t lastSampleMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
