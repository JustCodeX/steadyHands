// MCU <-> Linux link over the Arduino Router Bridge (msgpack-RPC).
//
//   MCU -> Linux   notify "input"(tiltX, tiltY, knob, buttons, distanceMm, sensorsOk, seq)
//   Linux -> MCU   "leds"(mask) -> bool, "voice_state"(state) -> bool,
//                  "ping"() -> int, "status"() -> int
//
// Handlers are registered with provide_safe, so they run between loop()
// passes in the main thread and may touch the modules directly.
#pragma once
#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include "ButtonPanel.h"
#include "Config.h"
#include "InputFrame.h"
#include "InputSource.h"
#include "Module.h"
#include "StatusLed.h"

namespace sh {

class BridgeLink : public Module {
public:
  static constexpr size_t kMaxSources = 8;

  BridgeLink(ButtonPanel& buttons, StatusLed& statusLed, uint16_t frameHz)
      : buttons_(buttons), statusLed_(statusLed), frameIntervalMs_(1000 / frameHz) {}

  const char* name() const override { return "bridge"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return started_; }

  bool addSource(InputSource& source);
  // Fills a frame from all sources (also used by tests and status).
  void collect(InputFrame& frame);
  void sendFrame();
  uint32_t framesSent() const { return seq_; }
  const InputFrame& lastFrame() const { return frame_; }

private:
  // RPC entry points (static: the RPC library stores plain callables).
  static bool rpcLeds(int mask);
  static bool rpcVoiceState(int state);
  static int rpcPing();
  static int rpcStatus();
  static BridgeLink* instance_;

  ButtonPanel& buttons_;
  StatusLed& statusLed_;
  uint32_t frameIntervalMs_;
  InputSource* sources_[kMaxSources] = {};
  size_t sourceCount_ = 0;
  InputFrame frame_;
  uint32_t seq_ = 0;
  uint32_t lastFrameMs_ = 0;
  bool started_ = false;
};

}  // namespace sh
