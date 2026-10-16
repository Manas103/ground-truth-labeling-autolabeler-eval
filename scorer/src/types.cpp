#include "scorer/types.hpp"

#include <fstream>
#include <sstream>

namespace scorer {

std::vector<Event> read_events_tsv(std::istream& is) {
    std::vector<Event> events;
    std::string line;
    std::getline(is, line); // header
    while (std::getline(is, line)) {
        if (line.empty()) continue;
        std::istringstream ss(line);
        Event e;
        std::string field;
        std::getline(ss, field, '\t');
        e.segment_id = static_cast<std::uint32_t>(std::stoul(field));
        std::getline(ss, field, '\t');
        e.agent_a = static_cast<std::uint32_t>(std::stoul(field));
        std::getline(ss, field, '\t');
        e.agent_b = static_cast<std::uint32_t>(std::stoul(field));
        std::getline(ss, e.event_class, '\t');
        std::getline(ss, field, '\t');
        e.start_step = std::stoi(field);
        std::getline(ss, field, '\t');
        e.end_step = std::stoi(field);
        events.push_back(e);
    }
    return events;
}

std::vector<Event> read_events_tsv_file(const std::string& path) {
    std::ifstream f(path);
    return read_events_tsv(f);
}

} // namespace scorer
