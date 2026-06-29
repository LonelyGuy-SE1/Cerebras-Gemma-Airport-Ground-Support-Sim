from __future__ import annotations

from typing import Any

from app.models import CoordinationPolicy, PolicyAction, TemporaryRule


def deterministic_policy(incident: str, telemetry: dict[str, Any] | None = None) -> CoordinationPolicy:
    telemetry = telemetry or {}
    incident_key = incident.lower()

    if incident_key == "runway_incursion":
        return CoordinationPolicy(
            incident="runway_incursion",
            priority_vehicle="nasa742",
            actions=[
                PolicyAction(
                    vehicle_id="nasa742",
                    directive="go_around",
                    duration_ms=8500,
                    reason="Short-final DC-8 cannot safely continue with an active runway crossing.",
                ),
                PolicyAction(
                    vehicle_id="cargo612",
                    directive="expedite_crossing",
                    duration_ms=4200,
                    reason="Clear the active runway surface before the missed approach stabilizes.",
                ),
                PolicyAction(
                    vehicle_id="gulf3",
                    directive="cancel_takeoff",
                    duration_ms=7500,
                    reason="Departure queue must stay clear during the runway incursion.",
                ),
                PolicyAction(vehicle_id="security_1", directive="block_zone", zone="runway_crossing_27", duration_ms=6500),
                PolicyAction(vehicle_id="fuel_1", directive="hold_position", duration_ms=7600),
                PolicyAction(vehicle_id="passenger_bus_1", directive="hold_position", duration_ms=4200),
                PolicyAction(vehicle_id="ambulance_1", directive="reroute_via", waypoint="service_lane_north"),
            ],
            temporary_rules=[
                TemporaryRule(zone="runway_27", rule="runway_closed", duration_ms=6200),
                TemporaryRule(zone="runway_crossing_27", rule="crossing_lockout", duration_ms=7200),
                TemporaryRule(zone="final_27", rule="arrival_priority", duration_ms=8500),
                TemporaryRule(zone="departure_queue", rule="departure_hold", duration_ms=7600),
            ],
            summary="Issue immediate go-around, lock the runway crossing, hold the departure queue, and freeze fuel traffic.",
        )

    if incident_key == "compound_incursion":
        return CoordinationPolicy(
            incident="compound_incursion",
            priority_vehicle="ambulance_1",
            actions=[
                PolicyAction(vehicle_id="ambulance_1", directive="priority_route", waypoint="gate_alpha_medical"),
                PolicyAction(vehicle_id="fuel_1", directive="hold_position", duration_ms=8500, reason="Freeze fuel movement while the hazard perimeter is active."),
                PolicyAction(vehicle_id="security_1", directive="block_zone", zone="service_lane_east", duration_ms=6200),
                PolicyAction(vehicle_id="pushback_1", directive="hold_position", duration_ms=5200, reason="VIP movement yields to life-safety response."),
                PolicyAction(vehicle_id="passenger_bus_1", directive="yield_to", target="ambulance_1", duration_ms=7000),
                PolicyAction(vehicle_id="baggage_1", directive="reroute_via", waypoint="service_lane_north"),
                PolicyAction(vehicle_id="catering_1", directive="reroute_via", waypoint="service_lane_north"),
            ],
            temporary_rules=[
                TemporaryRule(zone="service_lane_north", rule="sterile_corridor", duration_ms=7600),
                TemporaryRule(zone="service_lane_east", rule="hazmat_watch", duration_ms=7600),
                TemporaryRule(zone="taxiway_crossing_c", rule="blocked", duration_ms=6200),
            ],
            summary="Use the north lane as the sterile medical corridor, freeze fuel and VIP movements, and isolate the blocked crossing.",
        )

    if incident_key == "fuel_leak":
        return CoordinationPolicy(
            incident="fuel_leak",
            priority_vehicle="security_1",
            actions=[
                PolicyAction(
                    vehicle_id="fuel_1",
                    directive="hold_position",
                    duration_ms=6500,
                    reason="Stop fuel movement until the safety corridor is isolated.",
                ),
                PolicyAction(
                    vehicle_id="security_1",
                    directive="block_zone",
                    zone="service_lane_east",
                    duration_ms=6500,
                ),
                PolicyAction(vehicle_id="baggage_1", directive="reroute_via", waypoint="service_lane_north"),
                PolicyAction(vehicle_id="passenger_bus_1", directive="yield_to", target="security_1", duration_ms=4500),
            ],
            temporary_rules=[
                TemporaryRule(zone="service_lane_east", rule="safety_hold", duration_ms=6500),
                TemporaryRule(zone="taxiway_crossing_c", rule="no_fuel_traffic", duration_ms=7000),
            ],
            summary="Freeze fuel movement, isolate the eastern lane, and route non-critical traffic north.",
        )

    if incident_key == "vehicle_breakdown":
        return CoordinationPolicy(
            incident="vehicle_breakdown",
            priority_vehicle="maintenance_1",
            actions=[
                PolicyAction(vehicle_id="maintenance_1", directive="reroute_via", waypoint="service_lane_east"),
                PolicyAction(vehicle_id="security_1", directive="block_zone", zone="taxiway_crossing_c", duration_ms=6000),
                PolicyAction(vehicle_id="baggage_1", directive="reroute_via", waypoint="service_lane_north"),
                PolicyAction(vehicle_id="fuel_1", directive="hold_position", duration_ms=3000),
            ],
            temporary_rules=[TemporaryRule(zone="taxiway_crossing_c", rule="blocked", duration_ms=6500)],
            summary="Treat the blocked crossing as closed and move recovery traffic through the eastern service lane.",
        )

    if incident_key == "vip_arrival":
        return CoordinationPolicy(
            incident="vip_arrival",
            priority_vehicle="pushback_1",
            actions=[
                PolicyAction(vehicle_id="pushback_1", directive="priority_route", waypoint="gate_alpha"),
                PolicyAction(vehicle_id="passenger_bus_1", directive="hold_position", duration_ms=3500),
                PolicyAction(vehicle_id="baggage_1", directive="yield_to", target="pushback_1", duration_ms=4500),
                PolicyAction(vehicle_id="security_1", directive="block_zone", zone="gate_alpha", duration_ms=5000),
            ],
            temporary_rules=[TemporaryRule(zone="gate_alpha", rule="vip_priority", duration_ms=7000)],
            summary="Give pushback and security priority near the VIP gate while delaying lower-priority services.",
        )

    priority = str(telemetry.get("priority_vehicle") or "ambulance_1")
    return CoordinationPolicy(
        incident="medical_emergency",
        priority_vehicle=priority,
        actions=[
            PolicyAction(
                vehicle_id="fuel_1",
                directive="hold_position",
                duration_ms=5200,
                reason="Fuel service is non-critical during medical access.",
            ),
            PolicyAction(vehicle_id="baggage_1", directive="reroute_via", waypoint="service_lane_north"),
            PolicyAction(vehicle_id="catering_1", directive="reroute_via", waypoint="service_lane_north"),
            PolicyAction(vehicle_id="passenger_bus_1", directive="yield_to", target=priority, duration_ms=6000),
            PolicyAction(vehicle_id="security_1", directive="block_zone", zone="taxiway_crossing_c", duration_ms=5000),
            PolicyAction(vehicle_id=priority, directive="priority_route", waypoint="gate_alpha_medical"),
        ],
        temporary_rules=[
            TemporaryRule(zone="service_lane_east", rule="emergency_only", duration_ms=7000),
            TemporaryRule(zone="gate_alpha", rule="medical_priority", duration_ms=8000),
        ],
        summary="Clear the eastern service corridor for ambulance access while holding or rerouting non-critical vehicles.",
    )


POLICY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["incident", "priority_vehicle", "actions", "temporary_rules", "summary", "confidence"],
    "properties": {
        "incident": {"type": "string"},
        "priority_vehicle": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["vehicle_id", "directive", "duration_ms", "waypoint", "zone", "target", "reason"],
                "properties": {
                    "vehicle_id": {"type": "string"},
                    "directive": {
                        "type": "string",
                        "enum": [
                            "hold_position",
                            "reroute_via",
                            "yield_to",
                            "block_zone",
                            "priority_route",
                            "go_around",
                            "clear_land",
                            "cancel_takeoff",
                            "line_up_and_wait",
                            "expedite_crossing",
                        ],
                    },
                    "duration_ms": {"type": ["integer", "null"], "minimum": 0},
                    "waypoint": {"type": ["string", "null"]},
                    "zone": {"type": ["string", "null"]},
                    "target": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
            },
        },
        "temporary_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["zone", "rule", "duration_ms"],
                "properties": {
                    "zone": {"type": "string"},
                    "rule": {
                        "type": "string",
                        "enum": [
                            "emergency_only",
                            "medical_priority",
                            "safety_hold",
                            "no_fuel_traffic",
                            "blocked",
                            "vip_priority",
                            "sterile_corridor",
                            "hazmat_watch",
                            "runway_closed",
                            "crossing_lockout",
                            "arrival_priority",
                            "departure_hold",
                        ],
                    },
                    "duration_ms": {"type": "integer", "minimum": 0},
                },
            },
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
