#include <gtest/gtest.h>

#include <sstream>

#include "scorer/types.hpp"

using namespace scorer;

TEST(ReadEventsTsv, ParsesHeaderAndRows) {
    std::istringstream ss(
        "segment_id\tagent_a\tagent_b\tevent_class\tstart_step\tend_step\n"
        "1\t5\t6\tlane_change\t100\t140\n"
        "2\t9\t9\thard_brake\t10\t20\n");
    std::vector<Event> events = read_events_tsv(ss);
    ASSERT_EQ(events.size(), 2u);
    EXPECT_EQ(events[0].segment_id, 1u);
    EXPECT_EQ(events[0].agent_a, 5u);
    EXPECT_EQ(events[0].agent_b, 6u);
    EXPECT_EQ(events[0].event_class, "lane_change");
    EXPECT_EQ(events[0].start_step, 100);
    EXPECT_EQ(events[0].end_step, 140);
    EXPECT_EQ(events[1].event_class, "hard_brake");
}

TEST(ReadEventsTsv, EmptyBodyProducesNoEvents) {
    std::istringstream ss("segment_id\tagent_a\tagent_b\tevent_class\tstart_step\tend_step\n");
    EXPECT_TRUE(read_events_tsv(ss).empty());
}
