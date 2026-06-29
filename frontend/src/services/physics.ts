import type { CoordinationPolicy, IncidentType, PaneKind, PhysicsSnapshot, PhysicsSnapshots, CoordinatorTiming } from "../physics/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${path} failed: ${response.status} ${text.slice(0, 200)}`);
  }
  return response.json() as Promise<T>;
}

export function resetPhysics(seed = 42): Promise<PhysicsSnapshots> {
  return postJson<PhysicsSnapshots>("/api/physics/reset", { seed });
}

export function stepPhysics(dtMs: number, running: boolean): Promise<PhysicsSnapshots> {
  return postJson<PhysicsSnapshots>("/api/physics/step", { dtMs, running });
}

export function triggerPhysicsIncident(incident: IncidentType): Promise<PhysicsSnapshots> {
  return postJson<PhysicsSnapshots>("/api/physics/incident", { incident });
}

export function applyPhysicsPolicy(input: {
  pane: PaneKind;
  policy: CoordinationPolicy;
  timing: CoordinatorTiming;
  requestedAtSimMs: number;
  mode: "live" | "simulated" | "fallback_after_error";
  model: string;
}): Promise<PhysicsSnapshot> {
  return postJson<PhysicsSnapshot>("/api/physics/apply-policy", input);
}
