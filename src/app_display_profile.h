#pragma once

#include <optional>
#include <string>
#include <boost/property_tree/ptree.hpp>

#include "display_device/parsed_config.h"

namespace app_display {
  enum class target_e { physical, virtual_display };
  enum class mode_e { inherit, keep, client };
  enum class hdr_e { inherit, keep, client, on, off };

  struct profile_t {
    target_e target {target_e::physical};
    std::string output_name;
    std::optional<display_device::parsed_config_t::device_prep_e> topology;
    mode_e resolution_mode {mode_e::inherit};
    mode_e refresh_mode {mode_e::inherit};
    std::optional<display_device::resolution_t> resolution;
    std::optional<display_device::refresh_rate_t> refresh_rate;
    hdr_e hdr {hdr_e::inherit};
    std::optional<bool> restore_on_disconnect;
    std::optional<bool> dynamic_follow_display;

    bool overrides_resolution() const { return resolution || resolution_mode != mode_e::inherit; }
    bool overrides_refresh() const { return refresh_rate || refresh_mode != mode_e::inherit; }
  };

  // An absent target disables the entire scheme. Invalid enabled schemes throw.
  std::optional<profile_t> parse(const boost::property_tree::ptree &app);
  bool hdr_compatible(const profile_t &profile, bool stream_hdr, bool synthetic_hdr);
  // Called when the last video session disconnects while the app is still running.
  bool restore_on_disconnect(const std::optional<profile_t> &profile);
}  // namespace app_display
