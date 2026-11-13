#include "ButtonPanel.h"

namespace sh {

bool ButtonPanel::begin() {
  found_ = buttons_.begin();
  if (found_) setLeds(ledMask_);
  return found_;
}

void ButtonPanel::update(uint32_t nowMs) {
  if (!found_) {
    if (nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
      lastRetryMs_ = nowMs;
      begin();
    }
    return;
  }
  if (nowMs - lastPollMs_ < 1000 / cfg::SLOW_HZ) return;
  lastPollMs_ = nowMs;
  buttons_.update();
  uint8_t m = 0;
  if (buttons_.isPressed(0)) m |= InputFrame::A;
  if (buttons_.isPressed(1)) m |= InputFrame::B;
  if (buttons_.isPressed(2)) m |= InputFrame::C;
  mask_ = m;
}

void ButtonPanel::setLeds(uint8_t mask) {
  ledMask_ = mask & 0x07;
  if (!found_) return;
  buttons_.setLeds(ledMask_ & 1, (ledMask_ >> 1) & 1, (ledMask_ >> 2) & 1);
}

void ButtonPanel::fill(InputFrame& frame) {
  frame.buttons |= mask_;
  if (found_) frame.sensorsOk |= InputFrame::BUTTONS;
}

}  // namespace sh
