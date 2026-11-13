#include "PositionSensor.h"

namespace sh {

namespace {

bool deviceAnswers(TwoWire& wire, uint8_t addr7) {
  wire.beginTransmission(addr7);
  return wire.endTransmission() == 0;
}

}  // namespace

// Both Modulino Distance modules ship locked to 0x29, so they cannot share a
// bus as they are. Three ways out, tried in this order:
//
//  1. Modulino Hub (TCA9548A) in the chain: each module gets its own channel
//     and both keep 0x29. Detected at run time, nothing to configure.
//  2. Plain chain, modules plugged in one after the other: whichever module is
//     alone on 0x29 is moved to POS_ADDR_X, which frees 0x29 for the next one.
//     This is why update() keeps retrying — plug the second module in a few
//     seconds after boot and it joins on its own.
//  3. A wire from the X module's XSHUT pad to PIN_TOF_XSHUT, which lets the
//     firmware do the isolation itself with both modules already plugged in.
//
// A reassigned address lives in the sensor's RAM only, so cutting power to the
// chain puts both back on 0x29 and the sequence has to run again.
void PositionSensor::bringUp() {
  hub_ = deviceAnswers(Wire1, cfg::POS_HUB_ADDR);
  if (hub_) {
    tofX_.useHub(cfg::POS_HUB_ADDR, cfg::POS_HUB_CH_X);
    tofY_.useHub(cfg::POS_HUB_ADDR, cfg::POS_HUB_CH_Y);
    foundX_ = tofX_.begin(0x29);
    foundY_ = tofY_.begin(0x29);
    collision_ = false;
    return;
  }

  // With the XSHUT wire the modules can be separated in one go.
  if (haveXshutWire()) {
    tofX_.powerOff();
    delay(10);
    foundY_ = tofY_.begin(0x29);
    tofX_.powerOn();
    foundX_ = tofX_.begin(cfg::POS_ADDR_X);
    collision_ = false;
    return;
  }

  // Plain chain: park the first module we can talk to, then wait for the
  // second one to appear on the freed address. A module parked by an earlier
  // attempt already sits on POS_ADDR_X, so look there first.
  collision_ = false;
  if (!foundX_) {
    if (healthy(tofX_.modelId(cfg::POS_ADDR_X))) {
      foundX_ = tofX_.begin(cfg::POS_ADDR_X, cfg::POS_ADDR_X);
      return;
    }
    const uint16_t id = tofX_.modelId(0x29);
    if (healthy(id)) {
      foundX_ = tofX_.begin(cfg::POS_ADDR_X, 0x29);
    } else if (id != 0) {
      collision_ = true;  // two chips answering 0x29 together
    }
    return;
  }
  if (!foundY_) {
    const uint16_t id = tofY_.modelId(0x29);
    if (healthy(id)) {
      foundY_ = tofY_.begin(0x29, 0x29);
    } else if (id != 0) {
      collision_ = true;
    }
  }
}

bool PositionSensor::healthy(uint16_t id) {
  return id == ToFReader::ID_CD || id == ToFReader::ID_ED;
}

// The pad is pulled up on the module, so a wire to D4 reads low once we drive
// it; without a wire the pin floats and this stays false.
bool PositionSensor::haveXshutWire() const { return cfg::POS_USE_XSHUT; }

bool PositionSensor::begin() {
  bringUp();
  return foundX_ && foundY_;
}

// mm -> -1..+1 over the working range; larger distance = larger value
// (further from the left wall = right, further from the top wall = down).
float PositionSensor::normalise(uint16_t mm) {
  const float span = static_cast<float>(cfg::POS_MAX_MM - cfg::POS_MIN_MM);
  float n = (static_cast<float>(mm) - cfg::POS_MIN_MM) / span;
  if (n < 0.0f) n = 0.0f;
  if (n > 1.0f) n = 1.0f;
  return n * 2.0f - 1.0f;
}

void PositionSensor::update(uint32_t nowMs) {
  if ((!foundX_ || !foundY_) && nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
    lastRetryMs_ = nowMs;
    bringUp();
  }
  if (nowMs - lastPollMs_ < 1000 / cfg::SLOW_HZ) return;
  lastPollMs_ = nowMs;
  // Invalid or stale readings (hand out of range, oblique wall hit) keep the
  // last position instead of jerking the tool around.
  if (foundX_ && tofX_.poll()) {
    lastXMm_ = tofX_.lastMm();
    filterX_.update(normalise(lastXMm_));
  }
  if (foundY_ && tofY_.poll()) {
    lastYMm_ = tofY_.lastMm();
    filterY_.update(normalise(lastYMm_));
  }
}

void PositionSensor::fill(InputFrame& frame) {
  frame.tiltX = filterX_.value();
  frame.tiltY = filterY_.value();
  frame.distanceMm = lastXMm_;
  frame.distanceYMm = lastYMm_;
  if (foundX_) frame.sensorsOk |= InputFrame::TOF_X;
  if (foundY_) frame.sensorsOk |= InputFrame::TOF_Y;
  if (collision_) frame.sensorsOk |= InputFrame::TOF_CLASH;
  if (foundX_ && foundY_) frame.sensorsOk |= InputFrame::DISTANCE;
}

}  // namespace sh
