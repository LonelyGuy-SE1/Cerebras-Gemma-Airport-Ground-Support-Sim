import { Activity, AlertTriangle, Gauge, GitBranch, Route, ShieldCheck, Timer, Zap } from "lucide-react";

import type { SimMetrics } from "../physics/types";

function formatMs(ms: number | null): string {
  if (ms === null) return "--";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

interface MetricGridProps {
  metrics: SimMetrics;
}

export function MetricGrid({ metrics }: MetricGridProps) {
  const rows = [
    { label: "LLM latency", value: formatMs(metrics.llmLatencyMs), icon: Timer },
    { label: "Policy stale", value: `${metrics.policyStaleness}%`, icon: Gauge },
    { label: "Turn delay", value: formatMs(metrics.turnaroundDelayMs), icon: Route },
    { label: "Runway risk", value: `${metrics.runwayIncursionRisk}%`, icon: AlertTriangle },
    { label: "Aircraft delay", value: formatMs(metrics.aircraftDelayMs), icon: Activity },
    { label: "Conflicts avoided", value: `${metrics.conflictsAvoided}`, icon: ShieldCheck },
    { label: "Validity used", value: `${metrics.validityConsumedPct}%`, icon: Zap },
    { label: "Load", value: `${metrics.challengeLoad}`, icon: GitBranch },
    { label: "Deadlock", value: formatMs(metrics.deadlockDurationMs), icon: Gauge },
  ];

  return (
    <div className="metric-grid">
      {rows.map((row) => {
        const Icon = row.icon;
        return (
          <div className="metric" key={row.label}>
            <Icon aria-hidden="true" size={15} />
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        );
      })}
    </div>
  );
}
