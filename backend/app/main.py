from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.coordinator import coordinate
from app.models import (
    CoordinateRequest,
    CoordinateResponse,
    HealthResponse,
    PhysicsApplyPolicyRequest,
    PhysicsIncidentRequest,
    PhysicsResetRequest,
    PhysicsSnapshot,
    PhysicsStepRequest,
)
from app.physics import physics_manager


app = FastAPI(title="Airport Ground Support Simulator API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthResponse)
async def root() -> HealthResponse:
    return await health()


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        providers={
            "cerebras": {
                "configured": settings.cerebras.configured,
                "model": settings.cerebras.model,
                "base_url": settings.cerebras.base_url,
                "simulated_delay_ms": settings.cerebras.simulated_delay_ms,
            },
            "baseline": {
                "configured": settings.baseline.configured,
                "model": settings.baseline.model,
                "base_url": settings.baseline.base_url,
                "simulated_delay_ms": settings.baseline.simulated_delay_ms,
            },
        },
        simulator={"engine": "mujoco", "configured": True},
    )


@app.post("/api/coordinate", response_model=CoordinateResponse)
async def coordinate_policy(request: CoordinateRequest) -> CoordinateResponse:
    return await coordinate(request)


@app.post("/api/physics/reset", response_model=dict[str, PhysicsSnapshot])
async def reset_physics(request: PhysicsResetRequest) -> dict[str, PhysicsSnapshot]:
    return physics_manager.reset(request.seed)


@app.post("/api/physics/step", response_model=dict[str, PhysicsSnapshot])
async def step_physics(request: PhysicsStepRequest) -> dict[str, PhysicsSnapshot]:
    return physics_manager.step(request.dt_ms, running=request.running)


@app.post("/api/physics/incident", response_model=dict[str, PhysicsSnapshot])
async def trigger_physics_incident(request: PhysicsIncidentRequest) -> dict[str, PhysicsSnapshot]:
    return physics_manager.trigger_incident(request.incident)


@app.post("/api/physics/apply-policy", response_model=PhysicsSnapshot)
async def apply_physics_policy(request: PhysicsApplyPolicyRequest) -> PhysicsSnapshot:
    return physics_manager.apply_policy(
        request.pane,
        request.policy,
        request.timing,
        request.requested_at_sim_ms,
        request.mode,
        request.model,
    )


@app.get("/api/physics/model", response_model=dict[str, str])
async def get_physics_model() -> dict[str, str]:
    return {"format": "mjcf", "engine": "mujoco", "xml": physics_manager.model_xml()}
