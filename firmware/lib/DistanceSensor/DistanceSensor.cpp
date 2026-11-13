#include "DistanceSensor.h"

namespace sh {

bool DistanceSensor::begin() {
  found_ = sensor_.begin();
  return found_;
}

void DistanceSensor::update(uint32_t nowMs) {
  if (!found_) {
    if (nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
      lastRetryMs_ = nowMs;
      begin();
    }
    return;
  }
  if (nowMs - lastPollMs_ < 1000 / cfg::SLOW_HZ) return;
  lastPollMs_ = nowMs;
  if (sensor_.available()) {
    const float mm = sensor_.get();
    distanceMm_ = (mm > 0.0f && mm < 65535.0f) ? static_cast<uint16_t>(mm) : 0;
  }
}

void DistanceSensor::fill(InputFrame& frame) {
  frame.distanceMm = distanceMm_;
  if (found_) frame.sensorsOk |= InputFrame::DISTANCE;
}

}  // namespace sh
