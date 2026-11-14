// One Modulino Distance (VL53L4CD or the newer VL53L4ED) on a given I2C bus.
//
// Both chip generations ship fixed to address 0x29, so two of them on one bus
// answer every byte together (the wired-AND of 0xEBAA and 0xECAA reads back as
// 0xE8AA — that is how this was diagnosed). To run a pair on the same Qwiic
// chain, one module's XSHUT pad is pulled low while the other is moved to a
// free address; see PositionSensor. The address change is volatile, so the
// firmware redoes it on every boot.
#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <vl53l4cd_class.h>
#include <vl53l4ed_class.h>

namespace sh {

// The ST drivers keep their I2C address in a protected member and always start
// from the 0x29 default. A sensor this firmware already moved to another
// address can only be reached by setting it first, hence these two shims.
class ToFCD : public VL53L4CD {
public:
  explicit ToFCD(TwoWire* wire) : VL53L4CD(wire, -1) {}
  void useAddress(uint8_t addr7) { dev = static_cast<uint16_t>(addr7) << 1; }
};

class ToFED : public VL53L4ED {
public:
  explicit ToFED(TwoWire* wire) : VL53L4ED(wire, -1) {}
  // The ED driver calls its copy "address" (and stores it shifted, like the CD).
  void useAddress(uint8_t addr7) { address = static_cast<uint8_t>(addr7 << 1); }
};

class ToFReader {
public:
  static constexpr uint16_t ID_CD = 0xEBAA;
  static constexpr uint16_t ID_ED = 0xECAA;

  // xshutPin < 0: module has no shutdown wire (always powered).
  ToFReader(TwoWire& wire, int xshutPin = -1) : wire_(wire), xshut_(xshutPin) {}

  // Route every transfer through one channel of a Modulino Hub (TCA9548A).
  // With a hub both modules may keep address 0x29: the mux isolates them.
  void useHub(uint8_t hubAddr, int channel) {
    hubAddr_ = hubAddr;
    channel_ = channel;
  }

  void selectChannel() {
    if (channel_ < 0) return;
    wire_.beginTransmission(hubAddr_);
    wire_.write((uint8_t)(1 << channel_));
    wire_.endTransmission();
  }

  // Reads the identification register (0x010F) at the 7-bit address. 0xEBAA or
  // 0xECAA means exactly one healthy chip answers; anything else means no chip
  // or two chips corrupting each other.
  uint16_t modelId(uint8_t addr7 = 0x29) {
    selectChannel();
    wire_.beginTransmission(addr7);
    wire_.write((uint8_t)0x01);
    wire_.write((uint8_t)0x0F);
    if (wire_.endTransmission() != 0) return 0;
    const size_t got = wire_.requestFrom(addr7, (size_t)2);
    uint16_t id = 0;
    for (size_t i = 0; i < got && wire_.available(); ++i) id = (id << 8) | (uint8_t)wire_.read();
    return id;
  }

  void powerOff() {
    if (xshut_ < 0) return;
    pinMode(xshut_, OUTPUT);
    digitalWrite(xshut_, LOW);
  }

  // The module pulls XSHUT up to 3V3 itself, so releasing the pin powers it on.
  void powerOn() {
    if (xshut_ < 0) return;
    pinMode(xshut_, INPUT);
    delay(10);  // the chip needs ~2 ms to boot before it answers
  }

  // Brings the sensor up and leaves it at `addr7`. Picks the driver from the
  // model id, so a CD and an ED module can sit on the same chain.
  bool begin(uint8_t addr7, uint8_t currentAddr7 = 0x29) {
    release();
    selectChannel();
    lastId_ = modelId(currentAddr7);
    if (lastId_ == ID_CD) {
      cd_ = new ToFCD(&wire_);
      cd_->useAddress(currentAddr7);
      if (cd_->InitSensor(addr7 << 1) != VL53L4CD_ERROR_NONE) return release();
      cd_->VL53L4CD_SetRangeTiming(20, 0);
      cd_->VL53L4CD_StartRanging();
    } else if (lastId_ == ID_ED) {
      ed_ = new ToFED(&wire_);
      ed_->useAddress(currentAddr7);
      if (ed_->InitSensor(addr7 << 1) != VL53L4ED_ERROR_NONE) return release();
      ed_->VL53L4ED_SetRangeTiming(20, 0);
      ed_->VL53L4ED_StartRanging();
    } else {
      return false;  // nothing there, or two chips fighting over 0x29
    }
    addr7_ = addr7;
    started_ = true;
    return true;
  }

  // Ranging can stop without the chip dropping off the bus — a hot-plug glitch
  // on the chain is enough. Re-running init from the address it already has
  // brings it back without touching the other sensor.
  bool restart() { return addr7_ != 0 && begin(addr7_, addr7_); }

  bool started() const { return started_; }
  uint16_t lastId() const { return lastId_; }

  // True when a fresh, valid sample arrived; read it with lastMm().
  bool poll() {
    if (!started_) return false;
    selectChannel();
    uint8_t ready = 0;
    if (cd_ != nullptr) {
      if (cd_->VL53L4CD_CheckForDataReady(&ready) != VL53L4CD_ERROR_NONE || !ready) return false;
      VL53L4CD_Result_t r;
      cd_->VL53L4CD_ClearInterrupt();
      cd_->VL53L4CD_GetResult(&r);
      if (r.range_status != 0) return false;
      lastMm_ = r.distance_mm;
      return true;
    }
    if (ed_ == nullptr) return false;
    if (ed_->VL53L4ED_CheckForDataReady(&ready) != VL53L4ED_ERROR_NONE || !ready) return false;
    VL53L4ED_ResultsData_t r;
    ed_->VL53L4ED_ClearInterrupt();
    ed_->VL53L4ED_GetResult(&r);
    if (r.range_status != 0) return false;
    lastMm_ = r.distance_mm;
    return true;
  }

  uint16_t lastMm() const { return lastMm_; }

private:
  bool release() {
    delete cd_;
    cd_ = nullptr;
    delete ed_;
    ed_ = nullptr;
    started_ = false;
    return false;
  }

  TwoWire& wire_;
  int xshut_;
  uint8_t hubAddr_ = 0x70;
  int channel_ = -1;
  ToFCD* cd_ = nullptr;
  ToFED* ed_ = nullptr;
  uint16_t lastMm_ = 0;
  uint16_t lastId_ = 0;
  uint8_t addr7_ = 0;
  bool started_ = false;
};

}  // namespace sh
