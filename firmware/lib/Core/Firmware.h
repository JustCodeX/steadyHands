// Owns the list of modules and drives them.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "Module.h"

namespace sh {

class Firmware {
public:
  static constexpr size_t kMaxModules = 12;

  // Returns false when the list is full.
  bool add(Module& module);
  // Calls begin() on every module. Returns the number that reported ok.
  size_t begin();
  // Calls update() on every module.
  void update(uint32_t nowMs);

  size_t count() const { return count_; }
  Module* at(size_t i) const { return i < count_ ? modules_[i] : nullptr; }

private:
  Module* modules_[kMaxModules] = {};
  size_t count_ = 0;
};

}  // namespace sh
