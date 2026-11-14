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

// One axis: raw samples in, a steady held distance out. The median rejects
// single bad readings, the deadband rejects sensor noise, and the low-pass
// smooths the step the deadband lets through.
struct PositionAxis {
  explicit PositionAxis(float cutoffHz, float sampleHz) : filter(cutoffHz, sampleHz) {}

  LowPassFilter filter;
  uint16_t samples[cfg::POS_MEDIAN] = {0};
  uint8_t filled = 0;
  uint8_t next = 0;
  uint16_t heldMm = 0;
  uint32_t lastGoodMs = 0;
  uint32_t lastRestartMs = 0;

  void push(uint16_t mm);
  uint16_t median() const;
  bool stale(uint32_t nowMs) const;
};

class PositionSensor : public InputSource {
public:
  PositionSensor()
      : tofX_(Wire1, cfg::PIN_TOF_XSHUT),
        tofY_(Wire1),
        axisX_(cfg::POS_CUTOFF_HZ, cfg::SLOW_HZ),
        axisY_(cfg::POS_CUTOFF_HZ, cfg::SLOW_HZ) {}

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
  void feed(PositionAxis& axis, ToFReader& tof, uint32_t nowMs);

  ToFReader tofX_;
  ToFReader tofY_;
  PositionAxis axisX_;
  PositionAxis axisY_;
  bool foundX_ = false;
  bool foundY_ = false;
  bool hub_ = false;
  bool collision_ = false;
  uint32_t lastPollMs_ = 0;
  uint32_t lastRetryMs_ = 0;
};

}  // namespace sh
