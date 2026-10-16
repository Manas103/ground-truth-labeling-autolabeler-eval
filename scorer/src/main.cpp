// scorer_cli: temporal-IoU-plus-agent-pair-identity matcher that scores a
// predicted event log against a ground-truth event log.
//
// Subcommands:
//   score <ground_truth.tsv> <predicted.tsv> [iou_threshold=0.3]
//     Per-class precision/recall at one threshold, plus the overall
//     (micro-averaged) precision/recall across all classes.
//   sweep <ground_truth.tsv> <predicted.tsv> [thresholds_csv]
//     Overall recall at each threshold in thresholds_csv (default
//     "0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9"): this is the "match threshold
//     alone moves reported recall" measurement.
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "scorer/matcher.hpp"
#include "scorer/types.hpp"

namespace {

std::vector<double> parse_thresholds(const std::string& csv) {
    std::vector<double> out;
    std::istringstream ss(csv);
    std::string tok;
    while (std::getline(ss, tok, ',')) out.push_back(std::stod(tok));
    return out;
}

int cmd_score(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: scorer_cli score <ground_truth.tsv> <predicted.tsv> [iou_threshold=0.3]\n";
        return 2;
    }
    auto gt = scorer::read_events_tsv_file(argv[2]);
    auto pred = scorer::read_events_tsv_file(argv[3]);
    double threshold = argc > 4 ? std::stod(argv[4]) : 0.3;

    scorer::ScoreResult result = scorer::score(gt, pred, threshold);

    std::cout << std::fixed << std::setprecision(4);
    std::cout << "iou_threshold=" << threshold << "\n";
    for (const auto& [cls, stats] : result.per_class) {
        std::cout << cls << ": precision=" << stats.precision() << " recall=" << stats.recall()
                   << " tp=" << stats.tp << " fp=" << stats.fp << " fn=" << stats.fn << "\n";
    }
    scorer::ClassStats overall = result.overall();
    std::cout << "OVERALL: precision=" << overall.precision() << " recall=" << overall.recall()
               << " tp=" << overall.tp << " fp=" << overall.fp << " fn=" << overall.fn << "\n";
    return 0;
}

int cmd_sweep(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: scorer_cli sweep <ground_truth.tsv> <predicted.tsv> [thresholds_csv]\n";
        return 2;
    }
    auto gt = scorer::read_events_tsv_file(argv[2]);
    auto pred = scorer::read_events_tsv_file(argv[3]);
    std::vector<double> thresholds =
        argc > 4 ? parse_thresholds(argv[4]) : parse_thresholds("0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9");

    std::cout << std::fixed << std::setprecision(4);
    double min_recall = 1.0, max_recall = 0.0;
    for (double t : thresholds) {
        scorer::ScoreResult result = scorer::score(gt, pred, t);
        scorer::ClassStats overall = result.overall();
        std::cout << "threshold=" << t << " overall_recall=" << overall.recall()
                   << " overall_precision=" << overall.precision() << "\n";
        min_recall = std::min(min_recall, overall.recall());
        max_recall = std::max(max_recall, overall.recall());
    }
    std::cout << "RECALL_SWING_POINTS=" << (max_recall - min_recall) * 100.0 << "\n";
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: scorer_cli <score|sweep> ...\n";
        return 2;
    }
    std::string cmd = argv[1];
    if (cmd == "score") return cmd_score(argc, argv);
    if (cmd == "sweep") return cmd_sweep(argc, argv);
    std::cerr << "unknown subcommand: " << cmd << "\n";
    return 2;
}
