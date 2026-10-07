#include "../tests_common.h"
#include "src/app_display_profile.h"
#include "src/config.h"
#include "src/process.h"
#include "src/rtsp.h"

namespace {
  rtsp_stream::launch_session_t launch() {
    rtsp_stream::launch_session_t session {};
    session.width = 1920;
    session.height = 1080;
    session.fps = 60;
    session.enable_sops = true;
    session.custom_screen_mode = -1;
    session.use_vdd = true;
    return session;
  }
  app_display::profile_t profile(const char *key, const char *value) {
    boost::property_tree::ptree node;
    node.put("display-target", "virtual");
    node.put(key, value);
    return *app_display::parse(node);
  }
}

TEST(AppDisplayIntegration, FixedModesOverrideGlobalManualAndPreserveClientViewport) {
  auto video = config::video;
  video.resolution_change = 2;
  video.manual_resolution = "1280x720";
  video.refresh_rate_change = 2;
  video.manual_refresh_rate = "30";
  auto session = launch();
  session.app_display_profile = profile("display-resolution", "2560x1440");
  session.app_display_profile->refresh_rate = display_device::refresh_rate_t {2997, 50};
  const auto result = display_device::make_parsed_config(video, session, true);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->resolution);
  EXPECT_EQ(result->resolution->width, 2560);
  EXPECT_EQ(result->refresh_rate->numerator, 2997);
  EXPECT_EQ(result->refresh_rate->denominator, 50);
  EXPECT_EQ(session.width, 1920);
  EXPECT_EQ(session.fps, 60);
}

TEST(AppDisplayIntegration, ClientModeOverridesGlobalNoOperation) {
  auto video = config::video;
  video.resolution_change = 0;
  video.refresh_rate_change = 0;
  auto session = launch();
  session.enable_sops = false;
  session.app_display_profile = profile("display-resolution-mode", "client");
  session.app_display_profile->refresh_mode = app_display::mode_e::client;
  const auto result = display_device::make_parsed_config(video, session, true);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->resolution);
  ASSERT_TRUE(result->refresh_rate);
  EXPECT_EQ(result->resolution->width, 1920);
  EXPECT_EQ(result->refresh_rate->numerator, 60);
}

TEST(AppDisplayIntegration, KeepRefreshLeavesGlobalResolutionIndependent) {
  auto video = config::video;
  video.resolution_change = 2;
  video.manual_resolution = "1280x720";
  video.refresh_rate_change = 1;
  auto session = launch();
  session.app_display_profile = profile("display-refresh-rate-mode", "no_operation");
  const auto result = display_device::make_parsed_config(video, session, true);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->resolution);
  EXPECT_EQ(result->resolution->width, 1280);
  EXPECT_FALSE(result->refresh_rate);
}

TEST(AppDisplayIntegration, NoProfilePreservesGlobalManualModes) {
  auto video = config::video;
  video.resolution_change = 2;
  video.manual_resolution = "1280x720";
  video.refresh_rate_change = 2;
  video.manual_refresh_rate = "59.94";
  const auto result = display_device::make_parsed_config(video, launch(), true);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->resolution);
  ASSERT_TRUE(result->refresh_rate);
  EXPECT_EQ(result->resolution->width, 1280);
  EXPECT_NEAR(double(result->refresh_rate->numerator) / result->refresh_rate->denominator, 59.94, 0.0001);
}

TEST(AppDisplayIntegration, ResumeWithZeroModeKeepsUpstreamModeGuard) {
  auto video = config::video;
  auto session = launch();
  session.width = 0;
  session.height = 0;
  session.fps = 0;
  session.app_display_profile = profile("display-resolution-mode", "client");
  const auto result = display_device::make_parsed_config(video, session, false);
  ASSERT_TRUE(result);
  EXPECT_FALSE(result->resolution);
  EXPECT_FALSE(result->refresh_rate);
}

TEST(AppDisplayIntegration, ResumeWithZeroModeStillAppliesFixedAppModes) {
  auto video = config::video;
  auto session = launch();
  session.width = 0;
  session.height = 0;
  session.fps = 0;
  session.app_display_profile = profile("display-resolution", "2560x1440");
  session.app_display_profile->refresh_rate = display_device::refresh_rate_t {2997, 50};
  const auto result = display_device::make_parsed_config(video, session, false);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->resolution);
  ASSERT_TRUE(result->refresh_rate);
  EXPECT_EQ(result->resolution->width, 2560);
  EXPECT_EQ(result->refresh_rate->numerator, 2997);
  EXPECT_EQ(result->refresh_rate->denominator, 50);
}

TEST(AppDisplayIntegration, HdrOverrideRemainsStableAfterPipelineResolution) {
  auto video = config::video;
  video.hdr_prep = 0;
  auto session = launch();
  session.app_display_profile = profile("display-hdr", "off");
  session.enable_hdr = true;
  session.synthetic_hdr.enabled = true;
  session.frame_pipeline_policy_resolved = true;
  session.frame_pipeline_policy.source_display = platf::source_display_intent_e::require_sdr;
  const auto result = display_device::make_parsed_config(video, session, true);
  ASSERT_TRUE(result);
  ASSERT_TRUE(result->change_hdr_state);
  EXPECT_FALSE(*result->change_hdr_state);
  session.synthetic_hdr.enabled = false;
  EXPECT_FALSE(display_device::make_parsed_config(video, session, true));
}

TEST(AppDisplayIntegration, SessionSnapshotSurvivesAppListReplacement) {
  proc::proc_t processes {boost::process::v1::environment {}, std::vector<proc::ctx_t> {}};
  proc::ctx_t app {};
  app.id = "7";
  app.display_profile = profile("display-resolution", "2560x1440");
  processes.set_apps({app});
  auto session = launch();
  session.env["SUNSHINE_CLIENT_DISPLAY_NAME"] = "client-display";
  ASSERT_TRUE(processes.apply_app_display_profile(7, session));
  EXPECT_EQ(session.env.find("SUNSHINE_CLIENT_DISPLAY_NAME"), session.env.end());
  EXPECT_EQ(session.env["SUNSHINE_CLIENT_USE_VDD"].to_string(), "true");
  processes.set_apps({});
  ASSERT_TRUE(session.app_display_profile);
  EXPECT_EQ(session.app_display_profile->resolution->width, 2560);
}
