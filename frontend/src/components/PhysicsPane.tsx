import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties } from "react";
import { Cpu, Radio, SatelliteDish } from "lucide-react";

import type { PhysicsSnapshot } from "../physics/types";
import { AirportScene } from "../three/AirportScene";
import { MetricGrid } from "./MetricGrid";

export interface PhysicsPaneHandle {
  captureFrame: () => string | null;
}

interface PhysicsPaneProps {
  title: string;
  subtitle: string;
  accent: string;
  snapshot: PhysicsSnapshot | null;
  pending: boolean;
}

function modeLabel(mode: PhysicsSnapshot["lastCoordinatorMode"] | "idle"): string {
  if (mode === "fallback_after_error") return "Fallback";
  if (mode === "simulated") return "Simulated";
  if (mode === "live") return "Live";
  return "Idle";
}

function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "--";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${Math.round(value)}`;
}

function fmtEnergy(value: number | undefined): string {
  if (!value) return "--";
  if (value > 1000000) return `${(value / 1000000).toFixed(1)}MJ`;
  return `${Math.round(value / 1000)}kJ`;
}

export const PhysicsPane = forwardRef<PhysicsPaneHandle, PhysicsPaneProps>(({ title, subtitle, accent, snapshot, pending }, ref) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<AirportScene | null>(null);
  const frameRef = useRef<number | null>(null);
  const appliedSnapshotRef = useRef<PhysicsSnapshot | null | undefined>(undefined);
  const latestSnapshotRef = useRef<PhysicsSnapshot | null>(snapshot);
  const [gpuLabel, setGpuLabel] = useState("GPU pending");

  latestSnapshotRef.current = snapshot;

  useImperativeHandle(ref, () => ({
    captureFrame: () => sceneRef.current?.capture() ?? null,
  }));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const scene = new AirportScene(canvas);
    sceneRef.current = scene;
    setGpuLabel(scene.gpuLabel());

    const render = (time: number) => {
      const rect = canvas.getBoundingClientRect();
      scene.resize(rect.width, rect.height, window.devicePixelRatio || 1);
      const currentSnapshot = latestSnapshotRef.current;
      if (appliedSnapshotRef.current !== currentSnapshot) {
        scene.update(currentSnapshot);
        appliedSnapshotRef.current = currentSnapshot;
      }
      scene.render(time);
      frameRef.current = requestAnimationFrame(render);
    };

    frameRef.current = requestAnimationFrame(render);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

  const mode = snapshot?.lastCoordinatorMode ?? "idle";
  const statusClass = mode === "live" ? "live" : mode === "idle" ? "idle" : "sim";
  const incident = snapshot?.incident ? snapshot.incident.replaceAll("_", " ") : "Nominal operations";

  return (
    <section className="sim-pane physics-pane" style={{ "--accent": accent } as CSSProperties}>
      <header className="pane-header">
        <div>
          <p className="eyebrow">{subtitle}</p>
          <h2>{title}</h2>
        </div>
        <div className={`provider-badge ${statusClass}`}>
          {mode === "live" ? <SatelliteDish size={15} /> : <Cpu size={15} />}
          <span>{modeLabel(mode)}</span>
        </div>
      </header>

      <div className="scene-shell">
        <canvas ref={canvasRef} aria-label={`${title} MuJoCo 3D simulation`} />
        <div className={`engine-plaque ${gpuLabel === "GPU software" ? "software" : ""}`}>
          <strong>{snapshot?.physicsEngine ?? "MuJoCo"}</strong>
          <span>{snapshot ? `${snapshot.timestepMs}ms step` : "starting"}</span>
          <span>{gpuLabel}</span>
        </div>
        {pending && (
          <div className="pending-overlay">
            <Radio size={22} />
            <span>Coordinator pending</span>
            <i />
          </div>
        )}
      </div>

      <div className="policy-strip">
        <strong>{incident}</strong>
        <span>{snapshot?.lastPolicySummary ?? "Waiting for physics snapshot"}</span>
      </div>

      <div className="timing-strip">
        <span>
          <b>E2E</b>
          <strong>{formatMs(snapshot?.lastTiming?.latencyMs)}</strong>
        </span>
        <span>
          <b>TTFT</b>
          <strong>{formatMs(snapshot?.lastTiming?.ttftMs)}</strong>
        </span>
        <span>
          <b>Tok/s</b>
          <strong>{formatCount(snapshot?.lastTiming?.tokensPerSecond)}</strong>
        </span>
        <span>
          <b>Window</b>
          <strong>{snapshot ? `${snapshot.metrics.validityConsumedPct}%` : "--"}</strong>
        </span>
        <span>
          <b>Aircraft</b>
          <strong>{snapshot?.metrics.activeAircraft ?? 0}</strong>
        </span>
        <span>
          <b>Energy</b>
          <strong>{fmtEnergy(snapshot?.metrics.kineticEnergyJ)}</strong>
        </span>
      </div>

      {snapshot && <MetricGrid metrics={snapshot.metrics} />}
    </section>
  );
});

PhysicsPane.displayName = "PhysicsPane";
