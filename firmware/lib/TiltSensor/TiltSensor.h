// Modulino Movement in the handheld instrument.
//
// Tilt mode (MOTION_CONTROL = false): samples the accelerometer at SENSOR_HZ,
// low-pass filters X and Y, and reports them as tilt in g.
//
// Motion mode (MOTION_CONTROL = true): the board is held upright and the point
// follows the hand's sideways movement. Per sample: estimate gravity with a
// slow low-pass, subtract it, project the remaining linear acceleration onto
// the horizontal plane, and integrate it into a leaky velocity — the point
// moves while the hand moves and stays put when it stops. The result still
// goes out as tiltX/tiltY, so frame format and app stay unchanged.
#pragma once
#include <Arduino_Modulino.h>
#include "Config.h"
#include "InputSource.h"
#include "LowPassFilter.h"

namespace sh {

class TiltSensor : public InputSource {
public:
  TiltSensor()
      : filterX_(cfg::TILT_CUTOFF_HZ, cfg::SENSOR_HZ),
        filterY_(cfg::TILT_CUTOFF_HZ, cfg::SENSOR_HZ),
        gravX_(cfg::MOTION_GRAVITY_CUTOFF_HZ, cfg::SENSOR_HZ),
        gravY_(cfg::MOTION_GRAVITY_CUTOFF_HZ, cfg::SENSOR_HZ),
        gravZ_(cfg::MOTION_GRAVITY_CUTOFF_HZ, cfg::SENSOR_HZ) {}

  const char* name() const override { return "tilt"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return found_; }
  void fill(InputFrame& frame) override;

  float tiltX() const { return filterX_.value(); }
  float tiltY() const { return filterY_.value(); }

private:
  static float clampG(float g);
  static float shape(float g, float gain);
  void resetFilters();

  ModulinoMovement imu_;
  LowPassFilter filterX_;
  LowPassFilter filterY_;
  LowPassFilter gravX_;
  LowPassFilter gravY_;
  LowPassFilter gravZ_;
  float velX_ = 0.0f;
  float velY_ = 0.0f;
  bool found_ = false;
  uint32_t lastSampleMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
