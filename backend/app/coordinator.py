from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import ProviderSettings, get_settings
from app.models import CoordinateRequest, CoordinateResponse, CoordinationPolicy, TimingMetrics
from app.policy import POLICY_JSON_SCHEMA, deterministic_policy


SYSTEM_PROMPT = """You are a semantic airport ATC and ground operations coordinator for a MuJoCo airport twin.
You receive a rendered frame plus structured physics telemetry: aircraft/vehicle poses, velocities, altitude,
ETA to runway, mass, active rules, contact/congestion metrics, current incident, and live operational constraints.

Return only a high-level coordination policy as JSON. Do not compute raw geometry or point-by-point paths.
Use directives such as hold_position, reroute_via, yield_to, block_zone, priority_route, go_around,
cancel_takeoff, expedite_crossing, line_up_and_wait, and clear_land.

This is a reflex coordination task. Assume the policy validity window is about 3000 ms. If you over-block the
apron, throughput collapses; if you under-block, the ambulance or hazard perimeter conflicts with active traffic.
For runway incursions, rank landing safety first, runway surface separation second, departure queue control third,
and ground throughput last. For compound incidents, rank life-safety first, hazard isolation second, aircraft
movement third, and routine turnaround last. Prefer decisive, short-lived policies that preserve one safe runway
or sterile corridor instead of freezing the entire airport. Keep the JSON compact: short directives, short reasons,
no prose outside the object."""


def _provider_for(name: str) -> ProviderSettings:
    settings = get_settings()
    return settings.cerebras if name == "cerebras" else settings.baseline


def _provider_headers(provider: ProviderSettings) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in provider.base_url:
        headers["HTTP-Referer"] = "http://localhost:5173"
        headers["X-Title"] = "Airport Ground Support Simulator"
    return headers


def _chat_url(provider: ProviderSettings) -> str:
    return provider.base_url.rstrip("/") + "/chat/completions"


def _compact_telemetry(telemetry: dict[str, Any]) -> str:
    return json.dumps(telemetry, separators=(",", ":"), ensure_ascii=True)[:9000]


def _cardinal_from_yaw(yaw: float) -> str:
    degrees = (yaw * 180 / 3.141592653589793) % 360
    names = ("east", "northeast", "north", "northwest", "west", "southwest", "south", "southeast")
    return names[int((degrees + 22.5) // 45) % 8]


def _traffic_vector_summary(telemetry: dict[str, Any]) -> str:
    lines: list[str] = []
    for aircraft in telemetry.get("aircraft", [])[:6]:
        pose = aircraft.get("pose") or {}
        yaw = float(pose.get("yaw") or 0)
        lines.append(
            "air "
            f"{aircraft.get('id')} {aircraft.get('phase')} {aircraft.get('status')} "
            f"pos=({float(pose.get('x') or 0):.1f},{float(pose.get('y') or 0):.1f},{float(pose.get('z') or 0):.1f}) "
            f"heading={round((yaw * 180 / 3.141592653589793) % 360)}deg-{_cardinal_from_yaw(yaw)} "
            f"speed={float(aircraft.get('speed') or 0):.1f} etaMs={aircraft.get('etaRunwayMs')} "
            f"clearance={aircraft.get('clearance')} risk={aircraft.get('risk')}"
        )
    for vehicle in telemetry.get("vehicles", [])[:10]:
        pose = vehicle.get("pose") or {}
        yaw = float(pose.get("yaw") or 0)
        route = vehicle.get("route") or []
        lines.append(
            "veh "
            f"{vehicle.get('id')} {vehicle.get('kind')} {vehicle.get('status')} "
            f"pos=({float(pose.get('x') or 0):.1f},{float(pose.get('y') or 0):.1f}) "
            f"heading={round((yaw * 180 / 3.141592653589793) % 360)}deg-{_cardinal_from_yaw(yaw)} "
            f"speed={float(vehicle.get('speed') or 0):.1f} target={vehicle.get('target')} "
            f"route={'->'.join(str(item) for item in route[:4])}"
        )
    return "\n".join(lines)


def _build_body(
    request: CoordinateRequest,
    provider: ProviderSettings,
    strict: bool = True,
    include_frame: bool = True,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Incident: {request.incident}\n"
                f"Scenario seed: {request.scenario_seed}\n"
                "Decision challenge: choose a policy that remains valid within a short physical-world window. "
                "Late or overbroad policies cause stale-conflict penalties in the MuJoCo twin.\n"
                "Live traffic vectors with headings, direction, speed, targets, and clearances:\n"
                f"{_traffic_vector_summary(request.telemetry)}\n"
                "Telemetry JSON:\n"
                f"{_compact_telemetry(request.telemetry)}"
            ),
        }
    ]
    if include_frame and request.frame_data_url:
        content.append({"type": "image_url", "image_url": {"url": request.frame_data_url}})

    body: dict[str, Any] = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.0,
        "max_tokens": 360,
        "reasoning_effort": "low",
    }
    if strict:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "ground_coordination_policy",
                "strict": True,
                "schema": POLICY_JSON_SCHEMA,
            },
        }
    return body


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _parse_policy(content: str, incident: str, telemetry: dict[str, Any]) -> CoordinationPolicy:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
        return CoordinationPolicy.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return deterministic_policy(incident, telemetry)


def _timing_from_payload(payload: dict[str, Any], latency_ms: int) -> TimingMetrics:
    usage = payload.get("usage") or {}
    time_info = payload.get("time_info") or payload.get("timing") or {}
    completion_tokens = usage.get("completion_tokens")
    tokens_per_second = None
    if completion_tokens and latency_ms > 0:
        tokens_per_second = round(float(completion_tokens) / (latency_ms / 1000), 2)
    ttft = (
        time_info.get("time_to_first_token")
        or time_info.get("ttft")
        or time_info.get("ttft_ms")
        or time_info.get("timeToFirstTokenMs")
    )
    if isinstance(ttft, float) and ttft < 100:
        ttft = int(ttft * 1000)
    return TimingMetrics(
        latencyMs=latency_ms,
        ttftMs=int(ttft) if isinstance(ttft, int | float) else None,
        tokensPerSecond=tokens_per_second,
        promptTokens=usage.get("prompt_tokens"),
        completionTokens=completion_tokens,
        totalTokens=usage.get("total_tokens"),
    )


async def _live_completion(request: CoordinateRequest, provider: ProviderSettings) -> tuple[CoordinationPolicy, TimingMetrics, str]:
    timeout = httpx.Timeout(30.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        started = time.perf_counter()
        attempts = [(True, True), (False, True)]
        if request.frame_data_url:
            attempts.extend([(True, False), (False, False)])

        response: httpx.Response | None = None
        for strict, include_frame in attempts:
            body = _build_body(request, provider, strict=strict, include_frame=include_frame)
            if not strict:
                body.pop("reasoning_effort", None)
            response = await client.post(_chat_url(provider), headers=_provider_headers(provider), json=body)
            if response.status_code < 400:
                break
            if response.status_code not in {400, 422}:
                response.raise_for_status()

        if response is None:
            raise RuntimeError("Provider request was not attempted.")
        response.raise_for_status()
        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = response.json()
    content = _extract_content(payload)
    return _parse_policy(content, request.incident, request.telemetry), _timing_from_payload(payload, latency_ms), content[:600]


async def coordinate(request: CoordinateRequest) -> CoordinateResponse:
    provider = _provider_for(request.provider)
    if request.force_simulated or not provider.configured:
        await asyncio.sleep(provider.simulated_delay_ms / 1000)
        return CoordinateResponse(
            provider=request.provider,
            mode="simulated",
            model=provider.model,
            policy=deterministic_policy(request.incident, request.telemetry),
            timing=TimingMetrics(latencyMs=provider.simulated_delay_ms),
            rawSummary="Deterministic simulator policy; no provider key was used.",
        )

    try:
        policy, timing, raw_summary = await _live_completion(request, provider)
        return CoordinateResponse(
            provider=request.provider,
            mode="live",
            model=provider.model,
            policy=policy,
            timing=timing,
            rawSummary=raw_summary or policy.summary,
        )
    except Exception as exc:  # Provider failures should never break the demo.
        await asyncio.sleep(min(provider.simulated_delay_ms, 400) / 1000)
        return CoordinateResponse(
            provider=request.provider,
            mode="fallback_after_error",
            model=provider.model,
            policy=deterministic_policy(request.incident, request.telemetry),
            timing=TimingMetrics(latencyMs=provider.simulated_delay_ms),
            rawSummary="Provider request failed; deterministic fallback policy applied.",
            error=str(exc)[:500],
        )
