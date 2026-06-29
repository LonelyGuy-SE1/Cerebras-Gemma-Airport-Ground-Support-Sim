from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Iterable

import mujoco
import numpy as np

from app.models import (
    CoordinationPolicy,
    IncidentName,
    PhysicsAircraft,
    PhysicsContact,
    PhysicsMetrics,
    PhysicsRule,
    PhysicsSnapshot,
    PhysicsVehicle,
    Pose3D,
    ProviderName,
    TimingMetrics,
    Vec3,
)


TIMESTEP = 0.04


WAYPOINTS: dict[str, tuple[float, float]] = {
    "fuel_farm": (-23.0, -11.2),
    "ems_stand": (-24.2, -15.4),
    "cargo_ramp": (-23.0, 3.6),
    "catering_base": (-15.2, 10.6),
    "bus_stand": (-23.4, -4.2),
    "service_lane_west": (-18.0, -13.0),
    "central_hub": (-8.6, -13.0),
    "taxiway_crossing_c": (0.8, -13.0),
    "service_lane_east": (11.2, -13.0),
    "gate_alpha": (22.0, -3.3),
    "gate_alpha_medical": (22.0, -5.1),
    "gate_bravo": (20.2, 7.8),
    "terminal_north": (-4.6, 9.4),
    "service_lane_north": (8.2, 9.4),
    "maintenance_bay": (-1.5, 15.1),
    "security_post": (25.0, 14.2),
    "pushback_stand": (15.5, -15.2),
    "apron_hold": (16.9, -13.0),
    "runway_27_west": (-42.0, -24.0),
    "runway_09_east": (42.0, -24.0),
    "runway_crossing_27": (-2.0, -24.0),
    "taxiway_delta_hold": (-2.0, -16.7),
    "tower": (-28.0, 17.0),
}

ZONES: dict[str, dict[str, float | str]] = {
    "service_lane_east": {"label": "East service", "x": 8.2, "y": -15.4, "width": 11.6, "height": 5.0},
    "service_lane_north": {"label": "North lane", "x": -2.8, "y": 7.2, "width": 17.5, "height": 4.3},
    "taxiway_crossing_c": {"label": "Crossing C", "x": -2.0, "y": -15.5, "width": 6.0, "height": 5.3},
    "gate_alpha": {"label": "Gate Alpha", "x": 17.8, "y": -7.8, "width": 9.5, "height": 7.5},
    "runway_27": {"label": "Runway 09/27", "x": -48.0, "y": -27.2, "width": 96.0, "height": 6.4},
    "runway_crossing_27": {"label": "Taxiway Delta crossing", "x": -4.8, "y": -29.6, "width": 5.6, "height": 11.0},
    "final_27": {"label": "Final approach 27", "x": -76.0, "y": -29.0, "width": 32.0, "height": 10.0},
    "departure_queue": {"label": "Departure queue", "x": 19.5, "y": -27.4, "width": 15.0, "height": 6.8},
}

LANE_WAYPOINTS = {
    "service_lane_west",
    "central_hub",
    "taxiway_crossing_c",
    "service_lane_east",
    "service_lane_north",
    "terminal_north",
    "apron_hold",
    "taxiway_delta_hold",
    "runway_crossing_27",
}

CONFLICT_WAYPOINTS = {
    "service_lane_west",
    "central_hub",
    "taxiway_crossing_c",
    "service_lane_east",
    "service_lane_north",
    "gate_alpha",
    "gate_alpha_medical",
    "gate_bravo",
    "apron_hold",
    "taxiway_delta_hold",
    "runway_crossing_27",
}

CONFLICT_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"service_lane_west", "central_hub", "taxiway_crossing_c"}),
    frozenset({"service_lane_east", "gate_alpha", "gate_alpha_medical", "apron_hold"}),
    frozenset({"terminal_north", "service_lane_north", "gate_bravo"}),
    frozenset({"taxiway_delta_hold", "runway_crossing_27"}),
)

LANE_OFFSETS_BY_KIND = {
    "fuel": -0.82,
    "baggage": 0.36,
    "catering": -0.36,
    "bus": 0.82,
    "pushback": -0.24,
    "maintenance": 0.24,
    "ambulance": 1.0,
    "security": -1.0,
}

PATH_GRAPH: dict[str, tuple[str, ...]] = {
    "fuel_farm": ("service_lane_west",),
    "ems_stand": ("service_lane_west",),
    "bus_stand": ("service_lane_west",),
    "cargo_ramp": ("central_hub", "terminal_north"),
    "catering_base": ("terminal_north",),
    "maintenance_bay": ("terminal_north",),
    "service_lane_west": ("fuel_farm", "ems_stand", "bus_stand", "central_hub"),
    "central_hub": ("service_lane_west", "cargo_ramp", "taxiway_crossing_c", "terminal_north"),
    "taxiway_crossing_c": ("central_hub", "service_lane_east", "terminal_north", "taxiway_delta_hold"),
    "service_lane_east": ("taxiway_crossing_c", "gate_alpha", "gate_bravo", "apron_hold", "service_lane_north"),
    "service_lane_north": ("terminal_north", "gate_bravo", "service_lane_east", "security_post"),
    "terminal_north": ("catering_base", "maintenance_bay", "service_lane_north", "central_hub", "taxiway_crossing_c", "cargo_ramp"),
    "gate_alpha": ("service_lane_east", "gate_alpha_medical", "apron_hold"),
    "gate_alpha_medical": ("gate_alpha", "service_lane_east"),
    "gate_bravo": ("service_lane_east", "service_lane_north", "security_post"),
    "apron_hold": ("service_lane_east", "gate_alpha", "pushback_stand"),
    "pushback_stand": ("apron_hold",),
    "security_post": ("service_lane_north", "gate_bravo",),
    "taxiway_delta_hold": ("taxiway_crossing_c", "runway_crossing_27"),
    "runway_crossing_27": ("taxiway_delta_hold", "tower"),
    "tower": ("runway_crossing_27", "security_post"),
}


@dataclass(frozen=True)
class VehicleConfig:
    id: str
    label: str
    kind: str
    color: tuple[float, float, float, float]
    start: str
    route: list[str]
    length: float
    width: float
    height: float
    mass_kg: float
    max_speed: float
    max_accel: float
    max_yaw_rate: float
    priority: int
    task: str


@dataclass
class VehicleRuntime:
    config: VehicleConfig
    route: list[str]
    route_index: int = 0
    speed: float = 0.0
    status: str = "moving"
    task: str = ""
    priority: int = 0
    held_until_ms: int = 0
    yield_until_ms: int = 0
    yield_target_id: str | None = None
    policy_until_ms: int = 0
    idle_ms: int = 0
    completed_tasks: int = 0
    last_reached_target: str | None = None


@dataclass(frozen=True)
class AircraftConfig:
    id: str
    callsign: str
    model_key: str
    phase: str
    x: float
    y: float
    z: float
    yaw: float
    speed_mps: float
    priority: int
    runway: str = "09/27"


@dataclass
class AircraftRuntime:
    config: AircraftConfig
    x: float
    y: float
    z: float
    yaw: float
    speed_mps: float
    phase: str
    status: str
    clearance: str = "monitor"
    hold_until_ms: int = 0
    expedite_until_ms: int = 0
    go_around_until_ms: int = 0
    delay_ms: float = 0
    risk: int = 0


@dataclass
class RuntimeRule:
    zone: str
    rule: str
    expires_at_ms: int


@dataclass
class RuntimeMetrics:
    llm_latency_ms: int = 0
    policy_staleness: int = 0
    turnaround_delay_ms: float = 0
    vehicle_idle_ms: float = 0
    conflicts_avoided: int = 0
    emergency_response_ms: int | None = None
    fleet_throughput: int = 0
    interventions: int = 0
    deadlock_duration_ms: float = 0
    congestion_pressure: int = 0
    contact_count: int = 0
    kinetic_energy_j: float = 0
    validity_window_ms: int = 3000
    validity_consumed_pct: int = 0
    challenge_load: int = 0
    runway_incursion_risk: int = 0
    aircraft_delay_ms: float = 0
    active_aircraft: int = 0


@dataclass(frozen=True)
class VehicleStepState:
    x: float
    y: float
    yaw: float
    target_name: str
    target_x: float
    target_y: float
    distance: float
    desired_yaw: float


VEHICLES: tuple[VehicleConfig, ...] = (
    VehicleConfig(
        id="fuel_1",
        label="Fuel",
        kind="fuel",
        color=(0.96, 0.55, 0.13, 1),
        start="fuel_farm",
        route=[
            "service_lane_west",
            "central_hub",
            "taxiway_crossing_c",
            "service_lane_east",
            "gate_alpha",
            "service_lane_east",
            "taxiway_crossing_c",
            "central_hub",
            "service_lane_west",
            "fuel_farm",
        ],
        length=2.5,
        width=1.05,
        height=0.72,
        mass_kg=7800,
        max_speed=5.1,
        max_accel=1.6,
        max_yaw_rate=1.15,
        priority=32,
        task="Refuel Gate Alpha",
    ),
    VehicleConfig(
        id="baggage_1",
        label="Bags",
        kind="baggage",
        color=(0.28, 0.73, 1.0, 1),
        start="cargo_ramp",
        route=[
            "central_hub",
            "taxiway_crossing_c",
            "service_lane_east",
            "gate_bravo",
            "service_lane_north",
            "terminal_north",
            "cargo_ramp",
        ],
        length=1.9,
        width=0.92,
        height=0.55,
        mass_kg=2600,
        max_speed=6.0,
        max_accel=2.2,
        max_yaw_rate=1.55,
        priority=44,
        task="Load baggage",
    ),
    VehicleConfig(
        id="catering_1",
        label="Cat",
        kind="catering",
        color=(0.54, 0.88, 0.36, 1),
        start="catering_base",
        route=[
            "terminal_north",
            "service_lane_north",
            "gate_bravo",
            "service_lane_north",
            "terminal_north",
            "catering_base",
        ],
        length=2.2,
        width=1.0,
        height=0.85,
        mass_kg=4800,
        max_speed=5.2,
        max_accel=1.8,
        max_yaw_rate=1.25,
        priority=38,
        task="Catering restock",
    ),
    VehicleConfig(
        id="passenger_bus_1",
        label="Bus",
        kind="bus",
        color=(0.92, 0.79, 0.31, 1),
        start="bus_stand",
        route=[
            "service_lane_west",
            "central_hub",
            "taxiway_crossing_c",
            "service_lane_east",
            "gate_alpha",
            "service_lane_east",
            "taxiway_crossing_c",
            "central_hub",
            "service_lane_west",
            "bus_stand",
        ],
        length=3.3,
        width=1.2,
        height=1.0,
        mass_kg=11700,
        max_speed=5.5,
        max_accel=1.35,
        max_yaw_rate=1.0,
        priority=36,
        task="Passenger transfer",
    ),
    VehicleConfig(
        id="pushback_1",
        label="Push",
        kind="pushback",
        color=(0.62, 0.52, 1.0, 1),
        start="pushback_stand",
        route=["apron_hold", "gate_alpha", "apron_hold", "pushback_stand"],
        length=1.75,
        width=1.0,
        height=0.58,
        mass_kg=6400,
        max_speed=4.0,
        max_accel=1.7,
        max_yaw_rate=1.2,
        priority=58,
        task="Tow standby",
    ),
    VehicleConfig(
        id="maintenance_1",
        label="Maint",
        kind="maintenance",
        color=(1.0, 0.45, 0.24, 1),
        start="maintenance_bay",
        route=[],
        length=2.05,
        width=0.96,
        height=0.72,
        mass_kg=3900,
        max_speed=5.2,
        max_accel=1.9,
        max_yaw_rate=1.35,
        priority=48,
        task="Inspection loop",
    ),
    VehicleConfig(
        id="ambulance_1",
        label="EMS",
        kind="ambulance",
        color=(1.0, 0.1, 0.16, 1),
        start="ems_stand",
        route=[],
        length=2.3,
        width=1.02,
        height=0.86,
        mass_kg=5100,
        max_speed=7.6,
        max_accel=2.8,
        max_yaw_rate=1.8,
        priority=50,
        task="Medical standby",
    ),
    VehicleConfig(
        id="security_1",
        label="Sec",
        kind="security",
        color=(0.13, 0.88, 0.64, 1),
        start="security_post",
        route=[],
        length=1.9,
        width=0.92,
        height=0.64,
        mass_kg=3100,
        max_speed=6.2,
        max_accel=2.25,
        max_yaw_rate=1.65,
        priority=52,
        task="Perimeter patrol",
    ),
)


AIRCRAFT: tuple[AircraftConfig, ...] = (
    AircraftConfig(
        id="nasa742",
        callsign="NASA 742",
        model_key="dc8",
        phase="approach",
        x=-82.0,
        y=-24.0,
        z=7.6,
        yaw=0.0,
        speed_mps=5.2,
        priority=96,
    ),
    AircraftConfig(
        id="gulf3",
        callsign="NASA 503",
        model_key="g3",
        phase="departure",
        x=35.0,
        y=-24.0,
        z=0.86,
        yaw=math.pi,
        speed_mps=0.0,
        priority=72,
    ),
    AircraftConfig(
        id="cargo612",
        callsign="CARGO 612",
        model_key="dc8",
        phase="taxi_hold",
        x=-2.0,
        y=-16.8,
        z=0.85,
        yaw=-math.pi / 2,
        speed_mps=1.9,
        priority=58,
    ),
)


def _rgba(color: tuple[float, float, float, float]) -> str:
    return " ".join(f"{value:.3f}" for value in color)


def _escape(name: str) -> str:
    return name.replace("_", "-")


def _make_model_xml() -> str:
    vehicle_xml: list[str] = []
    for vehicle in VEHICLES:
        x, y = WAYPOINTS[vehicle.start]
        safe = _escape(vehicle.id)
        wheel_y = vehicle.width * 0.62
        wheel_x = vehicle.length * 0.32
        vehicle_xml.append(
            f"""
            <body name="{vehicle.id}" pos="{x:.3f} {y:.3f} {vehicle.height / 2 + 0.08:.3f}">
              <joint name="{vehicle.id}_x" type="slide" axis="1 0 0" damping="2.5" limited="true" range="-60 60"/>
              <joint name="{vehicle.id}_y" type="slide" axis="0 1 0" damping="2.5" limited="true" range="-40 40"/>
              <joint name="{vehicle.id}_yaw" type="hinge" axis="0 0 1" damping="1.2" limited="false"/>
              <geom name="{vehicle.id}_chassis" type="box" size="{vehicle.length / 2:.3f} {vehicle.width / 2:.3f} {vehicle.height / 2:.3f}" mass="{vehicle.mass_kg:.1f}" rgba="{_rgba(vehicle.color)}" friction="1.1 0.02 0.001" contype="0" conaffinity="0"/>
              <geom name="{vehicle.id}_sensor" type="sphere" size="{max(vehicle.length, vehicle.width) * 0.72:.3f}" rgba="{vehicle.color[0]:.3f} {vehicle.color[1]:.3f} {vehicle.color[2]:.3f} 0.045" contype="0" conaffinity="0"/>
              <geom name="{vehicle.id}_wheel_fl" type="cylinder" pos="{wheel_x:.3f} {wheel_y:.3f} {-vehicle.height / 2:.3f}" size="0.16 0.13" rgba="0.02 0.025 0.025 1" contype="0" conaffinity="0"/>
              <geom name="{vehicle.id}_wheel_fr" type="cylinder" pos="{wheel_x:.3f} {-wheel_y:.3f} {-vehicle.height / 2:.3f}" size="0.16 0.13" rgba="0.02 0.025 0.025 1" contype="0" conaffinity="0"/>
              <geom name="{vehicle.id}_wheel_rl" type="cylinder" pos="{-wheel_x:.3f} {wheel_y:.3f} {-vehicle.height / 2:.3f}" size="0.16 0.13" rgba="0.02 0.025 0.025 1" contype="0" conaffinity="0"/>
              <geom name="{vehicle.id}_wheel_rr" type="cylinder" pos="{-wheel_x:.3f} {-wheel_y:.3f} {-vehicle.height / 2:.3f}" size="0.16 0.13" rgba="0.02 0.025 0.025 1" contype="0" conaffinity="0"/>
              <site name="{vehicle.id}_front" pos="{vehicle.length / 2:.3f} 0 0" size="0.08" rgba="1 1 1 0.8"/>
            </body>
            """
        )

    return f"""
<mujoco model="airport_ground_support">
  <compiler angle="radian" coordinate="local" inertiafromgeom="true"/>
  <option timestep="{TIMESTEP}" gravity="0 0 -9.81" integrator="RK4" cone="elliptic" iterations="24"/>
  <size nconmax="300" njmax="500"/>
  <default>
    <geom condim="3" solref="0.015 1" solimp="0.9 0.95 0.001"/>
  </default>
  <asset>
    <material name="asphalt" rgba="0.045 0.065 0.065 1"/>
    <material name="lane" rgba="0.12 0.18 0.18 1"/>
    <material name="gate" rgba="0.26 0.32 0.31 1"/>
    <material name="line_yellow" rgba="0.92 0.72 0.2 1"/>
    <material name="aircraft" rgba="0.82 0.88 0.88 1"/>
    <material name="red_zone" rgba="0.75 0.08 0.1 0.3"/>
  </asset>
  <worldbody>
    <light name="apron_key" pos="0 -20 28" dir="0 0 -1" diffuse="0.8 0.92 0.88"/>
    <geom name="apron_floor" type="plane" size="32 22 0.1" material="asphalt" friction="1.3 0.02 0.001"/>
    <geom name="runway_edge" type="box" pos="0 -17.0 0.025" size="31 0.08 0.025" material="line_yellow" contype="0" conaffinity="0"/>
    <geom name="west_lane" type="box" pos="-12.5 -13.0 0.035" size="12.2 1.55 0.03" material="lane" contype="0" conaffinity="0"/>
    <geom name="east_lane" type="box" pos="10.5 -13.0 0.035" size="11.2 1.55 0.03" material="lane" contype="0" conaffinity="0"/>
    <geom name="north_lane" type="box" pos="2.2 9.4 0.035" size="15.8 1.35 0.03" material="lane" contype="0" conaffinity="0"/>
    <geom name="diagonal_lane_a" type="box" pos="-14.7 -5.4 0.04" euler="0 0 0.78" size="8.8 1.25 0.03" material="lane" contype="0" conaffinity="0"/>
    <geom name="diagonal_lane_b" type="box" pos="10.1 -4.3 0.04" euler="0 0 -1.08" size="10.0 1.25 0.03" material="lane" contype="0" conaffinity="0"/>
    <geom name="gate_alpha_pad" type="box" pos="22.4 -4.1 0.045" size="4.8 3.8 0.035" material="gate" contype="0" conaffinity="0"/>
    <geom name="gate_bravo_pad" type="box" pos="21.0 7.2 0.045" size="4.6 3.4 0.035" material="gate" contype="0" conaffinity="0"/>
    <body name="aircraft_alpha" pos="23.0 -1.0 0.9" euler="0 0 -1.5708">
      <geom name="alpha_fuselage" type="capsule" fromto="0 -3.8 0 0 4.2 0" size="0.48" material="aircraft" contype="0" conaffinity="0"/>
      <geom name="alpha_wing" type="box" pos="0 0 0" size="4.2 0.16 0.06" material="aircraft" contype="0" conaffinity="0"/>
      <geom name="alpha_tail" type="box" pos="0 3.45 0.15" size="1.8 0.12 0.05" material="aircraft" contype="0" conaffinity="0"/>
    </body>
    <body name="aircraft_bravo" pos="21.0 9.6 0.9" euler="0 0 -1.5708">
      <geom name="bravo_fuselage" type="capsule" fromto="0 -3.4 0 0 3.6 0" size="0.42" material="aircraft" contype="0" conaffinity="0"/>
      <geom name="bravo_wing" type="box" pos="0 0 0" size="3.6 0.15 0.055" material="aircraft" contype="0" conaffinity="0"/>
      <geom name="bravo_tail" type="box" pos="0 3.0 0.14" size="1.45 0.1 0.05" material="aircraft" contype="0" conaffinity="0"/>
    </body>
    <geom name="no_go_static" type="box" pos="2.5 -2.1 0.22" size="3.0 2.0 0.2" rgba="0.65 0.1 0.06 0.25" contype="0" conaffinity="0"/>
    {"".join(vehicle_xml)}
  </worldbody>
</mujoco>
"""


def model_xml() -> str:
    return _make_model_xml()


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _in_zone(x: float, y: float, zone_id: str) -> bool:
    zone = ZONES.get(zone_id)
    if not zone:
        return False
    return (
        float(zone["x"]) <= x <= float(zone["x"]) + float(zone["width"])
        and float(zone["y"]) <= y <= float(zone["y"]) + float(zone["height"])
    )


def _shortest_path(start: str, end: str) -> list[str]:
    if start == end:
        return [end]
    if start not in WAYPOINTS or end not in WAYPOINTS:
        return [end]

    queue: list[tuple[str, list[str]]] = [(start, [start])]
    visited = {start}
    while queue:
        node, path = queue.pop(0)
        for neighbor in PATH_GRAPH.get(node, ()):
            if neighbor in visited:
                continue
            next_path = [*path, neighbor]
            if neighbor == end:
                return next_path
            visited.add(neighbor)
            queue.append((neighbor, next_path))
    return [end]


def _path_through(start: str, via: str, end: str) -> list[str]:
    first = _shortest_path(start, via)
    second = _shortest_path(via, end)
    return [*first, *second[1:]]


def _same_conflict_group(first: str, second: str) -> bool:
    return any(first in group and second in group for group in CONFLICT_GROUPS)


class MuJoCoAirportSimulation:
    def __init__(self, pane: ProviderName, seed: int = 42):
        self.pane = pane
        self.seed = seed
        self.model = mujoco.MjModel.from_xml_string(_make_model_xml())
        self.data = mujoco.MjData(self.model)
        self.sim_time_ms = 0
        self.incident: IncidentName | None = None
        self.incident_started_at_ms: int | None = None
        self.priority_vehicle_id: str | None = None
        self.vehicles: dict[str, VehicleRuntime] = {
            config.id: VehicleRuntime(config=config, route=list(config.route), task=config.task, priority=config.priority)
            for config in VEHICLES
        }
        self.aircraft: dict[str, AircraftRuntime] = {
            config.id: AircraftRuntime(
                config=config,
                x=config.x,
                y=config.y,
                z=config.z,
                yaw=config.yaw,
                speed_mps=config.speed_mps,
                phase=config.phase,
                status=config.phase,
            )
            for config in AIRCRAFT
        }
        self.active_rules: list[RuntimeRule] = []
        self.blocked_zones: list[str] = []
        self.metrics = RuntimeMetrics()
        self.last_policy_summary = "MuJoCo apron model nominal"
        self.last_coordinator_mode: str = "idle"
        self.last_coordinator_model = ""
        self.last_timing: TimingMetrics | None = None
        self._joint_address: dict[str, tuple[int, int, int]] = {}
        for config in VEHICLES:
            self._joint_address[config.id] = (
                int(self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"{config.id}_x")]),
                int(self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"{config.id}_y")]),
                int(self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"{config.id}_yaw")]),
            )
        mujoco.mj_forward(self.model, self.data)

    def trigger_incident(self, incident: IncidentName) -> None:
        self.incident = incident
        self.incident_started_at_ms = self.sim_time_ms

        if incident == "medical_emergency":
            self.priority_vehicle_id = "ambulance_1"
            ambulance = self.vehicles["ambulance_1"]
            ambulance.priority = 98
            ambulance.task = "Emergency response to Gate Alpha"
            ambulance.route = [
                "service_lane_west",
                "central_hub",
                "taxiway_crossing_c",
                "service_lane_east",
                "gate_alpha",
                "gate_alpha_medical",
            ]
            ambulance.route_index = 0
            ambulance.status = "priority"
            self.last_policy_summary = "Medical incident detected; semantic coordinator pending"
        elif incident == "fuel_leak":
            self.priority_vehicle_id = "security_1"
            self.active_rules.append(RuntimeRule("service_lane_east", "safety_watch", self.sim_time_ms + 6500))
            self.last_policy_summary = "Fuel leak detected at east service lane"
        elif incident == "vehicle_breakdown":
            self.priority_vehicle_id = "maintenance_1"
            self.blocked_zones.append("taxiway_crossing_c")
            self.active_rules.append(RuntimeRule("taxiway_crossing_c", "blocked", self.sim_time_ms + 8500))
            self.last_policy_summary = "Vehicle breakdown blocks Crossing C"
        elif incident == "vip_arrival":
            self.priority_vehicle_id = "pushback_1"
            self.last_policy_summary = "Priority arrival changes gate sequencing"
        elif incident == "runway_incursion":
            self.priority_vehicle_id = "nasa742"
            self.metrics.validity_window_ms = 3000
            self.vehicles["fuel_1"].held_until_ms = self.sim_time_ms + 3500
            self.vehicles["security_1"].route = ["taxiway_delta_hold", "runway_crossing_27", "taxiway_delta_hold"]
            self.vehicles["security_1"].route_index = 0
            self.vehicles["security_1"].priority = 86
            self.aircraft["nasa742"].phase = "approach"
            self.aircraft["nasa742"].status = "short final"
            self.aircraft["nasa742"].clearance = "continue"
            self.aircraft["nasa742"].x = -52.0
            self.aircraft["nasa742"].y = -24.0
            self.aircraft["nasa742"].z = 2.2
            self.aircraft["nasa742"].yaw = 0.0
            self.aircraft["nasa742"].speed_mps = self.aircraft["nasa742"].config.speed_mps
            self.aircraft["cargo612"].x = -2.0
            self.aircraft["cargo612"].y = -23.1
            self.aircraft["cargo612"].z = 0.85
            self.aircraft["cargo612"].phase = "crossing"
            self.aircraft["cargo612"].status = "crossing active runway"
            self.aircraft["cargo612"].clearance = "taxi_crossing"
            self.aircraft["cargo612"].risk = 82
            self.aircraft["gulf3"].x = 35.0
            self.aircraft["gulf3"].y = -24.0
            self.aircraft["gulf3"].z = 0.86
            self.aircraft["gulf3"].yaw = math.pi
            self.aircraft["gulf3"].phase = "departure"
            self.aircraft["gulf3"].status = "departure held at runway 27"
            self.aircraft["gulf3"].clearance = "line_up_pending"
            self.aircraft["gulf3"].speed_mps = 0.0
            self.aircraft["gulf3"].hold_until_ms = self.sim_time_ms + 7600
            self.active_rules.extend(
                [
                    RuntimeRule("runway_crossing_27", "incursion", self.sim_time_ms + 7200),
                    RuntimeRule("departure_queue", "departure_hold", self.sim_time_ms + 7000),
                    RuntimeRule("service_lane_east", "hazmat_watch", self.sim_time_ms + 8000),
                ]
            )
            self.last_policy_summary = (
                "Runway incursion: short-final DC-8, active crossing traffic, held departure, and fuel hazard conflict."
            )
        else:
            self.priority_vehicle_id = "ambulance_1"
            ambulance = self.vehicles["ambulance_1"]
            ambulance.priority = 99
            ambulance.task = "Life-safety response under compound apron constraints"
            ambulance.route = [
                "service_lane_west",
                "central_hub",
                "taxiway_crossing_c",
                "service_lane_east",
                "gate_alpha",
                "gate_alpha_medical",
            ]
            ambulance.route_index = 0
            self.vehicles["fuel_1"].held_until_ms = self.sim_time_ms + 2200
            self.vehicles["pushback_1"].priority = 82
            self.active_rules.extend(
                [
                    RuntimeRule("taxiway_crossing_c", "blocked", self.sim_time_ms + 9000),
                    RuntimeRule("service_lane_east", "hazmat_watch", self.sim_time_ms + 9000),
                    RuntimeRule("gate_alpha", "vip_priority", self.sim_time_ms + 7200),
                ]
            )
            self.blocked_zones.append("taxiway_crossing_c")
            self.last_policy_summary = "Compound incursion: medical access, fuel hazard, VIP pressure, and blocked crossing compete."

    def apply_policy(
        self,
        policy: CoordinationPolicy,
        timing: TimingMetrics,
        requested_at_sim_ms: int,
        mode: str,
        model_name: str,
    ) -> None:
        self.metrics.llm_latency_ms = timing.latency_ms
        effective_policy_age_ms = timing.latency_ms + max(0, self.sim_time_ms - requested_at_sim_ms)
        self.metrics.validity_consumed_pct = min(
            999,
            round((effective_policy_age_ms / max(1, self.metrics.validity_window_ms)) * 100),
        )
        self.metrics.policy_staleness = min(
            100,
            max(
                0,
                round(
                    (effective_policy_age_ms / max(1, self.metrics.validity_window_ms)) * 42
                    + self.metrics.congestion_pressure * 5
                ),
            ),
        )
        self.metrics.interventions += len(policy.actions)
        self.metrics.conflicts_avoided += max(1, round(len(policy.actions) * (1.4 if self.metrics.policy_staleness < 35 else 0.55)))
        self.last_policy_summary = policy.summary
        self.last_coordinator_mode = mode
        self.last_coordinator_model = model_name
        self.last_timing = timing

        if self.metrics.policy_staleness >= 65:
            self.metrics.turnaround_delay_ms += effective_policy_age_ms * 0.42
            self.metrics.deadlock_duration_ms += min(4500, effective_policy_age_ms * 0.65)
            stale_zone = "runway_27" if self.incident == "runway_incursion" else "taxiway_crossing_c"
            self.active_rules.append(RuntimeRule(stale_zone, "stale_conflict", self.sim_time_ms + 5000))
            if stale_zone not in self.blocked_zones:
                self.blocked_zones.append(stale_zone)
            if self.incident == "runway_incursion":
                self.metrics.runway_incursion_risk = max(self.metrics.runway_incursion_risk, 92)
                self.metrics.aircraft_delay_ms += min(9000, effective_policy_age_ms * 1.2)
            self.last_policy_summary = f"Stale policy applied after the apron state changed. {policy.summary}"

        for rule in policy.temporary_rules:
            self.active_rules.append(RuntimeRule(rule.zone, rule.rule, self.sim_time_ms + rule.duration_ms))

        for action in policy.actions:
            if action.directive == "block_zone" and action.zone:
                self.active_rules.append(
                    RuntimeRule(action.zone, "blocked", self.sim_time_ms + (action.duration_ms or 5000))
                )
                if action.zone not in self.blocked_zones:
                    self.blocked_zones.append(action.zone)
                continue

            vehicle = self.vehicles.get(action.vehicle_id)
            aircraft = self.aircraft.get(action.vehicle_id)
            if aircraft:
                self._apply_aircraft_action(aircraft, action)
                continue
            if not vehicle:
                continue

            if action.directive == "hold_position":
                vehicle.held_until_ms = max(vehicle.held_until_ms, self.sim_time_ms + (action.duration_ms or 4000))
                vehicle.status = "holding"
                vehicle.policy_until_ms = vehicle.held_until_ms
            elif action.directive == "yield_to":
                vehicle.yield_target_id = action.target or policy.priority_vehicle
                vehicle.yield_until_ms = max(vehicle.yield_until_ms, self.sim_time_ms + (action.duration_ms or 4500))
                vehicle.status = "yielding"
                vehicle.policy_until_ms = vehicle.yield_until_ms
            elif action.directive == "reroute_via" and action.waypoint in WAYPOINTS:
                current_target = vehicle.route[vehicle.route_index] if vehicle.route else vehicle.config.start
                final_target = vehicle.route[-1] if vehicle.route else vehicle.config.start
                vehicle.route = _path_through(current_target, action.waypoint, final_target)
                vehicle.route_index = 0
                vehicle.status = "rerouting"
                vehicle.policy_until_ms = self.sim_time_ms + (action.duration_ms or 6000)
            elif action.directive == "priority_route":
                waypoint = action.waypoint if action.waypoint in WAYPOINTS else "gate_alpha_medical"
                current_target = vehicle.route[vehicle.route_index] if vehicle.route else vehicle.config.start
                vehicle.route = _shortest_path(current_target, waypoint)
                vehicle.route_index = 0
                vehicle.priority = max(vehicle.priority, 98)
                vehicle.status = "priority"
                vehicle.policy_until_ms = self.sim_time_ms + (action.duration_ms or 9000)

    def _apply_aircraft_action(self, aircraft: AircraftRuntime, action: object) -> None:
        directive = getattr(action, "directive", "")
        duration_ms = getattr(action, "duration_ms", None) or 5000

        if directive == "go_around":
            aircraft.phase = "go_around"
            aircraft.status = "go around issued"
            aircraft.clearance = "go_around"
            aircraft.go_around_until_ms = self.sim_time_ms + duration_ms
            aircraft.delay_ms += 1800
            aircraft.risk = min(aircraft.risk, 8)
        elif directive in ("hold_position", "cancel_takeoff", "line_up_and_wait"):
            aircraft.hold_until_ms = max(aircraft.hold_until_ms, self.sim_time_ms + duration_ms)
            aircraft.status = "holding short"
            aircraft.clearance = "hold_short"
            if aircraft.phase == "departure":
                aircraft.speed_mps = 0
                if directive in ("hold_position", "cancel_takeoff"):
                    aircraft.y = -17.4
            aircraft.risk = max(0, aircraft.risk - 35)
        elif directive == "expedite_crossing":
            aircraft.expedite_until_ms = max(aircraft.expedite_until_ms, self.sim_time_ms + duration_ms)
            aircraft.status = "expedite crossing"
            aircraft.clearance = "expedite_crossing"
            aircraft.risk = max(0, aircraft.risk - 45)
        elif directive == "clear_land":
            aircraft.status = "cleared to land"
            aircraft.clearance = "cleared_land"
        elif directive == "yield_to":
            aircraft.hold_until_ms = max(aircraft.hold_until_ms, self.sim_time_ms + duration_ms)
            aircraft.status = "yielding"
            aircraft.clearance = "yield"

    def step(self, dt_ms: int, running: bool = True) -> PhysicsSnapshot:
        if not running:
            return self.snapshot()

        remaining = max(10, min(dt_ms, 10000)) / 1000
        while remaining > 0:
            step_dt = min(TIMESTEP, remaining)
            self._control_step(step_dt)
            self._control_aircraft(step_dt)
            mujoco.mj_step(self.model, self.data)
            self.sim_time_ms += round(step_dt * 1000)
            remaining -= step_dt

        self.active_rules = [rule for rule in self.active_rules if rule.expires_at_ms > self.sim_time_ms]
        self.blocked_zones = [
            zone
            for zone in self.blocked_zones
            if any(rule.zone == zone and rule.expires_at_ms > self.sim_time_ms for rule in self.active_rules)
        ]
        return self.snapshot()

    def snapshot(self) -> PhysicsSnapshot:
        contacts = self._contacts()
        self._update_metrics(contacts)
        vehicles = [self._vehicle_snapshot(runtime) for runtime in self.vehicles.values()]
        aircraft = [self._aircraft_snapshot(runtime) for runtime in self.aircraft.values()]
        return PhysicsSnapshot(
            pane=self.pane,
            seed=self.seed,
            simTimeMs=self.sim_time_ms,
            physicsEngine=f"MuJoCo {mujoco.__version__}",
            timestepMs=round(TIMESTEP * 1000),
            incident=self.incident,
            incidentStartedAtMs=self.incident_started_at_ms,
            priorityVehicleId=self.priority_vehicle_id,
            vehicles=vehicles,
            aircraft=aircraft,
            activeRules=[
                PhysicsRule(zone=rule.zone, rule=rule.rule, expiresAtMs=rule.expires_at_ms)
                for rule in self.active_rules
            ],
            blockedZones=list(self.blocked_zones),
            contacts=contacts,
            metrics=PhysicsMetrics(
                llmLatencyMs=self.metrics.llm_latency_ms,
                policyStaleness=self.metrics.policy_staleness,
                turnaroundDelayMs=round(self.metrics.turnaround_delay_ms),
                vehicleIdleMs=round(self.metrics.vehicle_idle_ms),
                conflictsAvoided=self.metrics.conflicts_avoided,
                emergencyResponseMs=self.metrics.emergency_response_ms,
                fleetThroughput=self.metrics.fleet_throughput,
                interventions=self.metrics.interventions,
                deadlockDurationMs=round(self.metrics.deadlock_duration_ms),
                congestionPressure=self.metrics.congestion_pressure,
                contactCount=self.metrics.contact_count,
                kineticEnergyJ=round(self.metrics.kinetic_energy_j, 1),
                validityWindowMs=self.metrics.validity_window_ms,
                validityConsumedPct=self.metrics.validity_consumed_pct,
                challengeLoad=self.metrics.challenge_load,
                runwayIncursionRisk=self.metrics.runway_incursion_risk,
                aircraftDelayMs=round(self.metrics.aircraft_delay_ms),
                activeAircraft=self.metrics.active_aircraft,
            ),
            lastPolicySummary=self.last_policy_summary,
            lastCoordinatorMode=self.last_coordinator_mode,
            lastCoordinatorModel=self.last_coordinator_model,
            lastTiming=self.last_timing,
            waypoints={name: Vec3(x=x, y=y, z=0) for name, (x, y) in WAYPOINTS.items()},
            zones=ZONES,
        )

    def _advance_vehicle_target(self, runtime: VehicleRuntime, current_x: float, current_y: float) -> tuple[str, float, float, float]:
        if not runtime.route:
            target_name = runtime.config.start
            target_x, target_y = WAYPOINTS[target_name]
            return target_name, target_x, target_y, math.hypot(target_x - current_x, target_y - current_y)

        for _ in range(len(runtime.route) + 1):
            target_name = runtime.route[runtime.route_index]
            target_x, target_y = self._route_target_xy(runtime, target_name, current_x, current_y)
            distance = math.hypot(target_x - current_x, target_y - current_y)
            if distance >= max(0.72, runtime.config.length * 0.42):
                return target_name, target_x, target_y, distance

            runtime.last_reached_target = target_name
            runtime.route_index += 1
            if runtime.route_index >= len(runtime.route):
                runtime.route_index = 0
                runtime.completed_tasks += 1

        target_name = runtime.route[runtime.route_index]
        target_x, target_y = self._route_target_xy(runtime, target_name, current_x, current_y)
        return target_name, target_x, target_y, math.hypot(target_x - current_x, target_y - current_y)

    def _route_target_xy(
        self,
        runtime: VehicleRuntime,
        target_name: str,
        current_x: float,
        current_y: float,
    ) -> tuple[float, float]:
        base_x, base_y = WAYPOINTS[target_name]
        if target_name not in LANE_WAYPOINTS or not runtime.route:
            return base_x, base_y

        if runtime.route_index == 0:
            previous_name = runtime.config.start
        else:
            previous_name = runtime.route[runtime.route_index - 1]
        previous_x, previous_y = WAYPOINTS.get(previous_name, (current_x, current_y))
        tangent_x = base_x - previous_x
        tangent_y = base_y - previous_y

        if math.hypot(tangent_x, tangent_y) < 0.01 and len(runtime.route) > 1:
            next_name = runtime.route[(runtime.route_index + 1) % len(runtime.route)]
            next_x, next_y = WAYPOINTS.get(next_name, (current_x, current_y))
            tangent_x = next_x - base_x
            tangent_y = next_y - base_y

        tangent_length = math.hypot(tangent_x, tangent_y)
        if tangent_length < 0.01:
            return base_x, base_y

        offset = LANE_OFFSETS_BY_KIND.get(runtime.config.kind, 0.0)
        normal_x = -tangent_y / tangent_length
        normal_y = tangent_x / tangent_length
        return base_x + normal_x * offset, base_y + normal_y * offset

    @staticmethod
    def _should_yield_to(runtime: VehicleRuntime, other: VehicleRuntime) -> bool:
        if runtime.priority != other.priority:
            return runtime.priority < other.priority
        return runtime.config.id > other.config.id

    def _control_step(self, dt: float) -> None:
        congestion = 0
        idle_this_step = 0.0
        states: dict[str, VehicleStepState] = {}

        for runtime in self.vehicles.values():
            if runtime.status not in ("priority", "rerouting") or runtime.policy_until_ms <= self.sim_time_ms:
                runtime.status = "moving"

            _, _, qyaw = self._joint_address[runtime.config.id]
            current_x, current_y = self._position(runtime.config.id)
            current_yaw = _wrap_angle(float(self.data.qpos[qyaw]))
            self.data.qpos[qyaw] = current_yaw
            target_name, target_x, target_y, distance = self._advance_vehicle_target(runtime, current_x, current_y)
            desired_yaw = math.atan2(target_y - current_y, target_x - current_x) if distance > 0.01 else current_yaw
            states[runtime.config.id] = VehicleStepState(
                x=current_x,
                y=current_y,
                yaw=current_yaw,
                target_name=target_name,
                target_x=target_x,
                target_y=target_y,
                distance=distance,
                desired_yaw=desired_yaw,
            )

        for runtime in self.vehicles.values():
            qx, qy, qyaw = self._joint_address[runtime.config.id]
            state = states[runtime.config.id]
            current_x = state.x
            current_y = state.y
            current_yaw = state.yaw
            target_name = state.target_name
            target_x = state.target_x
            target_y = state.target_y
            distance = state.distance
            desired_yaw = state.desired_yaw

            is_priority = runtime.config.id == self.priority_vehicle_id or runtime.status == "priority"
            desired_speed = runtime.config.max_speed * (1.22 if is_priority else 0.96)
            if not runtime.route:
                desired_speed = 0.0
                runtime.status = "standby"
            if distance < 3.8:
                desired_speed *= max(0.18, distance / 3.8)

            yaw_error = _wrap_angle(desired_yaw - current_yaw)
            if abs(yaw_error) > 1.05:
                desired_speed = min(desired_speed, runtime.config.max_speed * 0.34)

            if runtime.held_until_ms > self.sim_time_ms:
                desired_speed = 0.0
                runtime.status = "holding"

            if runtime.yield_until_ms > self.sim_time_ms and runtime.yield_target_id:
                other_state = states.get(runtime.yield_target_id)
                if other_state and math.hypot(current_x - other_state.x, current_y - other_state.y) < 8.5:
                    desired_speed = min(desired_speed, runtime.config.max_speed * 0.1)
                    runtime.status = "yielding"

            for rule in self.active_rules:
                priority_vehicle = runtime.config.id == self.priority_vehicle_id or runtime.config.kind == "ambulance"
                if rule.rule in ("blocked", "emergency_only", "safety_hold", "crossing_lockout") and not priority_vehicle:
                    if target_name == rule.zone or _in_zone(current_x, current_y, rule.zone) or _in_zone(target_x, target_y, rule.zone):
                        desired_speed = 0.0 if rule.rule in ("blocked", "safety_hold", "crossing_lockout") else min(desired_speed, runtime.config.max_speed * 0.15)
                        runtime.status = "blocked" if desired_speed < 0.1 else "holding"

            dir_x = math.cos(desired_yaw)
            dir_y = math.sin(desired_yaw)

            for other in self.vehicles.values():
                if other.config.id == runtime.config.id:
                    continue
                other_state = states[other.config.id]
                rel_x = other_state.x - current_x
                rel_y = other_state.y - current_y
                separation = math.hypot(rel_x, rel_y)
                ahead = rel_x * dir_x + rel_y * dir_y
                lateral = abs(rel_x * dir_y - rel_y * dir_x)
                safe_distance = max(3.1, (runtime.config.length + other.config.length) * 0.66 + 0.7)
                follow_distance = safe_distance + max(1.6, runtime.speed * 1.4)
                same_direction = abs(_wrap_angle(desired_yaw - other_state.desired_yaw)) < 0.72
                same_conflict_point = target_name == other_state.target_name and target_name not in LANE_WAYPOINTS
                paired_conflict = _same_conflict_group(target_name, other_state.target_name)
                should_yield = self._should_yield_to(runtime, other)
                closing_head_on = ahead > 0 and abs(_wrap_angle(desired_yaw - other_state.desired_yaw)) > 2.15

                if same_direction and 0 < ahead < follow_distance and lateral < max(1.1, (runtime.config.width + other.config.width) * 0.62):
                    desired_speed = min(desired_speed, max(0.0, other.speed - 0.18))
                    runtime.status = "spacing"
                    congestion += 1
                elif closing_head_on and separation < safe_distance * 2.2 and lateral < max(1.2, (runtime.config.width + other.config.width) * 0.72):
                    if should_yield:
                        desired_speed = 0.0
                        runtime.status = "yielding"
                    else:
                        desired_speed = min(desired_speed, runtime.config.max_speed * 0.35)
                        runtime.status = "spacing"
                    congestion += 1

                if separation < safe_distance * 0.82:
                    desired_speed = 0.0 if should_yield else min(desired_speed, runtime.config.max_speed * 0.16)
                    runtime.status = "yielding" if should_yield else "spacing"
                    congestion += 1
                elif separation < safe_distance * 1.45 and should_yield:
                    desired_speed = 0.0
                    runtime.status = "yielding"
                    congestion += 1
                elif should_yield and same_conflict_point and state.distance < 16.0 and other_state.distance < 16.0:
                    hold_speed = 0.0
                    desired_speed = min(desired_speed, hold_speed)
                    runtime.status = "yielding" if hold_speed == 0.0 else "spacing"
                    congestion += 1
                elif (
                    should_yield
                    and paired_conflict
                    and state.distance < 7.5
                    and other_state.distance < 7.5
                    and separation < safe_distance * 1.75
                ):
                    hold_speed = 0.0 if state.distance > other_state.distance + 1.1 else runtime.config.max_speed * 0.22
                    desired_speed = min(desired_speed, hold_speed)
                    runtime.status = "yielding" if hold_speed == 0.0 else "spacing"
                    congestion += 1

            accel_limit = runtime.config.max_accel * dt * (3.4 if desired_speed < runtime.speed else 1.0)
            runtime.speed += float(np.clip(desired_speed - runtime.speed, -accel_limit, accel_limit))
            if runtime.speed < 0.05:
                runtime.speed = 0.0
                idle_this_step += dt * 1000
                runtime.idle_ms += round(dt * 1000)

            yaw_rate = float(np.clip(yaw_error / max(dt, 1e-3), -runtime.config.max_yaw_rate, runtime.config.max_yaw_rate))
            speed_scale = max(0.08, 1.0 - min(abs(yaw_error), math.pi) / (math.pi * 0.92))
            forward_speed = runtime.speed * speed_scale

            self.data.qvel[qx] = math.cos(desired_yaw) * forward_speed
            self.data.qvel[qy] = math.sin(desired_yaw) * forward_speed
            self.data.qvel[qyaw] = yaw_rate

            if (
                runtime.config.id == "ambulance_1"
                and self.incident == "medical_emergency"
                and self.incident_started_at_ms is not None
                and self.metrics.emergency_response_ms is None
            ):
                gx, gy = WAYPOINTS["gate_alpha_medical"]
                if math.hypot(current_x - gx, current_y - gy) < 1.4:
                    self.metrics.emergency_response_ms = self.sim_time_ms - self.incident_started_at_ms
                    runtime.task = "Patient transfer established"

        self.metrics.vehicle_idle_ms += idle_this_step
        self.metrics.turnaround_delay_ms += idle_this_step * 0.14
        self.metrics.congestion_pressure = congestion
        if congestion >= 5:
            self.metrics.deadlock_duration_ms += dt * 1000

    def _control_aircraft(self, dt: float) -> None:
        runway_locked = any(
            rule.zone == "runway_27" and rule.rule in ("runway_closed", "blocked", "stale_conflict")
            for rule in self.active_rules
        )
        crossing_locked = any(
            rule.zone == "runway_crossing_27" and rule.rule in ("crossing_lockout", "blocked")
            for rule in self.active_rules
        )
        arrival_priority = any(rule.zone == "final_27" and rule.rule == "arrival_priority" for rule in self.active_rules)

        for aircraft in self.aircraft.values():
            cfg = aircraft.config

            if aircraft.phase == "approach":
                eta_ms = self._eta_to_threshold_ms(aircraft)
                if aircraft.clearance == "go_around" or aircraft.go_around_until_ms > self.sim_time_ms:
                    aircraft.phase = "go_around"
                    aircraft.status = "climbing through missed approach"
                    aircraft.x += math.cos(aircraft.yaw) * aircraft.speed_mps * dt * 0.65
                    aircraft.y -= 2.2 * dt
                    aircraft.z = min(11.5, aircraft.z + 1.35 * dt)
                    aircraft.yaw = _wrap_angle(aircraft.yaw - 0.22 * dt)
                    aircraft.risk = max(4, aircraft.risk - round(45 * dt))
                    aircraft.delay_ms += dt * 1000 * 0.5
                    continue

                aircraft.x += math.cos(aircraft.yaw) * aircraft.speed_mps * dt
                aircraft.y += math.sin(aircraft.yaw) * aircraft.speed_mps * dt
                descent_progress = min(1.0, max(0.0, (aircraft.x + 82.0) / 40.0))
                aircraft.z = max(0.82, cfg.z - descent_progress * (cfg.z - 0.82))
                if aircraft.x >= -42.0:
                    aircraft.status = "threshold crossing"
                    aircraft.phase = "rollout"
                    aircraft.z = 0.82
                elif arrival_priority and not runway_locked:
                    aircraft.status = "priority short final"
                else:
                    aircraft.status = "short final"

                if self.incident == "runway_incursion" and eta_ms is not None and eta_ms < 2600:
                    if self._runway_occupied() and aircraft.clearance != "go_around":
                        aircraft.risk = min(100, max(aircraft.risk, 86 + round((2600 - eta_ms) / 55)))
                        if eta_ms < 620:
                            aircraft.phase = "go_around"
                            aircraft.status = "last-second missed approach"
                            aircraft.clearance = "emergency_escape"
                            aircraft.risk = 100
                            aircraft.delay_ms += 4200
                            continue
                    elif runway_locked:
                        aircraft.risk = max(aircraft.risk, 48)

            elif aircraft.phase == "rollout":
                aircraft.z = 0.82
                aircraft.speed_mps = max(1.2, aircraft.speed_mps - 1.8 * dt)
                aircraft.x += aircraft.speed_mps * dt
                aircraft.status = "landing rollout"
                if self._runway_occupied(ignore=aircraft.config.id):
                    aircraft.risk = min(100, max(aircraft.risk, 90))

            elif aircraft.phase == "departure":
                if aircraft.hold_until_ms > self.sim_time_ms or runway_locked or crossing_locked:
                    aircraft.status = "holding short"
                    aircraft.clearance = "hold_short"
                    aircraft.delay_ms += dt * 1000
                    aircraft.speed_mps = 0
                elif aircraft.clearance in ("takeoff", "cleared_takeoff"):
                    aircraft.status = "takeoff roll"
                    aircraft.speed_mps = min(7.0, aircraft.speed_mps + 1.6 * dt)
                    aircraft.x -= aircraft.speed_mps * dt
                    aircraft.z = 0.86
                    if aircraft.x < -20:
                        aircraft.phase = "initial_climb"
                else:
                    aircraft.status = "departure waiting"
                    aircraft.delay_ms += dt * 1000 * 0.55

            elif aircraft.phase == "crossing":
                if aircraft.hold_until_ms > self.sim_time_ms or (crossing_locked and aircraft.clearance != "expedite_crossing"):
                    aircraft.status = "holding at Delta"
                    aircraft.delay_ms += dt * 1000
                    continue
                speed = aircraft.speed_mps * (1.75 if aircraft.expedite_until_ms > self.sim_time_ms else 1.0)
                aircraft.y -= speed * dt
                aircraft.status = "expedite crossing" if aircraft.expedite_until_ms > self.sim_time_ms else "crossing runway"
                if aircraft.y < -31.0:
                    aircraft.phase = "taxi_clear"
                    aircraft.status = "clear of runway"
                    aircraft.clearance = "clear"
                    aircraft.risk = 0
                eta = self._eta_to_threshold_ms(self.aircraft["nasa742"])
                if self.incident == "runway_incursion" and -28.4 < aircraft.y < -20.0 and eta is not None and eta < 3200:
                    aircraft.risk = min(100, max(aircraft.risk, 78 + round((3200 - eta) / 55)))

            elif aircraft.phase == "taxi_hold":
                aircraft.status = "holding short of runway"
                aircraft.clearance = "hold_short"
                aircraft.delay_ms += dt * 1000 * 0.12

            elif aircraft.phase == "missed_approach":
                aircraft.x += math.cos(aircraft.yaw) * aircraft.speed_mps * dt
                aircraft.y += math.sin(aircraft.yaw) * aircraft.speed_mps * dt
                aircraft.z = min(9.5, aircraft.z + 0.42 * dt)
                aircraft.status = "missed approach climb"

            elif aircraft.phase == "go_around":
                aircraft.x += math.cos(aircraft.yaw) * aircraft.speed_mps * dt * 0.7
                aircraft.y -= 2.1 * dt
                aircraft.z = min(11.5, aircraft.z + 1.1 * dt)
                aircraft.yaw = _wrap_angle(aircraft.yaw - 0.18 * dt)
                aircraft.status = "go around"
                aircraft.delay_ms += dt * 1000 * 0.5

            aircraft.risk = max(0, min(100, aircraft.risk))

    def _runway_occupied(self, ignore: str | None = None) -> bool:
        for aircraft in self.aircraft.values():
            if aircraft.config.id == ignore:
                continue
            if aircraft.phase in ("crossing", "departure", "rollout") and -47.5 < aircraft.x < 47.5 and -28.5 < aircraft.y < -20.0:
                return True
        for runtime in self.vehicles.values():
            x, y = self._position(runtime.config.id)
            if -47.5 < x < 47.5 and -28.5 < y < -20.0 and runtime.speed > 0.05:
                return True
        return False

    def _eta_to_threshold_ms(self, aircraft: AircraftRuntime) -> int | None:
        if aircraft.config.id != "nasa742" or aircraft.speed_mps <= 0 or aircraft.phase not in ("approach", "rollout"):
            return None
        if aircraft.x >= -42.0:
            return 0
        return max(0, round(((-42.0 - aircraft.x) / max(0.1, aircraft.speed_mps)) * 1000))

    def _position(self, vehicle_id: str) -> tuple[float, float]:
        xpos = self.data.body(vehicle_id).xpos
        return float(xpos[0]), float(xpos[1])

    def _vehicle_snapshot(self, runtime: VehicleRuntime) -> PhysicsVehicle:
        qx, qy, qyaw = self._joint_address[runtime.config.id]
        xpos = self.data.body(runtime.config.id).xpos
        xvel = self.data.qvel[qx]
        yvel = self.data.qvel[qy]
        target = runtime.route[runtime.route_index] if runtime.route else runtime.config.start
        return PhysicsVehicle(
            id=runtime.config.id,
            label=runtime.config.label,
            kind=runtime.config.kind,
            pose=Pose3D(x=float(xpos[0]), y=float(xpos[1]), z=float(xpos[2]), yaw=_wrap_angle(float(self.data.qpos[qyaw]))),
            velocity=Vec3(x=float(xvel), y=float(yvel), z=0),
            speed=round(float(math.hypot(xvel, yvel)), 3),
            target=target,
            priority=runtime.priority,
            task=runtime.task,
            status=runtime.status,
            massKg=runtime.config.mass_kg,
            route=list(runtime.route),
            idleMs=runtime.idle_ms,
            completedTasks=runtime.completed_tasks,
        )

    def _aircraft_snapshot(self, runtime: AircraftRuntime) -> PhysicsAircraft:
        eta = self._eta_to_threshold_ms(runtime)
        return PhysicsAircraft(
            id=runtime.config.id,
            callsign=runtime.config.callsign,
            modelKey=runtime.config.model_key,
            phase=runtime.phase,
            status=runtime.status,
            pose=Pose3D(x=runtime.x, y=runtime.y, z=runtime.z, yaw=runtime.yaw),
            velocity=Vec3(
                x=math.cos(runtime.yaw) * runtime.speed_mps,
                y=math.sin(runtime.yaw) * runtime.speed_mps,
                z=0,
            ),
            speed=round(runtime.speed_mps, 3),
            altitudeFt=max(0, round(runtime.z * 650)),
            etaRunwayMs=eta,
            runway=runtime.config.runway,
            clearance=runtime.clearance,
            priority=runtime.config.priority,
            risk=runtime.risk,
        )

    def _contacts(self) -> list[PhysicsContact]:
        contacts: list[PhysicsContact] = []
        vehicle_ids = {vehicle.config.id for vehicle in self.vehicles.values()}
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            names = []
            for geom_id in (contact.geom1, contact.geom2):
                geom_name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id)) or ""
                names.append(geom_name.split("_chassis")[0].split("_wheel")[0].split("_sensor")[0])
            if names[0] in vehicle_ids and names[1] in vehicle_ids and names[0] != names[1]:
                contacts.append(
                    PhysicsContact(
                        a=names[0],
                        b=names[1],
                        impulse=max(0.0, -float(contact.dist) * 1000),
                        distance=round(float(contact.dist), 4),
                    )
                )
        return contacts[:12]

    def _update_metrics(self, contacts: list[PhysicsContact] | None = None) -> None:
        if contacts is None:
            contacts = self._contacts()
        self.metrics.contact_count = len(contacts)
        self.metrics.fleet_throughput = sum(vehicle.completed_tasks for vehicle in self.vehicles.values())
        aircraft_risk = max((aircraft.risk for aircraft in self.aircraft.values()), default=0)
        active_aircraft = sum(1 for aircraft in self.aircraft.values() if aircraft.phase not in ("taxi_clear",))
        aircraft_delay = sum(aircraft.delay_ms for aircraft in self.aircraft.values())
        if self.incident == "runway_incursion":
            eta = self._eta_to_threshold_ms(self.aircraft["nasa742"])
            if eta is not None and eta < 2200 and self._runway_occupied():
                aircraft_risk = max(aircraft_risk, 84)
            if any(rule.zone == "runway_27" and rule.rule == "stale_conflict" for rule in self.active_rules):
                aircraft_risk = max(aircraft_risk, 95)
        self.metrics.runway_incursion_risk = max(0, min(100, aircraft_risk))
        self.metrics.aircraft_delay_ms = max(self.metrics.aircraft_delay_ms, aircraft_delay)
        self.metrics.active_aircraft = active_aircraft
        self.metrics.challenge_load = (
            len(self.active_rules) * 16
            + len(self.blocked_zones) * 14
            + self.metrics.congestion_pressure * 9
            + (28 if self.incident == "compound_incursion" else 0)
            + (42 if self.incident == "runway_incursion" else 0)
            + round(self.metrics.runway_incursion_risk * 0.6)
            + active_aircraft * 8
        )
        kinetic = 0.0
        for runtime in self.vehicles.values():
            kinetic += 0.5 * runtime.config.mass_kg * runtime.speed * runtime.speed
        self.metrics.kinetic_energy_j = kinetic


class PhysicsManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seed = 42
        self._sessions: dict[ProviderName, MuJoCoAirportSimulation] = {
            "baseline": MuJoCoAirportSimulation("baseline", self._seed),
            "cerebras": MuJoCoAirportSimulation("cerebras", self._seed),
        }

    def reset(self, seed: int = 42) -> dict[ProviderName, PhysicsSnapshot]:
        with self._lock:
            self._seed = seed
            self._sessions = {
                "baseline": MuJoCoAirportSimulation("baseline", seed),
                "cerebras": MuJoCoAirportSimulation("cerebras", seed),
            }
            return self.snapshots()

    def step(self, dt_ms: int, running: bool = True) -> dict[ProviderName, PhysicsSnapshot]:
        with self._lock:
            return {
                pane: session.step(dt_ms, running=running)
                for pane, session in self._sessions.items()
            }

    def trigger_incident(self, incident: IncidentName) -> dict[ProviderName, PhysicsSnapshot]:
        with self._lock:
            for session in self._sessions.values():
                session.trigger_incident(incident)
            return self.snapshots()

    def apply_policy(
        self,
        pane: ProviderName,
        policy: CoordinationPolicy,
        timing: TimingMetrics,
        requested_at_sim_ms: int,
        mode: str,
        model_name: str,
    ) -> PhysicsSnapshot:
        with self._lock:
            session = self._sessions[pane]
            session.apply_policy(policy, timing, requested_at_sim_ms, mode, model_name)
            return session.snapshot()

    def snapshots(self) -> dict[ProviderName, PhysicsSnapshot]:
        return {pane: session.snapshot() for pane, session in self._sessions.items()}

    def model_xml(self) -> str:
        return model_xml()


physics_manager = PhysicsManager()
