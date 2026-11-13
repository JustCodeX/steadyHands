#include "Firmware.h"

namespace sh {

bool Firmware::add(Module& module) {
  if (count_ >= kMaxModules) return false;
  modules_[count_++] = &module;
  return true;
}

size_t Firmware::begin() {
  size_t ok = 0;
  for (size_t i = 0; i < count_; ++i) {
    if (modules_[i]->begin()) ++ok;
  }
  return ok;
}

void Firmware::update(uint32_t nowMs) {
  for (size_t i = 0; i < count_; ++i) {
    modules_[i]->update(nowMs);
  }
}

}  // namespace sh
