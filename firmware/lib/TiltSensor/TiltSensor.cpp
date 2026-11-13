#include "TiltSensor.h"

#include <math.h>

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

// Deadzone re-anchored at zero so there is no jump at the edge.
float TiltSensor::shape(float g, float gain) {
  const float mag = fabsf(g);
  if (mag < cfg::MOTION_DEADZONE_G) return 0.0f;
  const float out = mag - cfg::MOTION_DEADZONE_G;
  return (g < 0 ? -out : out) * gain;
}

void TiltSensor::resetFilters() {
  filterX_.reset();
  filterY_.reset();
  gravX_.reset();
  gravY_.reset();
  gravZ_.reset();
  velX_ = 0.0f;
  velY_ = 0.0f;
}

void TiltSensor::update(uint32_t nowMs) {
  if (!found_) {
    if (nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
      lastRetryMs_ = nowMs;
      found_ = imu_.begin();
      if (found_) resetFilters();
    }
    return;
  }
  if (nowMs - lastSampleMs_ < 1000 / cfg::SENSOR_HZ) return;
  lastSampleMs_ = nowMs;
  if (!imu_.available()) return;
  if (!imu_.update()) return;

  const float ax = imu_.getX();
  const float ay = imu_.getY();
  const float az = imu_.getZ();

  if (!cfg::MOTION_CONTROL) {
    filterX_.update(clampG(ax));
    filterY_.update(clampG(ay));
    return;
  }

  // Gravity estimate: only the slow part of the signal is orientation.
  const float gx = gravX_.update(ax);
  const float gy = gravY_.update(ay);
  const float gz = gravZ_.update(az);

  // Linear acceleration = measurement minus gravity.
  float lx = ax - gx;
  float ly = ay - gy;
  float lz = az - gz;

  // Drop the vertical component (lifting the hand must not move the point).
  const float gSq = gx * gx + gy * gy + gz * gz;
  if (gSq > 0.25f) {  // gravity estimate is sane (> 0.5 g)
    const float k = (lx * gx + ly * gy + lz * gz) / gSq;
    lx -= k * gx;
    ly -= k * gy;
    lz -= k * gz;
  }

  // Integrate into a leaky velocity (m/s). Sensor X = sideways, sensor Y =
  // towards/away from the body (board upright).
  const float dt = 1.0f / cfg::SENSOR_HZ;
  const float leak = dt / cfg::MOTION_LEAK_TAU_S;
  velX_ += shape(lx, 1.0f) * 9.81f * dt;
  velY_ += shape(ly, 1.0f) * 9.81f * dt;
  velX_ -= velX_ * leak;
  velY_ -= velY_ * leak;

  filterX_.update(clampG(cfg::MOTION_DIR_X * velX_ / cfg::MOTION_FULL_SPEED_MPS));
  filterY_.update(clampG(cfg::MOTION_DIR_Y * velY_ / cfg::MOTION_FULL_SPEED_MPS));
}

void TiltSensor::fill(InputFrame& frame) {
  frame.tiltX = filterX_.value();
  frame.tiltY = filterY_.value();
  if (found_) frame.sensorsOk |= InputFrame::TILT;
}

}  // namespace sh
