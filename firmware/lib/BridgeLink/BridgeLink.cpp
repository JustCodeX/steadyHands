#include "BridgeLink.h"

namespace sh {

BridgeLink* BridgeLink::instance_ = nullptr;

bool BridgeLink::addSource(InputSource& source) {
  if (sourceCount_ >= kMaxSources) return false;
  sources_[sourceCount_++] = &source;
  return true;
}

bool BridgeLink::begin() {
  instance_ = this;
  started_ = Bridge.begin();
  if (!started_) return false;
  Bridge.provide_safe(cfg::RPC_LEDS, rpcLeds);
  Bridge.provide_safe(cfg::RPC_VOICE_STATE, rpcVoiceState);
  Bridge.provide_safe(cfg::RPC_PING, rpcPing);
  Bridge.provide_safe(cfg::RPC_STATUS, rpcStatus);
  return true;
}

void BridgeLink::collect(InputFrame& frame) {
  frame = InputFrame{};
  for (size_t i = 0; i < sourceCount_; ++i) sources_[i]->fill(frame);
}

void BridgeLink::sendFrame() {
  collect(frame_);
  ++seq_;
  Bridge.notify(cfg::RPC_INPUT, frame_.tiltX, frame_.tiltY, static_cast<int>(frame_.knob),
                static_cast<int>(frame_.buttons), static_cast<int>(frame_.distanceMm),
                static_cast<int>(frame_.sensorsOk), static_cast<int>(seq_));
}

void BridgeLink::update(uint32_t nowMs) {
  if (!started_) return;
  if (nowMs - lastFrameMs_ < frameIntervalMs_) return;
  lastFrameMs_ = nowMs;
  sendFrame();
}

bool BridgeLink::rpcLeds(int mask) {
  if (!instance_) return false;
  instance_->buttons_.setLeds(static_cast<uint8_t>(mask & 0x07));
  return true;
}

bool BridgeLink::rpcVoiceState(int state) {
  if (!instance_ || state < 0 || state > 3) return false;
  instance_->statusLed_.show(static_cast<VoiceState>(state));
  return true;
}

int BridgeLink::rpcPing() { return static_cast<int>(millis()); }

// Bit mask of sensors that currently answer, same bits as InputFrame::Sensors.
int BridgeLink::rpcStatus() {
  if (!instance_) return 0;
  InputFrame f;
  instance_->collect(f);
  return f.sensorsOk;
}

}  // namespace sh
