#include "scorer/matcher.hpp"

#include <algorithm>
#include <tuple>

namespace scorer {

double temporal_iou(int start1, int end1, int start2, int end2) {
    const int inter_start = std::max(start1, start2);
    const int inter_end = std::min(end1, end2);
    const int intersection = std::max(0, inter_end - inter_start);
    if (intersection == 0) return 0.0;
    const int union_len = std::max(end1, end2) - std::min(start1, start2);
    if (union_len <= 0) return 0.0;
    return static_cast<double>(intersection) / static_cast<double>(union_len);
}

ClassStats ScoreResult::overall() const {
    ClassStats total;
    for (const auto& [cls, stats] : per_class) {
        total.tp += stats.tp;
        total.fp += stats.fp;
        total.fn += stats.fn;
    }
    return total;
}

namespace {

using Key = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t, std::string>; // segment, pair-min, pair-max, class

Key key_of(const Event& e) {
    return {e.segment_id, std::min(e.agent_a, e.agent_b), std::max(e.agent_a, e.agent_b), e.event_class};
}

} // namespace

ScoreResult score(const std::vector<Event>& ground_truth, const std::vector<Event>& predicted,
                   double iou_threshold) {
    std::map<Key, std::vector<const Event*>> gt_groups, pred_groups;
    for (const Event& e : ground_truth) gt_groups[key_of(e)].push_back(&e);
    for (const Event& e : predicted) pred_groups[key_of(e)].push_back(&e);

    std::map<std::string, ClassStats> per_class;

    std::map<Key, std::vector<const Event*>> all_keys = gt_groups;
    for (const auto& [k, v] : pred_groups) all_keys[k]; // ensure predicted-only keys exist too

    for (const auto& [key, _] : all_keys) {
        const std::string& cls = std::get<3>(key);
        std::vector<const Event*> gts = gt_groups.count(key) ? gt_groups[key] : std::vector<const Event*>{};
        std::vector<const Event*> preds = pred_groups.count(key) ? pred_groups[key] : std::vector<const Event*>{};

        std::vector<bool> gt_used(gts.size(), false), pred_used(preds.size(), false);

        // Greedy highest-IoU-first assignment over this (small) group.
        std::vector<std::tuple<double, std::size_t, std::size_t>> candidates;
        for (std::size_t i = 0; i < gts.size(); ++i) {
            for (std::size_t j = 0; j < preds.size(); ++j) {
                double iou = temporal_iou(gts[i]->start_step, gts[i]->end_step, preds[j]->start_step,
                                           preds[j]->end_step);
                if (iou >= iou_threshold) candidates.emplace_back(iou, i, j);
            }
        }
        std::sort(candidates.begin(), candidates.end(),
                  [](const auto& x, const auto& y) { return std::get<0>(x) > std::get<0>(y); });

        int tp = 0;
        for (const auto& [iou, i, j] : candidates) {
            if (gt_used[i] || pred_used[j]) continue;
            gt_used[i] = pred_used[j] = true;
            tp++;
        }
        int fn = 0, fp = 0;
        for (bool used : gt_used) fn += !used;
        for (bool used : pred_used) fp += !used;

        ClassStats& stats = per_class[cls];
        stats.tp += tp;
        stats.fn += fn;
        stats.fp += fp;
    }

    ScoreResult result;
    result.per_class = per_class;
    return result;
}

} // namespace scorer
