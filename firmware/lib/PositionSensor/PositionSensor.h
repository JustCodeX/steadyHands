// Absolute 2D position from two Modulino Distance sensors aimed at two
// perpendicular walls (CONTROL_MODE 2). Both sit on the Qwiic chain, so the
// instrument stays free to move; they are told apart by pulling sensor X's
// XSHUT pad low during start-up (PIN_TOF_XSHUT) while sensor Y is moved to
// POS_ADDR_Y. The distances are normalised to POS_MIN_MM..POS_MAX_MM and sent
// as tiltX/tiltY in -1..+1, so the frame format stays unchanged; the app's
// game.input_mode = "position" maps them onto the play field.
#pragma once
#include "Config.h"
#include "InputFrame.h"
#include "InputSource.h"
#include "LowPassFilter.h"
#include "ToFReader.h"

namespace sh {

class PositionSensor : public InputSource {
public:
  PositionSensor()
      : tofX_(Wire1, cfg::PIN_TOF_XSHUT),
        tofY_(Wire1),
        filterX_(cfg::POS_CUTOFF_HZ, cfg::SLOW_HZ),
        filterY_(cfg::POS_CUTOFF_HZ, cfg::SLOW_HZ) {}

  const char* name() const override { return "position"; }
  bool begin() override;
  void update(uint32_t nowMs) override;
  bool ok() const override { return foundX_ && foundY_; }
  void fill(InputFrame& frame) override;

  bool foundX() const { return foundX_; }
  bool foundY() const { return foundY_; }
  bool viaHub() const { return hub_; }
  bool clash() const { return collision_; }
  uint16_t idX() const { return tofX_.lastId(); }
  uint16_t idY() const { return tofY_.lastId(); }

private:
  static float normalise(uint16_t mm);
  static bool healthy(uint16_t modelId);
  bool haveXshutWire() const;
  void bringUp();

  ToFReader tofX_;
  ToFReader tofY_;
  LowPassFilter filterX_;
  LowPassFilter filterY_;
  bool foundX_ = false;
  bool foundY_ = false;
  bool hub_ = false;
  bool collision_ = false;
  uint16_t lastXMm_ = 0;
  uint16_t lastYMm_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
