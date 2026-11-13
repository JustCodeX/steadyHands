#include "KnobInput.h"

namespace sh {

bool KnobInput::begin() {
  found_ = knob_.begin();
  if (found_) knob_.set(0);
  return found_;
}

void KnobInput::update(uint32_t nowMs) {
  if (!found_) {
    if (nowMs - lastRetryMs_ >= cfg::RETRY_MS) {
      lastRetryMs_ = nowMs;
      begin();
    }
    return;
  }
  if (nowMs - lastPollMs_ < 1000 / cfg::SLOW_HZ) return;
  lastPollMs_ = nowMs;
  // isPressed() reads the module and caches the button state; get() reads again.
  pressed_ = knob_.isPressed();
  position_ = knob_.get();
}

void KnobInput::fill(InputFrame& frame) {
  frame.knob = position_;
  if (pressed_) frame.buttons |= InputFrame::KNOB;
  if (found_) frame.sensorsOk |= InputFrame::KNOB_OK;
}

}  // namespace sh
