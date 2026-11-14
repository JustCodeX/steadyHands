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

void PositionAxis::push(uint16_t mm) {
  samples[next] = mm;
  next = (next + 1) % cfg::POS_MEDIAN;
  if (filled < cfg::POS_MEDIAN) ++filled;
}

uint16_t PositionAxis::median() const {
  if (filled == 0) return 0;
  uint16_t sorted[cfg::POS_MEDIAN];
  for (uint8_t i = 0; i < filled; ++i) sorted[i] = samples[i];
  for (uint8_t i = 1; i < filled; ++i) {  // insertion sort, at most 5 elements
    const uint16_t v = sorted[i];
    int8_t j = static_cast<int8_t>(i) - 1;
    while (j >= 0 && sorted[j] > v) {
      sorted[j + 1] = sorted[j];
      --j;
    }
    sorted[j + 1] = v;
  }
  return sorted[filled / 2];
}

bool PositionAxis::stale(uint32_t nowMs) const {
  return lastGoodMs == 0 || nowMs - lastGoodMs > cfg::POS_STALE_MS;
}

// The deadband drags along instead of re-arming after every step: once the
// hand has pushed past it, the held position follows the reading continuously,
// trailing it by exactly POS_DEADBAND_MM. Snapping the held value onto the
// reading instead would move it by the whole deadband at once and then sit
// still until the next breakout - a staircase rather than a movement. Noise
// smaller than the band still never moves anything.
void PositionSensor::feed(PositionAxis& axis, ToFReader& tof, bool& found, uint32_t nowMs) {
  if (!tof.poll()) {
    // Silent for a while although the chip is still there: kick its ranging.
    // A chip that will not even re-init at the address it already has is gone
    // - unplugged, or knocked off the chain. Drop the flag, or the panel keeps
    // reporting a sensor that is not there and bringUp() never looks for it
    // again. A hand out of range does not get here: the chip still answers,
    // it just has no echo, so the re-init succeeds and the flag stays.
    if (axis.lastGoodMs != 0 && nowMs - axis.lastGoodMs > cfg::POS_REVIVE_MS &&
        nowMs - axis.lastRestartMs > cfg::POS_REVIVE_MS) {
      axis.lastRestartMs = nowMs;
      if (!tof.restart()) found = false;
    }
    return;
  }
  axis.push(tof.lastMm());
  axis.lastGoodMs = nowMs;
  const uint16_t mm = axis.median();
  const int32_t band = cfg::POS_DEADBAND_MM;
  const int32_t delta = static_cast<int32_t>(mm) - static_cast<int32_t>(axis.heldMm);
  if (axis.heldMm == 0) {
    axis.heldMm = mm;
  } else if (delta > band) {
    axis.heldMm = static_cast<uint16_t>(mm - band);
  } else if (delta < -band) {
    axis.heldMm = static_cast<uint16_t>(mm + band);
  }
  axis.filter.update(normalise(axis.heldMm));
}

void PositionSensor::update(uint32_t nowMs) {
  if ((!foundX_ || !foundY_) && nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
    lastRetryMs_ = nowMs;
    bringUp();
  }
  if (nowMs - lastPollMs_ < 1000 / cfg::SLOW_HZ) return;
  lastPollMs_ = nowMs;
  if (foundX_) feed(axisX_, tofX_, foundX_, nowMs);
  if (foundY_) feed(axisY_, tofY_, foundY_, nowMs);
}

void PositionSensor::fill(InputFrame& frame) {
  const uint32_t now = millis();
  // Whichever module ends up driving screen X is reported as tiltX/distanceMm,
  // so the debug panel keeps matching what the tool actually does.
  const PositionAxis& ax = cfg::POS_SWAP_AXES ? axisY_ : axisX_;
  const PositionAxis& ay = cfg::POS_SWAP_AXES ? axisX_ : axisY_;
  frame.tiltX = ax.filter.value();
  frame.tiltY = ay.filter.value();
  // Report 0 mm while an axis has no fresh echo, so the panel says so instead
  // of showing a stale number next to a tool that silently stopped following.
  frame.distanceMm = ax.stale(now) ? 0 : ax.heldMm;
  frame.distanceYMm = ay.stale(now) ? 0 : ay.heldMm;
  // The status bits follow the same swap, so each panel row reports the sensor
  // that actually drives that screen axis.
  const bool okX = cfg::POS_SWAP_AXES ? foundY_ : foundX_;
  const bool okY = cfg::POS_SWAP_AXES ? foundX_ : foundY_;
  if (okX) frame.sensorsOk |= InputFrame::TOF_X;
  if (okY) frame.sensorsOk |= InputFrame::TOF_Y;
  if (collision_) frame.sensorsOk |= InputFrame::TOF_CLASH;
  if (foundX_ && foundY_) frame.sensorsOk |= InputFrame::DISTANCE;
}

}  // namespace sh
