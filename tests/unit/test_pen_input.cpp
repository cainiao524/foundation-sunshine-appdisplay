/**
 * @file tests/unit/test_pen_input.cpp
 * @brief Pen protocol, queue batching, and barrel-roll compatibility tests.
 */
#include <gtest/gtest.h>

#include <src/config.h>
#include <src/input.h>
#include <src/pen_protocol.h>

#include <cstring>
#include <vector>

namespace {
  // Construct the reference wire format byte by byte so the tests also check
  // field offsets and byte order, independently of the host packet struct.
  std::vector<std::uint8_t>
  pen_packet(std::uint16_t azimuth, std::uint16_t roll, bool extended = true,
             std::uint8_t event = LI_TOUCH_EVENT_MOVE) {
    std::vector<std::uint8_t> bytes {
      0, 0, 0, static_cast<std::uint8_t>(extended ? 34 : 32),
      static_cast<std::uint8_t>(extended ? 0x0B : 0x03), 0, 0, 0x55,
      event, LI_TOOL_TYPE_PEN, 0, 0,
      0, 0, 0x80, 0x3E,  // x = 0.25
      0, 0, 0x40, 0x3F,  // y = 0.75
      0, 0, 0x00, 0x3F,  // pressure = 0.5
      static_cast<std::uint8_t>(azimuth), static_cast<std::uint8_t>(azimuth >> 8),
      45, 0,              // tilt = 45 degrees
      0, 0, 0, 0,         // contact area major
      0, 0, 0, 0,         // contact area minor
    };
    if (extended) {
      bytes.push_back(static_cast<std::uint8_t>(roll));
      bytes.push_back(static_cast<std::uint8_t>(roll >> 8));
    }
    return bytes;
  }

  class PenInputTest: public ::testing::Test {
  protected:
    void
    SetUp() override {
      original_mouse = config::input.mouse;
      config::input.mouse = true;
      context = input::testing::make_input();
      input::testing::set_pen_sink([this](const platf::pen_input_t &pen) {
        events.push_back(pen);
      });
    }

    void
    TearDown() override {
      input::testing::set_pen_sink({});
      config::input.mouse = original_mouse;
    }

    void
    process(const std::vector<std::vector<std::uint8_t>> &packets) {
      input::touch_port_t port {{0, 0, 1920, 1080}, 1920, 1080, 1920, 1080, 0, 0, 1};
      input::testing::process_packets(context, port, packets);
    }

    bool original_mouse;
    std::shared_ptr<input::input_t> context;
    std::vector<platf::pen_input_t> events;
  };
}  // namespace

TEST_F(PenInputTest, DecodesRollSeparatelyFromTiltAndPressure) {
  process({pen_packet(90, 270)});
  ASSERT_EQ(events.size(), 1u);
  const auto &pen = events.front();
  EXPECT_EQ(pen.rotation, 90);
  EXPECT_EQ(pen.barrelRoll, 270);
  EXPECT_EQ(pen.tilt, 45);
  EXPECT_FLOAT_EQ(pen.pressureOrDistance, 0.5f);
  EXPECT_FLOAT_EQ(pen.x, 0.25f);
  EXPECT_FLOAT_EQ(pen.y, 0.75f);
}

TEST_F(PenInputTest, PreservesLegacyAndUnknownRollFallback) {
  process({pen_packet(80, 123, false), pen_packet(100, LI_ROT_UNKNOWN),
           pen_packet(LI_ROT_UNKNOWN, LI_ROT_UNKNOWN), pen_packet(120, 0),
           pen_packet(LI_ROT_UNKNOWN, 315)});
  ASSERT_EQ(events.size(), 5u);
  EXPECT_EQ(events[0].barrelRoll, 80);
  EXPECT_EQ(events[1].barrelRoll, 100);
  EXPECT_EQ(events[2].rotation, LI_ROT_UNKNOWN);
  EXPECT_EQ(events[2].barrelRoll, LI_ROT_UNKNOWN);
  EXPECT_EQ(events[3].barrelRoll, 0);
  EXPECT_EQ(events[4].barrelRoll, 315);
  EXPECT_EQ(events[4].rotation, LI_ROT_UNKNOWN);
}

TEST_F(PenInputTest, NormalizesAnglesWithoutChangingUnknownSentinel) {
  process({pen_packet(450, 720), pen_packet(65534, 65534)});
  ASSERT_EQ(events.size(), 2u);
  EXPECT_EQ(events[0].rotation, 90);
  EXPECT_EQ(events[0].barrelRoll, 0);
  EXPECT_EQ(events[1].rotation, 14);
  EXPECT_EQ(events[1].barrelRoll, 14);
}

TEST_F(PenInputTest, BatchesHoverIncludingLatestRoll) {
  process({pen_packet(10, 20, true, LI_TOUCH_EVENT_HOVER),
           pen_packet(30, 310, true, LI_TOUCH_EVENT_HOVER)});
  ASSERT_EQ(events.size(), 1u);
  EXPECT_EQ(events[0].rotation, 30);
  EXPECT_EQ(events[0].barrelRoll, 310);
}

TEST_F(PenInputTest, PreservesEveryContactSampleAndEdge) {
  process({pen_packet(10, 0, true, LI_TOUCH_EVENT_DOWN), pen_packet(10, 30),
           pen_packet(10, 60), pen_packet(10, 90, true, LI_TOUCH_EVENT_UP),
           pen_packet(10, 100, true, LI_TOUCH_EVENT_HOVER_LEAVE),
           pen_packet(10, 110, true, LI_TOUCH_EVENT_CANCEL_ALL)});
  ASSERT_EQ(events.size(), 6u);
  EXPECT_EQ(events[0].eventType, LI_TOUCH_EVENT_DOWN);
  EXPECT_EQ(events[1].barrelRoll, 30);
  EXPECT_EQ(events[2].barrelRoll, 60);
  EXPECT_EQ(events[3].eventType, LI_TOUCH_EVENT_UP);
  EXPECT_EQ(events[4].eventType, LI_TOUCH_EVENT_HOVER_LEAVE);
  EXPECT_EQ(events[5].eventType, LI_TOUCH_EVENT_CANCEL_ALL);
}

TEST_F(PenInputTest, DoesNotBatchAcrossButtonsToolsOrPacketFormats) {
  auto first = pen_packet(10, 20, true, LI_TOUCH_EVENT_HOVER);
  auto button = first;
  button[10] = LI_PEN_BUTTON_PRIMARY;
  auto eraser = button;
  eraser[9] = LI_TOOL_TYPE_ERASER;
  auto legacy = pen_packet(40, 50, false, LI_TOUCH_EVENT_HOVER);
  process({first, button, eraser, legacy});
  ASSERT_EQ(events.size(), 4u);
  EXPECT_EQ(events[1].penButtons, LI_PEN_BUTTON_PRIMARY);
  EXPECT_EQ(events[2].toolType, LI_TOOL_TYPE_ERASER);
  EXPECT_EQ(events[3].barrelRoll, 40);
}

TEST_F(PenInputTest, RejectsTruncatedPacketsBeforeLoggingBatchingOrDispatch) {
  std::vector<std::vector<std::uint8_t>> packets;
  for (bool extended : {false, true}) {
    const auto complete = pen_packet(10, 20, extended, LI_TOUCH_EVENT_HOVER);
    for (std::size_t size = 0; size < complete.size(); ++size) {
      packets.emplace_back(complete.begin(), complete.begin() + size);
    }
  }
  // A valid queued hover must survive malformed neighbors on both sides.
  packets.insert(packets.begin() + 10, pen_packet(30, 300, true, LI_TOUCH_EVENT_HOVER));
  process(packets);
  ASSERT_EQ(events.size(), 1u);
  EXPECT_EQ(events[0].barrelRoll, 300);
}

TEST_F(PenInputTest, HonorsMouseInputToggleForBothFormats) {
  config::input.mouse = false;
  process({pen_packet(10, 20), pen_packet(30, 40, false)});
  EXPECT_TRUE(events.empty());
}
