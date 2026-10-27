#include <gtest/gtest.h>
#include "src/app_display_profile.h"

namespace {
  boost::property_tree::ptree app() {
    boost::property_tree::ptree node;
    node.put("display-target", "virtual");
    return node;
  }
}

TEST(AppDisplayProfile, NoTargetPreservesUpstreamAndIgnoresStaleFields) {
  boost::property_tree::ptree node;
  node.put("display-resolution", "invalid");
  EXPECT_FALSE(app_display::parse(node));
}

TEST(AppDisplayProfile, FixedRefreshPreservesFraction) {
  auto node = app();
  node.put("display-resolution", "2560x1440");
  node.put("display-refresh-rate", "59.94");
  const auto profile = app_display::parse(node);
  ASSERT_TRUE(profile);
  EXPECT_EQ(profile->resolution->width, 2560);
  EXPECT_EQ(profile->refresh_rate->numerator, 2997);
  EXPECT_EQ(profile->refresh_rate->denominator, 50);
}

TEST(AppDisplayProfile, TopologyCanReturnToInheritanceWithoutChangingOtherPolicies) {
  auto node = app();
  node.put("display-resolution", "2560x1440");
  EXPECT_FALSE(app_display::parse(node)->topology);
  node.put("display-device-prep", "ensure_only_display");
  EXPECT_EQ(app_display::parse(node)->topology, display_device::parsed_config_t::device_prep_e::ensure_only_display);
  node.put("display-device-prep", "");
  const auto inherited = app_display::parse(node);
  EXPECT_FALSE(inherited->topology);
  ASSERT_TRUE(inherited->resolution);
  EXPECT_EQ(inherited->resolution->width, 2560);
}

TEST(AppDisplayProfile, RejectsMalformedOrOutOfRangeModes) {
  for (const auto *value : {"1920x1080junk", "0x1080", "16385x1080", "1920X1080"}) {
    auto node = app();
    node.put("display-resolution", value);
    EXPECT_THROW(app_display::parse(node), std::invalid_argument) << value;
  }
  for (const auto *value : {"60junk", "59.94.1", "0", "1001", "60.", "1.1234567"}) {
    auto node = app();
    node.put("display-refresh-rate", value);
    EXPECT_THROW(app_display::parse(node), std::invalid_argument) << value;
  }
}

TEST(AppDisplayProfile, RejectsUnknownEnabledPolicies) {
  for (const auto *key : {"display-target", "display-device-prep", "display-resolution-mode", "display-refresh-rate-mode",
                          "display-hdr", "display-disconnect-action", "display-dynamic-resolution-follow-display"}) {
    auto node = app();
    node.put(key, "invalid");
    EXPECT_THROW(app_display::parse(node), std::invalid_argument) << key;
  }
}

TEST(AppDisplayProfile, RefreshKeepDoesNotChangeResolutionPolicy) {
  auto node = app();
  node.put("display-refresh-rate-mode", "no_operation");
  const auto profile = app_display::parse(node);
  EXPECT_EQ(profile->resolution_mode, app_display::mode_e::inherit);
  EXPECT_EQ(profile->refresh_mode, app_display::mode_e::keep);
}

TEST(AppDisplayProfile, DisconnectAndDynamicPoliciesAreOptional) {
  auto node = app();
  EXPECT_FALSE(app_display::parse(node)->restore_on_disconnect.has_value());
  EXPECT_FALSE(app_display::parse(node)->dynamic_follow_display.has_value());
  node.put("display-disconnect-action", "restore");
  node.put("display-dynamic-resolution-follow-display", "disabled");
  const auto profile = app_display::parse(node);
  EXPECT_TRUE(app_display::restore_on_disconnect(profile));
  EXPECT_FALSE(*profile->dynamic_follow_display);
  EXPECT_FALSE(app_display::restore_on_disconnect(std::nullopt));
  node.put("display-disconnect-action", "keep");
  EXPECT_FALSE(app_display::restore_on_disconnect(app_display::parse(node)));
}

TEST(AppDisplayProfile, HdrRejectsIncompatibleSources) {
  auto node = app();
  node.put("display-hdr", "off");
  const auto off = *app_display::parse(node);
  EXPECT_FALSE(app_display::hdr_compatible(off, true, false));
  EXPECT_TRUE(app_display::hdr_compatible(off, true, true));
  EXPECT_TRUE(app_display::hdr_compatible(off, false, false));
  node.put("display-hdr", "on");
  const auto on = *app_display::parse(node);
  EXPECT_FALSE(app_display::hdr_compatible(on, true, true));
  EXPECT_TRUE(app_display::hdr_compatible(on, true, false));
}
