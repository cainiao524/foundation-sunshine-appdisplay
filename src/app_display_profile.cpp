#include "app_display_profile.h"

#include <charconv>
#include <numeric>
#include <stdexcept>
#include <string_view>
#include <boost/algorithm/string/trim.hpp>

namespace app_display {
  namespace {
    std::string field(const boost::property_tree::ptree &app, const char *key) {
      return boost::algorithm::trim_copy(app.get<std::string>(key, ""));
    }

    unsigned int positive(std::string_view text, unsigned int maximum) {
      unsigned int result = 0;
      const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
      if (text.empty() || error != std::errc {} || end != text.data() + text.size() || result == 0 || result > maximum) {
        throw std::invalid_argument("Invalid app display numeric value: " + std::string(text));
      }
      return result;
    }

    mode_e mode(const std::string &value) {
      if (value.empty()) return mode_e::inherit;
      if (value == "no_operation") return mode_e::keep;
      if (value == "client") return mode_e::client;
      throw std::invalid_argument("Invalid app display mode: " + value);
    }
  }

  std::optional<profile_t> parse(const boost::property_tree::ptree &app) {
    const auto target = field(app, "display-target");
    if (target.empty()) return std::nullopt;
    profile_t result;
    if (target == "physical") result.target = target_e::physical;
    else if (target == "virtual") result.target = target_e::virtual_display;
    else throw std::invalid_argument("Invalid display-target: " + target);

    using prep = display_device::parsed_config_t::device_prep_e;
    const auto topology = field(app, "display-device-prep");
    if (topology == "no_operation") result.topology = prep::no_operation;
    else if (topology == "ensure_active") result.topology = prep::ensure_active;
    else if (topology == "ensure_primary") result.topology = prep::ensure_primary;
    else if (topology == "ensure_secondary") result.topology = prep::ensure_secondary;
    else if (topology == "ensure_only_display") result.topology = prep::ensure_only_display;
    else if (!topology.empty()) throw std::invalid_argument("Invalid display-device-prep: " + topology);

    result.resolution_mode = mode(field(app, "display-resolution-mode"));
    result.refresh_mode = mode(field(app, "display-refresh-rate-mode"));
    const auto resolution = field(app, "display-resolution");
    if (!resolution.empty()) {
      const auto separator = resolution.find('x');
      if (separator == std::string::npos) throw std::invalid_argument("Invalid display-resolution: " + resolution);
      result.resolution = display_device::resolution_t {
        positive(std::string_view(resolution).substr(0, separator), 16384),
        positive(std::string_view(resolution).substr(separator + 1), 16384)};
    }
    const auto refresh = field(app, "display-refresh-rate");
    if (!refresh.empty()) {
      const auto dot = refresh.find('.');
      unsigned int denominator = 1;
      std::string digits = refresh;
      if (dot != std::string::npos) {
        const auto places = refresh.size() - dot - 1;
        if (dot == 0 || places == 0 || places > 6) throw std::invalid_argument("Invalid display-refresh-rate: " + refresh);
        digits.erase(dot, 1);
        for (size_t i = 0; i < places; ++i) denominator *= 10;
      }
      const auto numerator = positive(digits, 1000 * denominator);
      const auto divisor = std::gcd(numerator, denominator);
      result.refresh_rate = display_device::refresh_rate_t {numerator / divisor, denominator / divisor};
    }
    const auto hdr = field(app, "display-hdr");
    if (hdr == "on") result.hdr = hdr_e::on;
    else if (hdr == "off") result.hdr = hdr_e::off;
    else if (hdr == "client") result.hdr = hdr_e::client;
    else if (hdr == "no_operation") result.hdr = hdr_e::keep;
    else if (!hdr.empty()) throw std::invalid_argument("Invalid display-hdr: " + hdr);

    if (result.target == target_e::physical) result.output_name = field(app, "display-output-name");
    const auto disconnect = field(app, "display-disconnect-action");
    if (disconnect == "keep") result.restore_on_disconnect = false;
    else if (disconnect == "restore") result.restore_on_disconnect = true;
    else if (!disconnect.empty()) throw std::invalid_argument("Invalid display-disconnect-action: " + disconnect);
    const auto dynamic = field(app, "display-dynamic-resolution-follow-display");
    if (dynamic == "enabled") result.dynamic_follow_display = true;
    else if (dynamic == "disabled") result.dynamic_follow_display = false;
    else if (!dynamic.empty()) throw std::invalid_argument("Invalid display-dynamic-resolution-follow-display: " + dynamic);
    return result;
  }

  bool hdr_compatible(const profile_t &profile, bool stream_hdr, bool synthetic_hdr) {
    return !(profile.hdr == hdr_e::on && synthetic_hdr) &&
           !(profile.hdr == hdr_e::off && stream_hdr && !synthetic_hdr);
  }

  bool restore_on_disconnect(const std::optional<profile_t> &profile) {
    return profile && profile->restore_on_disconnect.value_or(false);
  }
}  // namespace app_display
