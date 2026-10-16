#include <gtest/gtest.h>

#include "scorer/matcher.hpp"

using namespace scorer;

namespace {
Event ev(std::uint32_t seg, std::uint32_t a, std::uint32_t b, std::string cls, int start, int end) {
    Event e;
    e.segment_id = seg;
    e.agent_a = a;
    e.agent_b = b;
    e.event_class = std::move(cls);
    e.start_step = start;
    e.end_step = end;
    return e;
}
} // namespace

TEST(TemporalIou, IdenticalIntervalsIsOne) {
    EXPECT_DOUBLE_EQ(temporal_iou(10, 20, 10, 20), 1.0);
}

TEST(TemporalIou, DisjointIntervalsIsZero) {
    EXPECT_DOUBLE_EQ(temporal_iou(0, 10, 20, 30), 0.0);
}

TEST(TemporalIou, PartialOverlap) {
    // intersection [10,20) len 10, union [0,30) len 30 -> 1/3
    EXPECT_NEAR(temporal_iou(0, 20, 10, 30), 10.0 / 30.0, 1e-9);
}

TEST(Score, ExactMatchIsTruePositive) {
    std::vector<Event> gt = {ev(1, 5, 5, "lane_change", 100, 140)};
    std::vector<Event> pred = {ev(1, 5, 5, "lane_change", 100, 140)};
    ScoreResult r = score(gt, pred, 0.5);
    EXPECT_EQ(r.per_class["lane_change"].tp, 1);
    EXPECT_EQ(r.per_class["lane_change"].fp, 0);
    EXPECT_EQ(r.per_class["lane_change"].fn, 0);
}

TEST(Score, MissedGroundTruthIsFalseNegative) {
    std::vector<Event> gt = {ev(1, 5, 5, "hard_brake", 100, 140)};
    std::vector<Event> pred = {};
    ScoreResult r = score(gt, pred, 0.5);
    EXPECT_EQ(r.per_class["hard_brake"].tp, 0);
    EXPECT_EQ(r.per_class["hard_brake"].fn, 1);
}

TEST(Score, SpuriousPredictionIsFalsePositive) {
    std::vector<Event> gt = {};
    std::vector<Event> pred = {ev(1, 5, 5, "hard_brake", 100, 140)};
    ScoreResult r = score(gt, pred, 0.5);
    EXPECT_EQ(r.per_class["hard_brake"].fp, 1);
}

TEST(Score, AgentPairOrderDoesNotMatter) {
    std::vector<Event> gt = {ev(1, 5, 9, "crossing_paths", 100, 140)};
    std::vector<Event> pred = {ev(1, 9, 5, "crossing_paths", 100, 140)}; // swapped a/b
    ScoreResult r = score(gt, pred, 0.5);
    EXPECT_EQ(r.per_class["crossing_paths"].tp, 1);
}

TEST(Score, DifferentSegmentsDoNotMatch) {
    std::vector<Event> gt = {ev(1, 5, 5, "merge", 100, 140)};
    std::vector<Event> pred = {ev(2, 5, 5, "merge", 100, 140)};
    ScoreResult r = score(gt, pred, 0.5);
    EXPECT_EQ(r.per_class["merge"].tp, 0);
    EXPECT_EQ(r.per_class["merge"].fn, 1);
    EXPECT_EQ(r.per_class["merge"].fp, 1);
}

TEST(Score, LowIouBelowThresholdDoesNotMatch) {
    std::vector<Event> gt = {ev(1, 5, 5, "cut_in", 100, 110)};
    std::vector<Event> pred = {ev(1, 5, 5, "cut_in", 108, 200)}; // intersection=2, union=100, iou=0.02
    ScoreResult low = score(gt, pred, 0.01);
    ScoreResult high = score(gt, pred, 0.5);
    EXPECT_EQ(low.per_class["cut_in"].tp, 1);
    EXPECT_EQ(high.per_class["cut_in"].tp, 0);
}

TEST(Score, HigherThresholdNeverIncreasesRecall) {
    std::vector<Event> gt = {ev(1, 1, 1, "lane_change", 0, 10), ev(1, 2, 2, "lane_change", 0, 10)};
    std::vector<Event> pred = {ev(1, 1, 1, "lane_change", 0, 10), ev(1, 2, 2, "lane_change", 3, 10)};
    double prev_recall = 1.0;
    for (double t : {0.1, 0.3, 0.5, 0.7, 0.9}) {
        ScoreResult r = score(gt, pred, t);
        double recall = r.overall().recall();
        EXPECT_LE(recall, prev_recall + 1e-9);
        prev_recall = recall;
    }
}

TEST(Score, GreedyMatchingPrefersHigherIouPairing) {
    // Two ground truth, two predicted; one predicted overlaps both but
    // much better with the second. Greedy-by-IoU should not starve the
    // better match by taking the first ground truth first.
    std::vector<Event> gt = {ev(1, 1, 1, "close_proximity", 0, 20), ev(1, 1, 1, "close_proximity", 100, 120)};
    std::vector<Event> pred = {ev(1, 1, 1, "close_proximity", 95, 125)};
    ScoreResult r = score(gt, pred, 0.3);
    EXPECT_EQ(r.per_class["close_proximity"].tp, 1);
    EXPECT_EQ(r.per_class["close_proximity"].fn, 1);
}
