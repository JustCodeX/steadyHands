// First-order exponential low-pass filter. Pure C++ so it can be unit tested
// on the host.
#pragma once

namespace sh {

class LowPassFilter {
public:
  // cutoffHz: -3 dB point; sampleHz: how often update() is called.
  LowPassFilter(float cutoffHz, float sampleHz) : alpha_(alphaFor(cutoffHz, sampleHz)) {}

  static float alphaFor(float cutoffHz, float sampleHz) {
    if (cutoffHz <= 0.0f || sampleHz <= 0.0f) return 1.0f;
    // alpha = dt / (RC + dt) with RC = 1 / (2 pi fc)
    const float dt = 1.0f / sampleHz;
    const float rc = 1.0f / (6.2831853f * cutoffHz);
    return dt / (rc + dt);
  }

  float update(float x) {
    if (!primed_) {
      y_ = x;
      primed_ = true;
    } else {
      y_ += alpha_ * (x - y_);
    }
    return y_;
  }

  float value() const { return y_; }
  float alpha() const { return alpha_; }
  void reset() { primed_ = false; y_ = 0.0f; }

private:
  float alpha_;
  float y_ = 0.0f;
  bool primed_ = false;
};

}  // namespace sh
