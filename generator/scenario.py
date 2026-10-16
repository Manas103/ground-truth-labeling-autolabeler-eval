"""Synthetic driving-segment generator.

Independent of (and simpler than) radar-plot-to-track-processor's
autolabel/ extension: that project optimizes for scanning a billion
agent-pair timesteps, this one optimizes for generating 600 short,
reviewable segments with known planted events, each tagged with the
ground truth the review tool and the scorer are evaluated against. No
code is shared between the two; the closed-form kinematics are the
same kind of math because it is the obvious way to do it, not a copy.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict
from typing import Optional

VEHICLE, CYCLIST = "vehicle", "cyclist"

EVENT_CLASSES = [
    "lane_change",
    "crossing_paths",
    "unprotected_left",
    "cut_in",
    "hard_brake",
    "close_proximity",
    "merge",
    "high_acceleration",
    "cyclist_vehicle_close_approach",
]


@dataclass
class LaneChange:
    t_start: int
    t_end: int
    lane_from: int
    lane_to: int


@dataclass
class SpeedPulse:
    t_start: int
    t_end: int
    accel: float


@dataclass
class Agent:
    id: int
    type: str
    axis: int  # 0: travels +x, 1: travels +y
    lane_width: float
    lane_index: int
    base_speed: float
    x0: float
    lane_changes: list = field(default_factory=list)
    speed_pulses: list = field(default_factory=list)


@dataclass
class PlantedEvent:
    event_class: str
    agent_a: int
    agent_b: int
    t_center: int  # the instant a reviewer would naturally scrub to


@dataclass
class Segment:
    segment_id: int
    dt_s: float
    num_steps: int
    agents: list
    planted_events: list  # ground truth, not shown to the autolabeler


def _pulse_velocity_deviation(p: SpeedPulse, dt_s, t_s):
    start_s, end_s = p.t_start * dt_s, p.t_end * dt_s
    if t_s <= start_s or t_s >= end_s:
        return 0.0
    half_s = (end_s - start_s) / 2.0
    mid_s = start_s + half_s
    return p.accel * (t_s - start_s) if t_s <= mid_s else p.accel * (end_s - t_s)


def _pulse_displacement(p: SpeedPulse, dt_s, t_s):
    start_s, end_s = p.t_start * dt_s, p.t_end * dt_s
    if t_s <= start_s:
        return 0.0
    half_s = (end_s - start_s) / 2.0
    mid_s = start_s + half_s
    a = p.accel
    if t_s <= mid_s:
        u = t_s - start_s
        return 0.5 * a * u * u
    if t_s <= end_s:
        w = t_s - mid_s
        return 0.5 * a * half_s * half_s + a * half_s * w - 0.5 * a * w * w
    return a * half_s * half_s


def _lane_lateral(agent: Agent, dt_s, t_s):
    lateral = agent.lane_index * agent.lane_width
    lateral_v = 0.0
    for lc in agent.lane_changes:
        start_s, end_s = lc.t_start * dt_s, lc.t_end * dt_s
        from_y, to_y = lc.lane_from * agent.lane_width, lc.lane_to * agent.lane_width
        if t_s <= start_s:
            continue
        if t_s >= end_s:
            lateral = to_y
            continue
        frac = (t_s - start_s) / (end_s - start_s)
        lateral = from_y + frac * (to_y - from_y)
        lateral_v = (to_y - from_y) / (end_s - start_s)
    return lateral, lateral_v


def pose_at(agent: Agent, t: int, dt_s: float):
    """Returns (x, y, heading_rad, speed_mps). Closed-form: see predicates
    in autolabeler/rules.py and scorer for why this matters (cheap, exact,
    no integration-from-zero cost growth)."""
    t_s = t * dt_s
    dv = sum(_pulse_velocity_deviation(p, dt_s, t_s) for p in agent.speed_pulses)
    disp = sum(_pulse_displacement(p, dt_s, t_s) for p in agent.speed_pulses)
    longitudinal_speed = agent.base_speed + dv
    s = agent.x0 + agent.base_speed * t_s + disp
    lateral, lateral_v = _lane_lateral(agent, dt_s, t_s)
    if agent.axis == 0:
        x, y, vx, vy = s, lateral, longitudinal_speed, lateral_v
    else:
        y, x, vy, vx = s, lateral, longitudinal_speed, lateral_v
    heading = math.atan2(vy, vx)
    speed = math.hypot(vx, vy)
    return x, y, heading, speed


# Cyclists wobble: a small sinusoidal heading/lateral jitter layered on top
# of the closed-form lane position. This is a real geometric property (not
# a thumb on the scale for the eval numbers) that is what makes the
# cyclist_vehicle_close_approach class measurably harder to pin down than
# vehicle-vehicle close_proximity: a tighter passing-distance threshold
# applied to a noisier trajectory.
def cyclist_wobble(agent: Agent, t: int, dt_s: float, amplitude_m: float = 0.25, period_s: float = 2.2):
    t_s = t * dt_s
    return amplitude_m * math.sin(2 * math.pi * t_s / period_s + agent.id)


def pose_at_with_wobble(agent: Agent, t: int, dt_s: float):
    x, y, heading, speed = pose_at(agent, t, dt_s)
    if agent.type == CYCLIST:
        wobble = cyclist_wobble(agent, t, dt_s)
        if agent.axis == 0:
            y += wobble
        else:
            x += wobble
    return x, y, heading, speed


_NEXT_ID = [1]


def _new_id():
    v = _NEXT_ID[0]
    _NEXT_ID[0] += 1
    return v


def _cruiser(axis, lane, speed, x0, agent_type=VEHICLE, lane_width=3.5):
    return Agent(id=_new_id(), type=agent_type, axis=axis, lane_width=lane_width, lane_index=lane,
                 base_speed=speed, x0=x0)


def generate_segment(segment_id: int, seed: int) -> Segment:
    """One ~90s segment with a small cast of agents and 1-3 planted events,
    chosen round-robin-ish by segment_id so all 9 classes appear often
    across a 600-segment corpus, plus a few background cruisers for
    texture and incidental close_proximity noise."""
    rng = random.Random(seed)
    _NEXT_ID[0] = 1
    dt_s = 0.2
    num_steps = 450  # 90s
    agents = []
    planted = []

    # Background: 3-5 cruisers that never trigger anything.
    for i in range(rng.randint(3, 5)):
        agents.append(_cruiser(0, rng.randint(0, 6), 12.0 + rng.uniform(-1.5, 1.5), rng.uniform(-80, 80)))

    primary_class = EVENT_CLASSES[segment_id % len(EVENT_CLASSES)]
    extra_classes = rng.sample([c for c in EVENT_CLASSES if c != primary_class], k=rng.randint(0, 1))
    classes_to_plant = [primary_class] + extra_classes

    for cls in classes_to_plant:
        t_center = rng.randint(150, 300)
        if cls == "lane_change":
            a = _cruiser(0, 5, 14.0, -14.0 * t_center * dt_s)
            a.lane_changes.append(LaneChange(t_center - 20, t_center + 20, 5, 6))
            agents.append(a)
            planted.append(PlantedEvent(cls, a.id, a.id, t_center))
        elif cls == "hard_brake":
            a = _cruiser(0, 7, 16.0, -16.0 * t_center * dt_s)
            a.speed_pulses.append(SpeedPulse(t_center - 20, t_center + 20, -4.0))
            agents.append(a)
            planted.append(PlantedEvent(cls, a.id, a.id, t_center))
        elif cls == "high_acceleration":
            a = _cruiser(0, 8, 9.0, -9.0 * t_center * dt_s)
            a.speed_pulses.append(SpeedPulse(t_center - 20, t_center + 20, 3.0))
            agents.append(a)
            planted.append(PlantedEvent(cls, a.id, a.id, t_center))
        elif cls == "merge":
            a = _cruiser(0, 15, 15.0, 500.0 - 15.0 * t_center * dt_s)
            a.lane_changes.append(LaneChange(t_center - 22, t_center + 22, 15, 14))
            agents.append(a)
            planted.append(PlantedEvent(cls, a.id, a.id, t_center))
        elif cls == "crossing_paths" or cls == "unprotected_left":
            cross_speed = 12.0
            cross = _cruiser(1, 0, cross_speed, -cross_speed * t_center * dt_s)
            agents.append(cross)
            turn_speed = 9.0
            turning = _cruiser(0, 2, turn_speed, -turn_speed * t_center * dt_s)
            if cls == "unprotected_left":
                turning.lane_changes.append(LaneChange(t_center - 15, t_center + 15, 2, -2))
            agents.append(turning)
            planted.append(PlantedEvent(cls, turning.id, cross.id, t_center))
        elif cls == "cut_in":
            lead_speed, cutter_speed = 13.0, 14.3
            lead = _cruiser(0, 10, lead_speed, -lead_speed * t_center * dt_s)
            gap_at_center = 3.0
            cutter_x0 = (lead.x0 + lead_speed * t_center * dt_s + gap_at_center) - cutter_speed * t_center * dt_s
            cutter = _cruiser(0, 11, cutter_speed, cutter_x0)
            cutter.lane_changes.append(LaneChange(t_center - 20, t_center + 20, 11, 10))
            agents.append(lead)
            agents.append(cutter)
            planted.append(PlantedEvent(cls, cutter.id, lead.id, t_center))
        elif cls == "close_proximity":
            # A small relative speed (not equal speeds) is deliberate: two
            # cruisers at identical speed and a fixed offset would be
            # "close" for the entire segment, which is not a close
            # *approach*, it is a permanent formation. The relative speed
            # closes the gap to its minimum right at t_center and opens it
            # back up on both sides, which is what gives this class an
            # actual interval to label and to score against, instead of a
            # 450-step continuous condition.
            base_speed, rel_speed = 14.0, 0.3
            a = _cruiser(0, 13, base_speed, -base_speed * t_center * dt_s)
            b_speed = base_speed + rel_speed
            b_x0 = a.x0 + base_speed * t_center * dt_s - b_speed * t_center * dt_s + 4.0
            b = _cruiser(0, 13, b_speed, b_x0)
            agents.append(a)
            agents.append(b)
            planted.append(PlantedEvent(cls, a.id, b.id, t_center))
        elif cls == "cyclist_vehicle_close_approach":
            cyclist = _cruiser(0, 18, 5.0, -5.0 * t_center * dt_s, agent_type=CYCLIST, lane_width=1.3)
            vehicle = _cruiser(0, 17, 15.0, -15.0 * t_center * dt_s, lane_width=1.3)
            agents.append(cyclist)
            agents.append(vehicle)
            planted.append(PlantedEvent(cls, vehicle.id, cyclist.id, t_center))

    return Segment(segment_id, dt_s, num_steps, agents, planted)


def segment_to_dict(seg: Segment) -> dict:
    d = asdict(seg)
    return d


def dict_to_segment(d: dict) -> Segment:
    agents = [Agent(**{**a, "lane_changes": [LaneChange(**lc) for lc in a["lane_changes"]],
                        "speed_pulses": [SpeedPulse(**sp) for sp in a["speed_pulses"]]})
              for a in d["agents"]]
    planted = [PlantedEvent(**p) for p in d["planted_events"]]
    return Segment(d["segment_id"], d["dt_s"], d["num_steps"], agents, planted)


def generate_corpus(num_segments: int, seed: int) -> list:
    return [generate_segment(i + 1, seed * 100003 + i) for i in range(num_segments)]


def write_corpus(segments: list, path: str):
    with open(path, "w") as f:
        json.dump([segment_to_dict(s) for s in segments], f)


def read_corpus(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    return [dict_to_segment(d) for d in data]
