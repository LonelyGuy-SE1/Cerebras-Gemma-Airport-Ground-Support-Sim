from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderName = Literal["baseline", "cerebras"]
CoordinatorMode = Literal["live", "simulated", "fallback_after_error"]
IncidentName = Literal[
    "medical_emergency",
    "fuel_leak",
    "vehicle_breakdown",
    "vip_arrival",
    "compound_incursion",
    "runway_incursion",
]


class PolicyAction(BaseModel):
    vehicle_id: str = Field(..., min_length=1)
    directive: str = Field(..., min_length=1)
    duration_ms: int | None = Field(default=None, ge=0)
    waypoint: str | None = None
    zone: str | None = None
    target: str | None = None
    reason: str | None = None


class TemporaryRule(BaseModel):
    zone: str = Field(..., min_length=1)
    rule: str = Field(..., min_length=1)
    duration_ms: int = Field(..., ge=0)


class CoordinationPolicy(BaseModel):
    incident: str
    priority_vehicle: str
    actions: list[PolicyAction]
    temporary_rules: list[TemporaryRule] = Field(default_factory=list)
    summary: str
    confidence: float = Field(default=0.86, ge=0, le=1)


class CoordinateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: ProviderName
    incident: str
    telemetry: dict[str, Any]
    frame_data_url: str | None = Field(default=None, alias="frameDataUrl")
    scenario_seed: int = Field(default=42, alias="scenarioSeed")
    force_simulated: bool = Field(default=False, alias="forceSimulated")


class TimingMetrics(BaseModel):
    latency_ms: int = Field(default=0, alias="latencyMs")
    ttft_ms: int | None = Field(default=None, alias="ttftMs")
    tokens_per_second: float | None = Field(default=None, alias="tokensPerSecond")
    prompt_tokens: int | None = Field(default=None, alias="promptTokens")
    completion_tokens: int | None = Field(default=None, alias="completionTokens")
    total_tokens: int | None = Field(default=None, alias="totalTokens")


class CoordinateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: ProviderName
    mode: CoordinatorMode
    model: str
    policy: CoordinationPolicy
    timing: TimingMetrics
    raw_summary: str = Field(alias="rawSummary")
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    providers: dict[str, dict[str, str | bool | int]]
    simulator: dict[str, str | bool] = Field(default_factory=dict)


class Vec3(BaseModel):
    x: float
    y: float
    z: float = 0.0


class Pose3D(BaseModel):
    x: float
    y: float
    z: float
    yaw: float


class PhysicsVehicle(BaseModel):
    id: str
    label: str
    kind: str
    pose: Pose3D
    velocity: Vec3
    speed: float
    target: str
    priority: int
    task: str
    status: str
    mass_kg: float = Field(alias="massKg")
    route: list[str]
    idle_ms: int = Field(alias="idleMs")
    completed_tasks: int = Field(alias="completedTasks")


class PhysicsAircraft(BaseModel):
    id: str
    callsign: str
    model_key: str = Field(alias="modelKey")
    phase: str
    status: str
    pose: Pose3D
    velocity: Vec3
    speed: float
    altitude_ft: int = Field(alias="altitudeFt")
    eta_runway_ms: int | None = Field(alias="etaRunwayMs")
    runway: str
    clearance: str
    priority: int
    risk: int


class PhysicsRule(BaseModel):
    zone: str
    rule: str
    expires_at_ms: int = Field(alias="expiresAtMs")


class PhysicsContact(BaseModel):
    a: str
    b: str
    impulse: float
    distance: float


class PhysicsMetrics(BaseModel):
    llm_latency_ms: int = Field(default=0, alias="llmLatencyMs")
    policy_staleness: int = Field(default=0, alias="policyStaleness")
    turnaround_delay_ms: int = Field(default=0, alias="turnaroundDelayMs")
    vehicle_idle_ms: int = Field(default=0, alias="vehicleIdleMs")
    conflicts_avoided: int = Field(default=0, alias="conflictsAvoided")
    emergency_response_ms: int | None = Field(default=None, alias="emergencyResponseMs")
    fleet_throughput: int = Field(default=0, alias="fleetThroughput")
    interventions: int = 0
    deadlock_duration_ms: int = Field(default=0, alias="deadlockDurationMs")
    congestion_pressure: int = Field(default=0, alias="congestionPressure")
    contact_count: int = Field(default=0, alias="contactCount")
    kinetic_energy_j: float = Field(default=0, alias="kineticEnergyJ")
    validity_window_ms: int = Field(default=1800, alias="validityWindowMs")
    validity_consumed_pct: int = Field(default=0, alias="validityConsumedPct")
    challenge_load: int = Field(default=0, alias="challengeLoad")
    runway_incursion_risk: int = Field(default=0, alias="runwayIncursionRisk")
    aircraft_delay_ms: int = Field(default=0, alias="aircraftDelayMs")
    active_aircraft: int = Field(default=0, alias="activeAircraft")


class PhysicsSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pane: ProviderName
    seed: int
    sim_time_ms: int = Field(alias="simTimeMs")
    physics_engine: str = Field(alias="physicsEngine")
    timestep_ms: int = Field(alias="timestepMs")
    incident: IncidentName | None
    incident_started_at_ms: int | None = Field(alias="incidentStartedAtMs")
    priority_vehicle_id: str | None = Field(alias="priorityVehicleId")
    vehicles: list[PhysicsVehicle]
    aircraft: list[PhysicsAircraft] = Field(default_factory=list)
    active_rules: list[PhysicsRule] = Field(alias="activeRules")
    blocked_zones: list[str] = Field(alias="blockedZones")
    contacts: list[PhysicsContact]
    metrics: PhysicsMetrics
    last_policy_summary: str = Field(alias="lastPolicySummary")
    last_coordinator_mode: CoordinatorMode | Literal["idle"] = Field(alias="lastCoordinatorMode")
    last_coordinator_model: str = Field(alias="lastCoordinatorModel")
    last_timing: TimingMetrics | None = Field(alias="lastTiming")
    waypoints: dict[str, Vec3]
    zones: dict[str, dict[str, float | str]]


class PhysicsResetRequest(BaseModel):
    seed: int = 42


class PhysicsStepRequest(BaseModel):
    dt_ms: int = Field(default=50, alias="dtMs", ge=10, le=10000)
    running: bool = True


class PhysicsIncidentRequest(BaseModel):
    incident: IncidentName


class PhysicsApplyPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pane: ProviderName
    policy: CoordinationPolicy
    timing: TimingMetrics
    requested_at_sim_ms: int = Field(alias="requestedAtSimMs")
    mode: CoordinatorMode
    model: str
