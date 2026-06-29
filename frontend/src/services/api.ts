import type { CoordinationPolicy, CoordinatorTiming, PaneKind, PhysicsSnapshot } from "../physics/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  providers: Record<
    string,
    {
      configured: boolean;
      model: string;
      base_url: string;
      simulated_delay_ms: number;
    }
  >;
}

export interface CoordinateResponse {
  provider: PaneKind;
  mode: "live" | "simulated" | "fallback_after_error";
  model: string;
  policy: CoordinationPolicy;
  timing: CoordinatorTiming;
  rawSummary: string;
  error: string | null;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
  return response.json() as Promise<HealthResponse>;
}

export async function coordinatePolicy(input: {
  provider: PaneKind;
  incident: string;
  telemetry: PhysicsSnapshot;
  frameDataUrl: string | null;
  scenarioSeed: number;
  forceSimulated: boolean;
}): Promise<CoordinateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/coordinate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Coordinator failed: ${response.status} ${body.slice(0, 200)}`);
  }
  return response.json() as Promise<CoordinateResponse>;
}
