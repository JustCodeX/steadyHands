// Host tests for the pure parts of the firmware: LowPassFilter and InputFrame.
#include <unity.h>

#include "Firmware.h"
#include "InputFrame.h"
#include "InputSource.h"
#include "LowPassFilter.h"

using sh::InputFrame;
using sh::LowPassFilter;

void setUp() {}
void tearDown() {}

void test_filter_first_sample_passes_through() {
  LowPassFilter f(5.0f, 100.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.7f, f.update(0.7f));
}

void test_filter_converges_to_step() {
  LowPassFilter f(5.0f, 100.0f);
  f.update(0.0f);
  float y = 0.0f;
  for (int i = 0; i < 200; ++i) y = f.update(1.0f);  // 2 s at 100 Hz
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.0f, y);
}

void test_filter_smooths_jitter() {
  LowPassFilter f(5.0f, 100.0f);
  f.update(0.0f);
  float maxAbs = 0.0f;
  for (int i = 0; i < 100; ++i) {
    float y = f.update((i % 2) ? 1.0f : -1.0f);  // 50 Hz square wave
    if (y > maxAbs) maxAbs = y;
    if (-y > maxAbs) maxAbs = -y;
  }
  TEST_ASSERT_TRUE(maxAbs < 0.3f);
}

void test_alpha_in_range() {
  TEST_ASSERT_TRUE(LowPassFilter::alphaFor(5.0f, 100.0f) > 0.0f);
  TEST_ASSERT_TRUE(LowPassFilter::alphaFor(5.0f, 100.0f) < 1.0f);
  TEST_ASSERT_EQUAL_FLOAT(1.0f, LowPassFilter::alphaFor(0.0f, 100.0f));
}

class FakeSource : public sh::InputSource {
public:
  const char* name() const override { return "fake"; }
  bool begin() override { begun = true; return true; }
  void update(uint32_t nowMs) override { lastNow = nowMs; }
  void fill(InputFrame& frame) override {
    frame.buttons |= InputFrame::A;
    frame.sensorsOk |= InputFrame::BUTTONS;
  }
  bool begun = false;
  uint32_t lastNow = 0;
};

void test_firmware_runs_modules() {
  sh::Firmware fw;
  FakeSource a, b;
  TEST_ASSERT_TRUE(fw.add(a));
  TEST_ASSERT_TRUE(fw.add(b));
  TEST_ASSERT_EQUAL(2, fw.begin());
  fw.update(123);
  TEST_ASSERT_TRUE(a.begun && b.begun);
  TEST_ASSERT_EQUAL_UINT32(123, b.lastNow);
}

void test_frame_bits_combine() {
  InputFrame frame;
  FakeSource a;
  a.fill(frame);
  frame.buttons |= InputFrame::KNOB;
  TEST_ASSERT_EQUAL_HEX8(InputFrame::A | InputFrame::KNOB, frame.buttons);
  TEST_ASSERT_EQUAL_HEX8(InputFrame::BUTTONS, frame.sensorsOk);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_filter_first_sample_passes_through);
  RUN_TEST(test_filter_converges_to_step);
  RUN_TEST(test_filter_smooths_jitter);
  RUN_TEST(test_alpha_in_range);
  RUN_TEST(test_firmware_runs_modules);
  RUN_TEST(test_frame_bits_combine);
  return UNITY_END();
}
