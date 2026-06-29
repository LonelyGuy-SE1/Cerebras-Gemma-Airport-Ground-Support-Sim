export type PaneKind = "baseline" | "cerebras";

export type IncidentType =
  | "medical_emergency"
  | "fuel_leak"
  | "vehicle_breakdown"
  | "vip_arrival"
  | "compound_incursion"
  | "runway_incursion";

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Pose3D {
  x: number;
  y: number;
  z: number;
  yaw: number;
}

export interface CoordinatorTiming {
  latencyMs: number;
  ttftMs: number | null;
  tokensPerSecond: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
}

export interface PolicyAction {
  vehicle_id: string;
  directive: "hold_position" | "reroute_via" | "yield_to" | "block_zone" | "priority_route" | string;
  duration_ms?: number | null;
  waypoint?: string | null;
  zone?: string | null;
  target?: string | null;
  reason?: string | null;
}

export interface TemporaryRule {
  zone: string;
  rule: string;
  duration_ms: number;
}

export interface CoordinationPolicy {
  incident: string;
  priority_vehicle: string;
  actions: PolicyAction[];
  temporary_rules: TemporaryRule[];
  summary: string;
  confidence: number;
}

export interface PhysicsVehicle {
  id: string;
  label: string;
  kind: string;
  pose: Pose3D;
  velocity: Vec3;
  speed: number;
  target: string;
  priority: number;
  task: string;
  status: string;
  massKg: number;
  route: string[];
  idleMs: number;
  completedTasks: number;
}

export interface PhysicsAircraft {
  id: string;
  callsign: string;
  modelKey: string;
  phase: string;
  status: string;
  pose: Pose3D;
  velocity: Vec3;
  speed: number;
  altitudeFt: number;
  etaRunwayMs: number | null;
  runway: string;
  clearance: string;
  priority: number;
  risk: number;
}

export interface PhysicsRule {
  zone: string;
  rule: string;
  expiresAtMs: number;
}

export interface PhysicsContact {
  a: string;
  b: string;
  impulse: number;
  distance: number;
}

export interface SimMetrics {
  llmLatencyMs: number;
  policyStaleness: number;
  turnaroundDelayMs: number;
  vehicleIdleMs: number;
  conflictsAvoided: number;
  emergencyResponseMs: number | null;
  fleetThroughput: number;
  interventions: number;
  deadlockDurationMs: number;
  congestionPressure: number;
  contactCount: number;
  kineticEnergyJ: number;
  validityWindowMs: number;
  validityConsumedPct: number;
  challengeLoad: number;
  runwayIncursionRisk: number;
  aircraftDelayMs: number;
  activeAircraft: number;
}

export interface PhysicsSnapshot {
  pane: PaneKind;
  seed: number;
  simTimeMs: number;
  physicsEngine: string;
  timestepMs: number;
  incident: IncidentType | null;
  incidentStartedAtMs: number | null;
  priorityVehicleId: string | null;
  vehicles: PhysicsVehicle[];
  aircraft: PhysicsAircraft[];
  activeRules: PhysicsRule[];
  blockedZones: string[];
  contacts: PhysicsContact[];
  metrics: SimMetrics;
  lastPolicySummary: string;
  lastCoordinatorMode: "live" | "simulated" | "fallback_after_error" | "idle";
  lastCoordinatorModel: string;
  lastTiming: CoordinatorTiming | null;
  waypoints: Record<string, Vec3>;
  zones: Record<string, { label: string; x: number; y: number; width: number; height: number }>;
}

export type PhysicsSnapshots = Record<PaneKind, PhysicsSnapshot>;
