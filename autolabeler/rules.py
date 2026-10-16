"""The autolabeler under evaluation: a compact, independently-written
rule-based event miner over the generator's agent tracks. This is not
radar-plot-to-track-processor's autolabel/ extension vendored in; it is a
fresh, smaller implementation built for this repo, because what this
project evaluates is the scoring methodology, not a second copy of that
project's throughput-optimized miner. It runs brute force (no grid
prefilter: segments here are a few dozen agents for 450 steps, trivial at
that scale) and is deliberately simple enough to have real, uneven
precision and recall rather than being tuned to any target number.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generator"))
from scenario import pose_at_with_wobble, EVENT_CLASSES, VEHICLE, CYCLIST  # noqa: E402

TH = dict(
    lane_change_min_lateral_m=2.2,
    lane_change_half_window=18,
    hard_brake_decel=3.0,
    high_accel=2.0,
    accel_sustain=8,
    close_proximity_m=6.5,
    cyclist_passing_distance_m=1.4,
    crossing_heading_min_deg=20.0,
    crossing_heading_max_deg=160.0,
    crossing_time_gap_s=1.6,
    crossing_max_lookahead_s=8.0,
    turn_rate_deg_s=7.0,
    oncoming_speed_mps=4.0,
    cut_in_follow_gap_m=12.0,
    cut_in_half_window=20,
    merge_zone=(400.0, 600.0),
)


def heading_diff_deg(ha, hb):
    d = ha - hb
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return abs(d) * 180.0 / math.pi


def lateral(agent, pose):
    return pose[1] if agent.axis == 0 else pose[0]


def longitudinal(agent, pose):
    return pose[0] if agent.axis == 0 else pose[1]


def solve_crossing(pa, pb):
    da = (math.cos(pa[2]), math.sin(pa[2]))
    db = (math.cos(pb[2]), math.sin(pb[2]))
    det = da[0] * (-db[1]) - (-db[0]) * da[1]
    if abs(det) < 1e-6:
        return None
    rhs = (pb[0] - pa[0], pb[1] - pa[1])
    s = (rhs[0] * (-db[1]) - (-db[0]) * rhs[1]) / det
    u = (da[0] * rhs[1] - da[1] * rhs[0]) / det
    if s < 0 or u < 0:
        return None
    sa, sb = pa[3], pb[3]
    if sa < 1e-3 or sb < 1e-3:
        return None
    ta, tb = s / sa, u / sb
    if ta > TH["crossing_max_lookahead_s"] or tb > TH["crossing_max_lookahead_s"]:
        return None
    return abs(ta - tb), heading_diff_deg(pa[2], pb[2])


def mine_segment(seg):
    """Returns a list of dicts {event_class, agent_a, agent_b, start_step,
    end_step}, merged from raw per-timestep hits (same merge idea as
    radar-plot-to-track-processor's autolabel/, independently coded here:
    sort by key, merge runs within a small gap)."""
    raw = []  # (key, t)
    agents = seg.agents
    n = len(agents)
    poses_by_t = {}

    def pose(a, t):
        key = (a.id, t)
        if key not in poses_by_t:
            poses_by_t[key] = pose_at_with_wobble(a, t, seg.dt_s)
        return poses_by_t[key]

    for t in range(seg.num_steps):
        for a in agents:
            half = TH["lane_change_half_window"]
            t0, t1 = max(0, t - half), t + half
            if abs(lateral(a, pose(a, t1)) - lateral(a, pose(a, t0))) >= TH["lane_change_min_lateral_m"]:
                raw.append(((a.id, a.id, "lane_change"), t0, t1))
                mid_x = pose(a, t)[0]
                if a.axis == 0 and TH["merge_zone"][0] <= mid_x <= TH["merge_zone"][1]:
                    raw.append(((a.id, a.id, "merge"), t0, t1))

            sustain = TH["accel_sustain"]
            s0, s1 = pose(a, t)[3], pose(a, t + sustain)[3]
            accel = (s1 - s0) / (sustain * seg.dt_s)
            if accel <= -TH["hard_brake_decel"]:
                raw.append(((a.id, a.id, "hard_brake"), t, t + sustain))
            if accel >= TH["high_accel"]:
                raw.append(((a.id, a.id, "high_acceleration"), t, t + sustain))

        for i in range(n):
            for j in range(i + 1, n):
                a, b = agents[i], agents[j]
                pa, pb = pose(a, t), pose(b, t)
                dist = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                pair = (min(a.id, b.id), max(a.id, b.id))

                if dist <= TH["close_proximity_m"]:
                    raw.append((pair + ("close_proximity",), t, t + 1))

                sol = solve_crossing(pa, pb)
                if sol is not None:
                    gap, hdiff = sol
                    if gap <= TH["crossing_time_gap_s"] and TH["crossing_heading_min_deg"] <= hdiff <= TH[
                            "crossing_heading_max_deg"]:
                        raw.append((pair + ("crossing_paths",), t - 5, t + 5))
                    if gap <= TH["crossing_time_gap_s"]:
                        half = 5
                        ha0, ha1 = pose(a, max(0, t - half))[2], pose(a, t + half)[2]
                        hb0, hb1 = pose(b, max(0, t - half))[2], pose(b, t + half)[2]
                        rate_a = heading_diff_deg(ha1, ha0) / (2 * half * seg.dt_s)
                        rate_b = heading_diff_deg(hb1, hb0) / (2 * half * seg.dt_s)
                        a_turn, b_turn = rate_a >= TH["turn_rate_deg_s"], rate_b >= TH["turn_rate_deg_s"]
                        if a_turn or b_turn:
                            oncoming = pb[3] if a_turn else pa[3]
                            if oncoming >= TH["oncoming_speed_mps"]:
                                raw.append((pair + ("unprotected_left",), t - half, t + half))

                if a.axis == b.axis:
                    for lead, cutter in ((a, b), (b, a)):
                        half = TH["cut_in_half_window"]
                        t0, t1 = max(0, t - half), t + half
                        pl0, pl1 = pose(lead, t0), pose(lead, t1)
                        pc0, pc1 = pose(cutter, t0), pose(cutter, t1)
                        lat_gap0 = abs(lateral(lead, pl0) - lateral(cutter, pc0))
                        lat_gap1 = abs(lateral(lead, pl1) - lateral(cutter, pc1))
                        diff_lane = max(lead.lane_width, cutter.lane_width) * 0.7
                        if lat_gap0 < diff_lane or lat_gap1 > diff_lane * 0.35:
                            continue
                        gap1 = longitudinal(cutter, pc1) - longitudinal(lead, pl1)
                        if 0.0 < gap1 <= TH["cut_in_follow_gap_m"]:
                            raw.append((pair + ("cut_in",), t0, t1))

                if {a.type, b.type} == {VEHICLE, CYCLIST}:
                    vehicle, cyclist = (a, b) if a.type == VEHICLE else (b, a)
                    pv, pc = pose(vehicle, t), pose(cyclist, t)
                    wx, wy = pc[0] - pv[0], pc[1] - pv[1]
                    ux, uy = math.cos(pv[2]), math.sin(pv[2])
                    lateral_offset = abs(ux * wy - uy * wx)
                    overall = math.hypot(wx, wy)
                    if overall <= TH["close_proximity_m"] * 1.4 and lateral_offset <= TH[
                            "cyclist_passing_distance_m"]:
                        raw.append((pair + ("cyclist_vehicle_close_approach",), t - 5, t + 5))

    raw.sort(key=lambda r: (r[0], r[1]))
    merged = []
    gap_tolerance = 8
    # close_proximity is the one predicate here that is genuinely
    # continuous-by-construction (two cruisers holding a steady gap stay
    # "close" for the whole segment, not just for a maneuver's duration).
    # Capping only this class's merge length is what keeps it from
    # reporting one segment-spanning blob instead of discrete
    # close-approach moments; the other eight classes are bounded by their
    # own detection window already (a lane shift, a brake pulse, a
    # crossing) and capping them too just chops one real maneuver into
    # several false positives against a single ground-truth label, which
    # a first attempt at this fix did, and is why the cap is class-scoped.
    max_close_proximity_span_steps = 30
    for key, start, end in raw:
        cap = max_close_proximity_span_steps if key[2] == "close_proximity" else None
        if (merged and merged[-1][0] == key and start <= merged[-1][2] + gap_tolerance and
                (cap is None or end - merged[-1][1] <= cap)):
            merged[-1] = (key, merged[-1][1], max(merged[-1][2], end))
        else:
            merged.append((key, max(0, start), end))

    out = []
    for key, start, end in merged:
        agent_a, agent_b, event_class = key
        out.append(dict(event_class=event_class, agent_a=agent_a, agent_b=agent_b, start_step=start,
                         end_step=end))
    return out
