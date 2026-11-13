// Interface for every hardware part of the firmware.
#pragma once
#include <stdint.h>

namespace sh {

class Module {
public:
  virtual ~Module() = default;
  // Short name for logs.
  virtual const char* name() const = 0;
  // Initialise hardware. Returns false if the part was not found; the firmware
  // keeps running and the module may retry later.
  virtual bool begin() = 0;
  // Called on every loop pass with the current time in milliseconds.
  virtual void update(uint32_t nowMs) = 0;
  // True while the part is working.
  virtual bool ok() const { return true; }
};

}  // namespace sh
