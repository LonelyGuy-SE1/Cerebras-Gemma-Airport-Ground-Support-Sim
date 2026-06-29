import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Pause, Plane, Play, RadioTower, RefreshCw, Siren, ToggleLeft, ToggleRight, Zap } from "lucide-react";

import { PhysicsPane, type PhysicsPaneHandle } from "./components/PhysicsPane";
import { coordinatePolicy, getHealth, type CoordinateResponse, type HealthResponse } from "./services/api";
import { applyPhysicsPolicy, resetPhysics, stepPhysics, triggerPhysicsIncident } from "./services/physics";
import type { IncidentType, PaneKind, PhysicsSnapshots } from "./physics/types";

const SEED = 42;
const DEMO_INCIDENT: IncidentType = "runway_incursion";
const DEMO_FINAL_CARD_MS = 52000;
const INCIDENT_OPTIONS: Array<{ value: IncidentType; label: string }> = [
  { value: "runway_incursion", label: "Runway incursion" },
  { value: "compound_incursion", label: "Compound" },
  { value: "medical_emergency", label: "Medical" },
  { value: "fuel_leak", label: "Fuel leak" },
  { value: "vehicle_breakdown", label: "Breakdown" },
  { value: "vip_arrival", label: "VIP arrival" },
];

const CHALLENGE_BRIEF: Record<IncidentType, { primary: string; constraints: string[]; window: string }> = {
  runway_incursion: {
    primary: "DC-8 short final, runway crossing traffic, departure queue, and fuel hazard collide",
    constraints: ["go-around decision", "crossing lockout", "departure hold", "fuel freeze"],
    window: "1800ms ATC reflex window",
  },
  compound_incursion: {
    primary: "Ambulance to Gate Alpha while fuel, VIP, and crossing constraints collide",
    constraints: ["life safety first", "fuel hazard east", "Crossing C blocked", "VIP gate pressure"],
    window: "1800ms policy validity",
  },
  medical_emergency: {
    primary: "Clear ambulance access to Gate Alpha",
    constraints: ["yield bus", "hold fuel", "preserve throughput", "secure crossing"],
    window: "1800ms policy validity",
  },
  fuel_leak: {
    primary: "Freeze fuel motion and isolate the east service lane",
    constraints: ["hazmat perimeter", "reroute baggage", "security block", "avoid apron freeze"],
    window: "2200ms policy validity",
  },
  vehicle_breakdown: {
    primary: "Recover blocked Crossing C without deadlocking services",
    constraints: ["maintenance priority", "north reroutes", "hold fuel", "protect taxiway"],
    window: "2000ms policy validity",
  },
  vip_arrival: {
    primary: "Protect priority gate movement without starving routine services",
    constraints: ["pushback priority", "security gate block", "bus hold", "baggage yield"],
    window: "1800ms policy validity",
  },
};

function providerText(health: HealthResponse | null, provider: PaneKind, liveProviders: boolean): string {
  if (!liveProviders) return "forced sim";
  const data = health?.providers[provider];
  if (!data) return "checking";
  return data.configured ? "live key" : `${data.simulated_delay_ms}ms sim`;
}

function mergeSnapshot(current: PhysicsSnapshots | null, pane: PaneKind, snapshot: PhysicsSnapshots[PaneKind]): PhysicsSnapshots | null {
  if (!current) return null;
  return { ...current, [pane]: snapshot };
}

export function App() {
  const baselineRef = useRef<PhysicsPaneHandle | null>(null);
  const cerebrasRef = useRef<PhysicsPaneHandle | null>(null);
  const timersRef = useRef<number[]>([]);
  const steppingRef = useRef(false);
  const scriptedAdvanceRef = useRef(false);
  const lastStepAtRef = useRef(performance.now());
  const snapshotsRef = useRef<PhysicsSnapshots | null>(null);
  const [snapshots, setSnapshots] = useState<PhysicsSnapshots | null>(null);
  const [pending, setPending] = useState<Record<PaneKind, boolean>>({ baseline: false, cerebras: false });
  const [running, setRunning] = useState(true);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [liveProviders, setLiveProviders] = useState(true);
  const [selectedIncident, setSelectedIncident] = useState<IncidentType>(DEMO_INCIDENT);
  const [demoActive, setDemoActive] = useState(false);
  const [finalCard, setFinalCard] = useState(false);
  const [stage, setStage] = useState("Starting MuJoCo");
  const [events, setEvents] = useState<string[]>(["Initializing physics world"]);

  snapshotsRef.current = snapshots;

  const pushEvent = useCallback((event: string) => {
    setEvents((current) => [event, ...current].slice(0, 6));
  }, []);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error: unknown) => pushEvent(`Backend health unavailable: ${String(error).slice(0, 90)}`));
  }, [pushEvent]);

  useEffect(() => {
    resetPhysics(SEED)
      .then((next) => {
        snapshotsRef.current = next;
        setSnapshots(next);
        setStage("MuJoCo runway online");
        pushEvent("MuJoCo twin initialized");
      })
      .catch((error: unknown) => {
        setStage("Physics backend unavailable");
        pushEvent(`Physics reset failed: ${String(error).slice(0, 92)}`);
      });
  }, [pushEvent]);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      if (!cancelled && !steppingRef.current && !scriptedAdvanceRef.current) {
        const now = performance.now();
        const dtMs = Math.max(120, Math.min(360, Math.round(now - lastStepAtRef.current)));
        lastStepAtRef.current = now;
        steppingRef.current = true;
        try {
          const next = await stepPhysics(dtMs, running);
          if (!cancelled) {
            snapshotsRef.current = next;
            setSnapshots(next);
          }
        } catch (error) {
          if (!cancelled) pushEvent(`Physics step failed: ${String(error).slice(0, 82)}`);
        } finally {
          steppingRef.current = false;
        }
      }
    };

    const interval = window.setInterval(() => {
      void tick();
    }, 240);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pushEvent, running]);

  const clearTimers = useCallback(() => {
    for (const timer of timersRef.current) window.clearTimeout(timer);
    timersRef.current = [];
  }, []);

  const schedule = useCallback((callback: () => void, ms: number) => {
    const timer = window.setTimeout(callback, ms);
    timersRef.current.push(timer);
  }, []);

  const reset = useCallback(() => {
    clearTimers();
    setDemoActive(false);
    setFinalCard(false);
    setStage("Resetting MuJoCo");
    setPending({ baseline: false, cerebras: false });
    resetPhysics(SEED)
      .then((next) => {
        snapshotsRef.current = next;
        setSnapshots(next);
        setRunning(true);
        setStage("Ready");
        pushEvent("Scenario reset from MJCF seed");
      })
      .catch((error: unknown) => pushEvent(`Reset failed: ${String(error).slice(0, 92)}`));
  }, [clearTimers, pushEvent]);

  const setBothRunning = useCallback((nextRunning: boolean) => {
    setRunning(nextRunning);
  }, []);

  const requestPanePolicy = useCallback(
    async (provider: PaneKind, incident: IncidentType) => {
      const current = snapshotsRef.current?.[provider];
      if (!current) return;
      const pane = provider === "baseline" ? baselineRef.current : cerebrasRef.current;
      const frameDataUrl = pane?.captureFrame() ?? null;
      const requestedAtSimMs = current.simTimeMs;
      setPending((value) => ({ ...value, [provider]: true }));
      pushEvent(`${provider} request sent at T+${(requestedAtSimMs / 1000).toFixed(1)}s`);

      try {
        const response: CoordinateResponse = await coordinatePolicy({
          provider,
          incident,
          telemetry: current,
          frameDataUrl,
          scenarioSeed: SEED,
          forceSimulated: !liveProviders,
        });
        const updated = await applyPhysicsPolicy({
          pane: provider,
          policy: response.policy,
          timing: response.timing,
          requestedAtSimMs,
          mode: response.mode,
          model: response.model,
        });
        snapshotsRef.current = mergeSnapshot(snapshotsRef.current, provider, updated);
        setSnapshots((existing) => mergeSnapshot(existing, provider, updated));
        pushEvent(`${provider} ${response.mode} policy in ${response.timing.latencyMs}ms`);
      } catch (error) {
        pushEvent(`${provider} coordinator error: ${String(error).slice(0, 92)}`);
      } finally {
        setPending((value) => ({ ...value, [provider]: false }));
      }
    },
    [liveProviders, pushEvent],
  );

  const advancePhysicsTo = useCallback(
    async (targetSimMs: number): Promise<PhysicsSnapshots | null> => {
      const currentSimMs = snapshotsRef.current?.baseline.simTimeMs ?? 0;
      const dtMs = Math.max(0, targetSimMs - currentSimMs);
      if (dtMs < 10) return snapshotsRef.current;
      scriptedAdvanceRef.current = true;
      try {
        const next = await stepPhysics(dtMs, true);
        snapshotsRef.current = next;
        setSnapshots(next);
        return next;
      } finally {
        scriptedAdvanceRef.current = false;
      }
    },
    [],
  );

  const triggerIncident = useCallback(() => {
    setFinalCard(false);
    const label = selectedIncident.replaceAll("_", " ");
    setStage(label);
    triggerPhysicsIncident(selectedIncident)
      .then((next) => {
        snapshotsRef.current = next;
        setSnapshots(next);
        pushEvent(`${label} injected into MuJoCo world`);
        void requestPanePolicy("baseline", selectedIncident);
        void requestPanePolicy("cerebras", selectedIncident);
      })
      .catch((error: unknown) => pushEvent(`Incident failed: ${String(error).slice(0, 92)}`));
  }, [pushEvent, requestPanePolicy, selectedIncident]);

  const runDemo = useCallback(() => {
    clearTimers();
    setPending({ baseline: false, cerebras: false });
    setFinalCard(false);
    setDemoActive(true);
    setStage("Resetting MuJoCo");
    pushEvent("60s MuJoCo demo armed");
    resetPhysics(SEED)
      .then((next) => {
        let incidentReady: Promise<void> = Promise.resolve();
        snapshotsRef.current = next;
        setSnapshots(next);
        setRunning(true);
        setStage("Nominal MuJoCo turnaround");
        pushEvent("60s MuJoCo demo started");
        schedule(() => setStage("Physics twin running"), 1200);
        schedule(() => {
          incidentReady = advancePhysicsTo(5200)
            .then(() => triggerPhysicsIncident(DEMO_INCIDENT))
            .then((incidentSnapshots) => {
              snapshotsRef.current = incidentSnapshots;
              setSnapshots(incidentSnapshots);
          setStage("Runway incursion");
          pushEvent("Runway incursion injected into both twins");
            })
            .catch((error: unknown) => pushEvent(`Incident failed: ${String(error).slice(0, 92)}`));
        }, 5200);
        schedule(() => {
          setStage("Frame and telemetry captured");
          incidentReady
            .then(() => advancePhysicsTo(5900))
            .then(() => {
              void requestPanePolicy("baseline", DEMO_INCIDENT);
              void requestPanePolicy("cerebras", DEMO_INCIDENT);
            })
            .catch((error: unknown) => pushEvent(`Demo advance failed: ${String(error).slice(0, 92)}`));
        }, 5900);
        schedule(() => setStage("Policy contrast forming"), 12000);
        schedule(() => setStage("Physical metrics locked"), 34000);
        schedule(() => {
          setFinalCard(true);
          setStage("Final comparison");
        }, DEMO_FINAL_CARD_MS);
      })
      .catch((error: unknown) => pushEvent(`Demo reset failed: ${String(error).slice(0, 92)}`));
  }, [advancePhysicsTo, clearTimers, pushEvent, requestPanePolicy, schedule]);

  const baselineLatency = snapshots?.baseline.metrics.llmLatencyMs ?? 0;
  const cerebrasLatency = snapshots?.cerebras.metrics.llmLatencyMs ?? 0;
  const baselineMetrics = snapshots?.baseline.metrics;
  const cerebrasMetrics = snapshots?.cerebras.metrics;
  const delta = baselineLatency && cerebrasLatency ? Math.max(0, baselineLatency - cerebrasLatency) : 0;

  return (
    <main className="app-shell">
      <header className="command-bar">
        <div className="brand-lockup">
          <Plane aria-hidden="true" size={28} />
          <div>
            <h1>AI Airport Operations Simulator</h1>
            <p>MuJoCo-backed ATC and ground coordination for autonomous runway operations</p>
          </div>
        </div>

        <div className="command-actions">
          <button type="button" className="primary" onClick={runDemo} title="Run 60 second demo">
            <Play size={17} />
            <span>Run 60s Demo</span>
          </button>
          <label className="incident-picker" title="Select incident type">
            <Siren size={16} />
            <select value={selectedIncident} onChange={(event) => setSelectedIncident(event.target.value as IncidentType)}>
              {INCIDENT_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={triggerIncident} title="Trigger selected incident">
            <Siren size={17} />
            <span>Trigger</span>
          </button>
          <button type="button" onClick={() => setBothRunning(!running)} title={running ? "Pause physics" : "Resume physics"}>
            {running ? <Pause size={17} /> : <Play size={17} />}
            <span>{running ? "Pause" : "Resume"}</span>
          </button>
          <button type="button" onClick={reset} title="Reset seeded MuJoCo scenario">
            <RefreshCw size={17} />
            <span>Reset</span>
          </button>
          <button type="button" className="toggle" onClick={() => setLiveProviders((value) => !value)} title="Toggle live provider calls">
            {liveProviders ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
            <span>{liveProviders ? "Live API" : "Sim API"}</span>
          </button>
        </div>
      </header>

      <section className="status-ribbon">
        <div>
          <RadioTower size={16} />
          <span>Stage</span>
          <strong>{stage}</strong>
        </div>
        <div>
          <Zap size={16} />
          <span>Cerebras</span>
          <strong>{providerText(health, "cerebras", liveProviders)}</strong>
        </div>
        <div>
          <AlertTriangle size={16} />
          <span>Baseline</span>
          <strong>{providerText(health, "baseline", liveProviders)}</strong>
        </div>
        <div>
          <Zap size={16} />
          <span>Latency gap</span>
          <strong>{delta ? `${delta}ms` : "--"}</strong>
        </div>
      </section>

      <section className="mission-board">
        <div>
          <span>Primary clearance</span>
          <strong>{CHALLENGE_BRIEF[selectedIncident].primary}</strong>
        </div>
        <div>
          <span>Active constraints</span>
          <strong>{CHALLENGE_BRIEF[selectedIncident].constraints.join(" / ")}</strong>
        </div>
        <div>
          <span>Reflex window</span>
          <strong>{CHALLENGE_BRIEF[selectedIncident].window}</strong>
        </div>
      </section>

      <section className="simulation-grid">
        <PhysicsPane
          ref={baselineRef}
          title="Slow Baseline"
          subtitle="Left MuJoCo twin"
          accent="#f4b84a"
          snapshot={snapshots?.baseline ?? null}
          pending={pending.baseline}
        />
        <PhysicsPane
          ref={cerebrasRef}
          title="Cerebras Gemma 4"
          subtitle="Right MuJoCo twin"
          accent="#41e7b5"
          snapshot={snapshots?.cerebras ?? null}
          pending={pending.cerebras}
        />
      </section>

      <aside className="event-strip">
        {events.map((event) => (
          <span key={event}>{event}</span>
        ))}
      </aside>

      {finalCard && (
        <section className="final-card" aria-live="polite">
          <div className="final-board">
            <div className="final-head">
              <p>{demoActive ? "Reflex window result" : "Comparison"}</p>
              <h2>The runway kept changing while the slow model thought.</h2>
              <strong>{delta ? `${delta}ms latency gap scored by MuJoCo` : "Awaiting policy timing"}</strong>
            </div>
            <div className="final-lanes">
              <article className="final-lane stale">
                <span>Slow baseline</span>
                <strong>{baselineLatency ? `${baselineLatency}ms` : "--"}</strong>
                <b>{baselineMetrics?.validityConsumedPct ?? 0}% window used</b>
                <small>
                  {baselineMetrics?.runwayIncursionRisk ?? 0}% runway risk / {((baselineMetrics?.aircraftDelayMs ?? 0) / 1000).toFixed(1)}s aircraft delay
                </small>
              </article>
              <article className="final-lane fresh">
                <span>Cerebras Gemma 4</span>
                <strong>{cerebrasLatency ? `${cerebrasLatency}ms` : "--"}</strong>
                <b>{cerebrasMetrics?.validityConsumedPct ?? 0}% window used</b>
                <small>
                  {cerebrasMetrics?.runwayIncursionRisk ?? 0}% runway risk / {((cerebrasMetrics?.aircraftDelayMs ?? 0) / 1000).toFixed(1)}s aircraft delay
                </small>
              </article>
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
