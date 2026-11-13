#include "TiltSensor.h"

namespace sh {

bool TiltSensor::begin() {
  found_ = imu_.begin();
  return found_;
}

float TiltSensor::clampG(float g) {
  if (g > cfg::TILT_CLAMP_G) return cfg::TILT_CLAMP_G;
  if (g < -cfg::TILT_CLAMP_G) return -cfg::TILT_CLAMP_G;
  return g;
}

void TiltSensor::update(uint32_t nowMs) {
  if (!found_) {
    if (nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
      lastRetryMs_ = nowMs;
      found_ = imu_.begin();
      if (found_) {
        filterX_.reset();
        filterY_.reset();
      }
    }
    return;
  }
  if (nowMs - lastSampleMs_ < 1000 / cfg::SENSOR_HZ) return;
  lastSampleMs_ = nowMs;
  if (!imu_.available()) return;
  if (!imu_.update()) return;
  filterX_.update(clampG(imu_.getX()));
  filterY_.update(clampG(imu_.getY()));
}

void TiltSensor::fill(InputFrame& frame) {
  frame.tiltX = filterX_.value();
  frame.tiltY = filterY_.value();
  if (found_) frame.sensorsOk |= InputFrame::TILT;
}

}  // namespace sh
