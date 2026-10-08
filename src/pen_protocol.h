/**
 * @file src/pen_protocol.h
 * @brief Backward-compatible pen barrel-roll extension used by Sunshine 1005 clients.
 */
#pragma once

#include <cstddef>
#include <cstdint>

#include <moonlight-common-c/src/Input.h>
#include <moonlight-common-c/src/Limelight.h>

namespace input::pen_protocol {
  constexpr std::uint32_t barrel_magic = 0x5500000B;

  // The legacy 36-byte pen packet stays intact. The extension appends a
  // little-endian uint16 angle; rotation in the base packet remains azimuth.
  // Keep this host extension separate from the pinned protocol submodule.
#pragma pack(push, 1)
  struct barrel_packet_t {
    SS_PEN_PACKET pen;
    std::uint16_t barrelRoll;
  };
#pragma pack(pop)

  static_assert(sizeof(SS_PEN_PACKET) == 36);
  static_assert(offsetof(barrel_packet_t, barrelRoll) == 36);
  static_assert(sizeof(barrel_packet_t) == 38);

  constexpr std::uint16_t
  normalize_angle(std::uint16_t angle) {
    return angle == LI_ROT_UNKNOWN ? angle : angle % 360;
  }

  constexpr std::uint16_t
  effective_barrel_roll(std::uint16_t azimuth, std::uint16_t barrel_roll) {
    // Match the reference host: legacy clients and unknown roll keep the
    // previous Windows rotation behavior, while an explicit zero is valid.
    return normalize_angle(barrel_roll == LI_ROT_UNKNOWN ? azimuth : barrel_roll);
  }
}  // namespace input::pen_protocol
