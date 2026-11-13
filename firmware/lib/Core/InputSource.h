// A module that contributes values to the InputFrame.
#pragma once
#include "InputFrame.h"
#include "Module.h"

namespace sh {

class InputSource : public Module {
public:
  // Write this module's latest values into the frame.
  virtual void fill(InputFrame& frame) = 0;
};

}  // namespace sh
