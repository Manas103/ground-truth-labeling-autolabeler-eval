#pragma once

#include <map>
#include <string>
#include <vector>

#include "scorer/types.hpp"

namespace scorer {

// Temporal intersection-over-union of two [start, end] step intervals.
// 0.0 when they do not overlap at all.
double temporal_iou(int start1, int end1, int start2, int end2);

struct ClassStats {
    int tp = 0;
    int fp = 0;
    int fn = 0;

    double precision() const { return (tp + fp) == 0 ? 0.0 : static_cast<double>(tp) / (tp + fp); }
    double recall() const { return (tp + fn) == 0 ? 0.0 : static_cast<double>(tp) / (tp + fn); }
};

struct ScoreResult {
    std::map<std::string, ClassStats> per_class;
    ClassStats overall() const;
};

// Matches ground_truth against predicted within each (segment, unordered
// agent pair, event class) group: greedy highest-IoU-first assignment,
// a pair counts as matched only if their temporal IoU is at least
// iou_threshold. Unmatched ground truth is a false negative (missed
// event); unmatched predicted is a false positive.
ScoreResult score(const std::vector<Event>& ground_truth, const std::vector<Event>& predicted,
                   double iou_threshold);

} // namespace scorer
