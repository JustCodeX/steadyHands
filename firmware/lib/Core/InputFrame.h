// One snapshot of every input, sent to Linux at FRAME_HZ.
#pragma once
#include <stdint.h>

namespace sh {

struct InputFrame {
  // Filtered tilt of the instrument in g, about -1..1 on each axis.
  float tiltX = 0.0f;
  float tiltY = 0.0f;
  // Knob position in encoder steps (signed, wraps at int16 limits).
  int16_t knob = 0;
  // Bit mask: see Buttons below.
  uint8_t buttons = 0;
  // Distance to the hand in mm, 0 when no sensor or no reading.
  uint16_t distanceMm = 0;
  // Bit mask of sensors that answered: see Sensors below.
  uint8_t sensorsOk = 0;

  enum Buttons : uint8_t { A = 1 << 0, B = 1 << 1, C = 1 << 2, KNOB = 1 << 3 };
  enum Sensors : uint8_t { TILT = 1 << 0, KNOB_OK = 1 << 1, BUTTONS = 1 << 2, DISTANCE = 1 << 3 };
};

}  // namespace sh
