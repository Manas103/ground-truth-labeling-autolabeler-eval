#pragma once

#include <cstdint>
#include <istream>
#include <string>
#include <vector>

namespace scorer {

struct Event {
    std::uint32_t segment_id = 0;
    std::uint32_t agent_a = 0;
    std::uint32_t agent_b = 0;
    std::string event_class;
    int start_step = 0;
    int end_step = 0;
};

// Reads a TSV with header "segment_id\tagent_a\tagent_b\tevent_class\tstart_step\tend_step",
// the schema both the autolabeler's predicted_events.tsv and the
// collected ground_truth_events.tsv share.
std::vector<Event> read_events_tsv(std::istream& is);
std::vector<Event> read_events_tsv_file(const std::string& path);

} // namespace scorer
