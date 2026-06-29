# Architecture

Airport Ground Support Simulator is a local two-part application:

- `frontend/`: Vite, React, TypeScript, and Three.js rendering.
- `backend/`: FastAPI service that owns MuJoCo simulation state, normalizes provider calls, and returns coordination policies.

The backend owns the deterministic physical simulation loop. Each pane is an independent MuJoCo session initialized from the same MJCF model and seed. The model includes a runway/taxiway field, service lanes, no-go zones, vehicle rigid bodies, planar slide/hinge joints, masses, contact geoms, and a 20ms integration timestep. A deterministic aircraft-state layer runs beside MuJoCo for short-final, departure, missed-approach, and runway-crossing aircraft because the demo needs ATC conflict timing as well as ground contact dynamics.

The frontend is a renderer and operator console. It streams snapshots from the backend and renders them as two synchronized Three.js airport twins. It captures the WebGL frame as a Base64 data URI when coordinator calls are triggered.

The backend also owns semantic coordination. It receives the rendered frame plus structured MuJoCo telemetry, calls an OpenAI-compatible chat completions endpoint when configured, or returns a deterministic fallback policy when a provider key is missing or a request fails.

## Coordinator Contract

The model returns high-level operational policy, not raw path geometry. Supported directives:

- `hold_position`
- `reroute_via`
- `yield_to`
- `block_zone`
- `priority_route`
- `go_around`
- `clear_land`
- `cancel_takeoff`
- `line_up_and_wait`
- `expedite_crossing`

The backend applies those directives to MuJoCo route-controller state and aircraft state, then continues deterministic movement. Policy application can hold vehicles, reroute through semantic waypoints, yield to a priority vehicle or aircraft, block zones, close a runway, issue a go-around, cancel takeoff, expedite a crossing, or set temporary rules such as emergency-only access.

## Physics Endpoints

- `POST /api/physics/reset`: reset both MuJoCo twins to a deterministic seed.
- `POST /api/physics/step`: advance both twins by a requested simulation delta.
- `POST /api/physics/incident`: inject a semantic disruption into both twins.
- `POST /api/physics/apply-policy`: apply a coordination policy to one twin.
- `GET /api/physics/model`: return the active MJCF model XML.

The UI displays physical metrics from the twin sessions: contact count, kinetic energy, vehicle idle time, runway incursion risk, aircraft delay, deadlock duration, turnaround delay, policy staleness, and emergency response time.

## Provider Modes

- Cerebras: primary fast coordinator using `gemma-4-31b`.
- Baseline: optional OpenAI-compatible provider, defaulting to OpenRouter when configured.
- Simulated: deterministic policy with configurable delay for reliable side-by-side demos.

The UI labels whether each response was live, simulated, or a fallback after provider error.
