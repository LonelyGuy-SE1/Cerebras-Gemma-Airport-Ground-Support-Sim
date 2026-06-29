You are Codex 5.5 xhigh acting as a senior full-stack systems engineer, product designer, and hackathon execution lead.

Build a complete, demo-ready project for the Cerebras x Google DeepMind Gemma 4 Hackathon.

Project name: Airport Ground Support Simulator

Subtitle: Zero-Latency Semantic Ground Control for Autonomous Airport Operations

Core thesis:
Airport Ground Support Simulator demonstrates that ultra-fast inference enables a new control paradigm for physical AI. In a dynamic airport apron simulation, local planners handle normal vehicle movement, but when a semantic disruption occurs, Gemma 4 31B on Cerebras acts as a real-time ground operations coordinator. A slower GPU-backed model returns stale decisions after the world has already changed. Cerebras responds fast enough for the coordination policy to remain valid.

Hackathon requirements:

* Target Track 1: Multiverse Agents.
* Must show multi-agent coordination.
* Must use Gemma 4 31B on Cerebras as the central model.
* Must use multimodal input: rendered simulation image plus structured telemetry.
* Must clearly demonstrate Cerebras speed improving the experience.
* Must support a side-by-side comparison against a slower baseline provider or simulated slower model.
* Demo video must be under 60 seconds, so the app must have a polished “Demo Mode.”

Product:
A web-based airport ground operations simulator.

Visual environment:

* Top-down or isometric airport apron.
* One or more aircraft at gates.
* Autonomous service vehicles:

  * fuel truck
  * baggage cart
  * catering truck
  * passenger bus
  * pushback tractor
  * maintenance van
  * ambulance/emergency vehicle
  * security vehicle
* Vehicles move continuously using deterministic local pathfinding.
* Add roads, taxiway markings, gates, no-go zones, runway/taxiway edges, service lanes.
* Use a premium visual design, not generic Tailwind cards.
* The UI should feel like an operations control room at NVIDIA GTC or Hannover Messe.
* Include smooth animation, clear typography, dark industrial theme, subtle glow effects, map overlays, priority badges, vehicle trails, and live telemetry.
* Avoid stock-looking dashboards.

Core simulation:

* Deterministic local planner for each vehicle.
* Vehicles have position, target, velocity, priority, task, status, and route.
* The world continues moving even while an AI request is pending.
* Add scenario events:

  1. Medical emergency: ambulance must reach aircraft immediately.
  2. Fuel leak: fuel truck must pause and safety corridor opens.
  3. Vehicle breakdown: one service lane becomes blocked.
  4. VIP aircraft arrival: priority routing changes.
* Local pathfinding alone should produce congestion or poor behavior under disruptions.
* Airport Ground Support Simulator should call the semantic coordinator only when disruption or congestion is detected.

LLM role:
The LLM must not compute raw paths.
The LLM computes high-level semantic coordination policies.

Example policy:
{
"incident": "medical_emergency",
"priority_vehicle": "ambulance_1",
"actions": [
{"vehicle_id": "fuel_1", "directive": "hold_position", "duration_ms": 4000},
{"vehicle_id": "baggage_2", "directive": "reroute_via", "waypoint": "service_lane_north"},
{"vehicle_id": "security_1", "directive": "block_zone", "zone": "taxiway_crossing_c"},
{"vehicle_id": "passenger_bus_1", "directive": "yield_to", "target": "ambulance_1"}
],
"temporary_rules": [
{"zone": "service_lane_east", "rule": "emergency_only", "duration_ms": 6000}
],
"summary": "Clear eastern service lane for ambulance access while delaying non-critical ground services."
}

Cerebras integration:

* Use OpenAI-compatible Chat Completions API.
* Model ID: gemma-4-31b.
* Environment variables:

  * CEREBRAS_API_KEY
  * BASELINE_API_KEY optional
  * BASELINE_BASE_URL optional
  * BASELINE_MODEL optional
* Support image input as Base64 data URI.
* Send both:

  1. current rendered frame
  2. structured telemetry JSON
* Use structured outputs / JSON schema if supported.
* Use reasoning_effort: low for fast reflexive coordination.
* Capture and display response timing:

  * TTFT if available
  * end-to-end latency
  * tokens/sec if available
  * prompt/completion tokens
* Gracefully handle API failure with a deterministic fallback policy.

Baseline comparison:
Implement two panes:

* Left: Baseline model or “slow provider simulation.”
* Right: Cerebras Gemma 4.

Both panes start from the exact same seeded scenario.

In baseline mode:

* If no baseline API is configured, simulate latency using a configurable delay such as 2500 ms.
* During the delay, the world must continue moving.
* When the policy arrives, it should often be stale, showing congestion, conflict, or lower throughput.

In Cerebras mode:

* Use actual Cerebras API if key exists.
* If no key exists, allow demo fallback with configurable low latency, but clearly label it as simulated.
* Apply policy quickly and visibly resolve the disruption.

Metrics:
Show live metrics for both panes:

* LLM latency
* policy staleness score
* aircraft turnaround delay
* vehicle idle time
* conflicts avoided
* emergency response time
* fleet throughput
* number of policy interventions
* deadlock/congestion duration

Demo Mode:
Add a one-click “Run 60s Demo” button.
It should:

1. Start identical simulations side by side.
2. Run normal apron operations.
3. Trigger a medical emergency.
4. Capture both panes’ visual frame and telemetry.
5. Send to baseline and Cerebras.
6. Show baseline waiting while world changes.
7. Show Cerebras resolving the situation immediately.
8. Display final comparison metrics.
9. Present a final title card:
   “Cerebras keeps the policy synchronized with reality. Slow inference returns decisions for a world that no longer exists.”

Architecture:
Use a clean, minimal, production-grade stack.
Recommended:

* frontend: Vite + React + TypeScript
* rendering: Canvas or PixiJS, whichever is faster to implement cleanly
* backend: FastAPI + Python
* package management: uv preferred for Python
* environment: local venv
* no unnecessary cloud dependencies
* no database unless absolutely needed
* no auth
* no bloated framework sprawl

Repository expectations:

* Create the full project structure.
* Include README.md with:

  * project pitch
  * setup instructions
  * environment variables
  * how to run demo mode
  * hackathon track alignment
  * architecture
  * how Cerebras speed is demonstrated
* Include .env.example.
* Include .gitignore.
* Include LICENSE, preferably Apache-2.0.
* Include a short demo script in docs/demo_script.md for a 60-second recording.
* Include docs/architecture.md.
* Include sample JSON policy schemas.
* Include deterministic seeded demo scenarios.

Coding standards:

* TypeScript strict mode.
* Python type hints.
* Clear module boundaries.
* No hardcoded secrets.
* Configurable delays, model IDs, API endpoints, simulation seed, vehicle count, event type, and demo timing.
* Robust error handling.
* No fake claims in the UI: label simulated metrics when using fallback.
* Keep code readable and shippable within 24 hours.
* Prefer simple, reliable implementation over clever abstractions.

Execution environment:

* Create everything inside the repo.
* Use a Python venv or uv-managed environment.
* It is acceptable to install npm packages and Python packages as needed.
* Keep generated junk out of git.
* The project should be easy to delete after pushing to GitHub.

Final deliverable:
A working local app where I can run:

Backend:
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload

Frontend:
cd frontend
npm install
npm run dev

Or provide a simpler single-command dev script if possible.

Do not stop at scaffolding.
Implement the complete working demo.
Prioritize:

1. polished visual simulation
2. side-by-side speed contrast
3. real Cerebras API path
4. demo mode
5. clean README and demo script

After building, run the app or at least run type checks/lint/build where possible, fix errors, and summarize only:

* what was built
* how to run it
* any missing API keys needed
* what to record for the hackathon demo
