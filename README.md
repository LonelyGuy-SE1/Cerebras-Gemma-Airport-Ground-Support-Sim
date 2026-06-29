# Airport Ground Support Simulator

Sub-second AI coordination for runway incursions and autonomous airport operations.

Airport Ground Support Simulator is a local web simulation of airport runway and apron operations. A MuJoCo physics twin models ground vehicles, planar joints, masses, contact geometry, deterministic route controllers, and a live aircraft-state layer for short-final, departure, missed-approach, and runway-crossing traffic. A multimodal coordination model intervenes during semantic disruptions such as runway incursions, medical emergencies, fuel leaks, lane blockages, and priority arrivals.

The app demonstrates why response latency matters in physical operations: both panes start from the same seeded scenario, but the slow baseline may return a coordination policy after the airport state has already changed. The fast coordinator can apply a policy while it is still synchronized with the world.

## Features

- Side-by-side seeded simulation panes.
- MuJoCo-backed simulation state with a 20ms integration timestep, rigid vehicle bodies, contact reporting, kinetic energy, and deterministic seeded resets.
- Three.js 3D operations view with a marked runway, taxiways, approach lights, ATC tower, NASA aircraft GLB models, runway-risk overlays, vehicle trails, and live telemetry.
- Multi-aircraft ATC crisis: DC-8 short final, G-III departure queue, missed-approach traffic, runway crossing traffic, and fuel/ground support conflicts.
- Autonomous service vehicles: fuel truck, baggage cart, catering truck, passenger bus, pushback tractor, maintenance van, ambulance, and security vehicle.
- High-level semantic policies for go-around, cancel takeoff, expedite runway crossing, holding, yielding, rerouting, blocking zones, and priority routing.
- Real OpenAI-compatible provider calls when API keys are configured.
- Deterministic simulated/fallback policies when keys are absent or provider calls fail.
- One-click **Run 60s Demo** mode with final comparison card.

## Setup

Backend:

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

On hybrid Intel/NVIDIA laptops, launch the browser with PRIME offload so the
Three.js runway scene uses the dGPU:

```bash
cd frontend
npm run open:dgpu
```

The in-scene MuJoCo plaque shows the WebGL GPU family (`GPU NVIDIA`, `GPU Intel`,
or `GPU software`) so you can verify the browser picked the right adapter. The
launcher opens a separate dGPU browser profile, passes the detected NVIDIA
render node, and uses Chromium's X11/ANGLE path to avoid reuse of an
already-open Intel-backed browser process.

## Environment

Copy `.env.example` to `.env` and add keys as needed.

If no baseline key is configured, the app uses a configurable slow simulated baseline. If no Cerebras key is configured, the app uses a clearly labeled fast simulated coordinator so the local demo remains reproducible.

## Demo Mode

Click **Run 60s Demo**. The app resets both panes to the same seed, runs normal airport movement, triggers a runway incursion with a DC-8 on short final, crossing traffic on the runway, a G-III departure queue, and fuel/ground-support hazards, captures each pane's rendered frame and telemetry, calls both coordinators, and shows the policy timing impact in live metrics.

The slow baseline intentionally applies policy against an older MuJoCo state. The UI surfaces this as policy staleness, runway incursion risk, aircraft delay, deadlock duration, turnaround delay, and stale conflict zones.

The final card compares:

- latency gap scored by MuJoCo
- validity-window consumption
- runway risk
- aircraft delay

## Architecture

- `frontend/`: Vite + React + TypeScript with an imperative Three.js scene renderer.
- `backend/`: FastAPI API for health checks, MuJoCo physics stepping, incident injection, policy application, and model coordination.
- `schemas/`: JSON schema for coordination policies.
- `shared/scenarios/`: deterministic scenario metadata.
- `docs/`: architecture notes and recording script.

The model is asked to produce high-level policy only. MuJoCo remains the source of physical ground state, while deterministic local controllers handle vehicle motion, yielding, rerouting, contact-aware congestion, aircraft state, runway risk, and ATC clearance consequences.

NASA aircraft assets are stored in `frontend/public/assets/nasa-aircraft/` with attribution.

The active MJCF model is exposed locally at:

```bash
curl http://localhost:8000/api/physics/model
```
