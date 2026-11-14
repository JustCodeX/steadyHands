// Every tunable of the firmware in one place.
#pragma once
#include <stdint.h>

namespace sh {
namespace cfg {

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

// --- Control mode ---
// 0 = tilt (original, board flat, tip to move)
// 1 = motion (board upright, leaky-velocity from the accelerometer)
// 2 = position (two Modulino Distance against two perpendicular walls;
//     needs the app config game.input_mode = "position")
//
// Two boards run this firmware: the game board (buttons, knob, tilt) and the
// hand-held remote (the two distance sensors). Build the remote's image with
//   PLATFORMIO_BUILD_FLAGS=-DSH_CONTROL_MODE=2 tools/board.sh upload
// so the same source serves both and neither can get the other's behaviour.
#ifndef SH_CONTROL_MODE
#define SH_CONTROL_MODE 0
#endif
constexpr uint8_t CONTROL_MODE = SH_CONTROL_MODE;

// --- Position control (CONTROL_MODE 2) ---
// Both Modulino Distance modules hang on the Qwiic chain and ship fixed to
// 0x29, so they have to be told apart. Preferred, with no wiring at all: a
// Modulino Hub (TCA9548A) in the chain gives each module its own channel and
// both keep 0x29. Detected at run time.
constexpr uint8_t POS_HUB_ADDR = 0x70;  // hub default; jumpers allow 0x70-0x77
constexpr uint8_t POS_HUB_CH_X = 0;     // hub port for the left-wall sensor
constexpr uint8_t POS_HUB_CH_Y = 1;     // hub port for the top-wall sensor
// Works with nothing but the stock Qwiic chain: whichever module is alone on
// 0x29 first gets moved to POS_ADDR_X, so plugging the second one in a few
// seconds later finds 0x29 free. See PositionSensor for the sequence.
constexpr uint8_t POS_ADDR_X = 0x2A;  // first module parks here (left wall)
// Fallback with a wire: the X module's XSHUT pad on this pin removes the need
// to plug the modules in one after the other.
constexpr bool POS_USE_XSHUT = false;  // true once the XSHUT wire is fitted
constexpr uint8_t PIN_TOF_XSHUT = 4;   // D4 -> XSHUT pad of the X module
constexpr uint16_t POS_MIN_MM = 40;   // maps to the left/top edge
constexpr uint16_t POS_MAX_MM = 400;  // maps to the right/bottom edge
// true when the module aimed at the left wall is the one on 0x29, i.e. when
// screen X and screen Y come out the wrong way round.
constexpr bool POS_SWAP_AXES = true;
// The chips are accurate but noisy by a few mm. A median of POS_MEDIAN samples
// kills single spikes, and the held position trails the reading by
// POS_DEADBAND_MM, so the tool sits perfectly still between moves.
constexpr uint8_t POS_MEDIAN = 5;
constexpr uint16_t POS_DEADBAND_MM = 6;
constexpr float POS_CUTOFF_HZ = 6.0f;  // output smoothing
// No valid echo for this long (hand out of range, beam missing the wall) is
// reported as "no reading" instead of silently holding the last position.
constexpr uint32_t POS_STALE_MS = 800;
// A sensor that answers but has stopped ranging gets its init redone.
constexpr uint32_t POS_REVIVE_MS = 2500;

// --- Motion control (CONTROL_MODE 1) ---
// The frame still carries the result in tiltX/tiltY, so the app is unchanged.
constexpr bool MOTION_CONTROL = (CONTROL_MODE == 1);
constexpr float MOTION_GRAVITY_CUTOFF_HZ = 0.3f;  // gravity tracker: slow, survives shakes
constexpr float MOTION_DEADZONE_G = 0.03f;        // ignores hand tremor and sensor noise
// The horizontal acceleration is integrated into a leaky velocity: the point
// moves while the hand moves and stays when it stops (the braking impulse
// cancels the velocity, not the position). The leak bleeds any residue to zero.
constexpr float MOTION_LEAK_TAU_S = 0.5f;         // residual velocity halves in ~0.35 s
constexpr float MOTION_FULL_SPEED_MPS = 0.4f;     // hand speed for full deflection
constexpr float MOTION_DIR_X = 1.0f;              // -1 flips the axis
constexpr float MOTION_DIR_Y = 1.0f;

// --- I2C ---
// 100 kHz: the ToF sensors garble register reads at 400 kHz over the long
// Qwiic cable (model id came back 0xE8AA instead of 0xEBAA, measured 13 Nov).
constexpr uint32_t I2C_CLOCK_HZ = 100000;

// --- Bridge method names (must match app/trainer/hardware/mcu_link.py) ---
constexpr const char* RPC_INPUT = "input";
constexpr const char* RPC_LEDS = "leds";
constexpr const char* RPC_VOICE_STATE = "voice_state";
constexpr const char* RPC_PING = "ping";
constexpr const char* RPC_STATUS = "status";

}  // namespace cfg
}  // namespace sh
