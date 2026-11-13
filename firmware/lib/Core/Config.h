// Every tunable of the firmware in one place. Pins follow WIRING.md.
#pragma once
#include <stdint.h>

namespace sh {
namespace cfg {

// --- Pins (UNO Q header numbering) ---
constexpr uint8_t PIN_RED_LED = 6;  // D6 via 330 ohm
constexpr uint8_t PIN_HORN = 10;    // D10 via NPN driver

// --- Horn ---
// false: active buzzer, switched on/off. true: passive piezo, driven with tone().
constexpr bool HORN_PASSIVE = false;
constexpr uint16_t HORN_TONE_HZ = 2000;
constexpr uint16_t ALARM_MAX_MS = 3000;  // ignore longer requests (safety)

// --- On-board RGB LED 4 for the voice state ---
// Set to true if the colours look inverted (LED on when it should be off).
constexpr bool RGB_ACTIVE_LOW = false;
constexpr uint16_t RGB_PULSE_MS = 400;  // blink half-period while listening

// --- Rates ---
constexpr uint16_t SENSOR_HZ = 100;  // IMU sampling
constexpr uint16_t FRAME_HZ = 50;    // frames to Linux
constexpr uint16_t SLOW_HZ = 50;     // knob, buttons, distance polling
constexpr uint32_t RETRY_MS = 2000;  // retry missing Modulinos this often

// --- Tilt filter ---
constexpr float TILT_CUTOFF_HZ = 5.0f;
constexpr float TILT_CLAMP_G = 1.0f;

// --- I2C ---
constexpr uint32_t I2C_CLOCK_HZ = 400000;  // lower to 100000 if the long cable causes errors

// --- Bridge method names (must match app/trainer/hardware/mcu_link.py) ---
constexpr const char* RPC_INPUT = "input";
constexpr const char* RPC_ALARM = "alarm";
constexpr const char* RPC_LEDS = "leds";
constexpr const char* RPC_VOICE_STATE = "voice_state";
constexpr const char* RPC_PING = "ping";
constexpr const char* RPC_STATUS = "status";

}  // namespace cfg
}  // namespace sh
