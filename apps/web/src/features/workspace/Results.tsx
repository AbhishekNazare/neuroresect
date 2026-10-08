"use client";
import {
  ArrowDownRight,
  ArrowRight,
  ChartNoAxesCombined,
  GitBranch,
  Network,
  ShieldCheck,
} from "lucide-react";
import { numeric, percent } from "@/lib/api";
import { ProvenanceDetails, Spinner } from "./primitives";
import type { WorkspaceState } from "./useWorkspace";
export function MetricCards({ state }: { state: WorkspaceState }) {
  const { simulation: s } = state;
  const metrics = [
    {
      label: "GLOBAL EFFICIENCY",
      value: numeric(s?.post.efficiency),
      before: s && numeric(s.baseline.efficiency),
      description: "Weighted network communication",
      icon: ChartNoAxesCombined,
      delta: s?.delta.efficiency,
    },
    {
      label: "CONNECTIVITY LOSS",
      value: s ? percent(s.connectivity_loss) : "—",
      before: null,
      description: "Total edge weight removed",
      icon: Network,
      delta: undefined,
    },
    {
      label: "NETWORK MODULARITY",
      value: numeric(s?.post.modularity),
      before: s && numeric(s.baseline.modularity),
      description: "Community organization",
      icon: GitBranch,
      delta: s?.delta.modularity,
    },
    {
      label: "HUB DAMAGE",
      value: s ? percent(s.hub_damage) : "—",
      before: null,
      description: "Weighted disruption of network hubs",
      icon: ShieldCheck,
      delta: undefined,
    },
  ];
  return (
    <section className="metrics-grid" aria-label="Network metrics">
      {metrics.map((m) => (
        <article className="metric-card" key={m.label}>
          <div className="metric-heading">
            <span>{m.label}</span>
            <m.icon size={16} />
          </div>
          <div className="metric-value">
            {m.value}
            {m.delta !== undefined && (
              <span className={`delta ${m.delta < 0 ? "negative" : ""}`}>
                <ArrowDownRight size={12} />
                {m.delta > 0 ? "+" : ""}
                {numeric(m.delta)}
              </span>
            )}
          </div>
          <div className="metric-description">
            {s ? (
              m.before ? (
                <>
                  Baseline <b>{m.before}</b>
                  <span>→ after resection</span>
                </>
              ) : (
                m.description
              )
            ) : (
              "Available after simulation"
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
export function PredictionPanel({ state }: { state: WorkspaceState }) {
  const p = state.prediction;
  return (
    <section className="prediction-panel panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">MODEL EXPLORER</span>
          <h2>Outcome estimate</h2>
        </div>
        <span className="tag amber">SYNTHETIC</span>
      </div>
      <p className="panel-description">
        An educational model trained on synthetic outcomes. It cannot estimate
        an actual patient’s outcome.
      </p>
      {p ? (
        <>
          <div className="prediction-value">
            {percent(p.probability, 0)}
            <span>synthetic favorable outcome</span>
          </div>
          <div className="interval-track">
            <div
              style={{
                left: `${p.interval.lower * 100}%`,
                width: `${(p.interval.upper - p.interval.lower) * 100}%`,
              }}
            />
            <i style={{ left: `${p.probability * 100}%` }} />
          </div>
          <div className="interval-labels">
            <span>0%</span>
            <strong>
              {percent(p.interval.lower, 0)}–{percent(p.interval.upper, 0)} ·{" "}
              {percent(p.interval.level, 0)} interval
            </strong>
            <span>100%</span>
          </div>
          <div className="small-note">
            {p.interval.method.replaceAll("_", " ")} · {p.model.name}{" "}
            {p.model.version}
          </div>
          <details className="contributions">
            <summary>Inspect log-odds contributions</summary>
            {p.contributions.slice(0, 12).map((c) => (
              <div key={c.feature}>
                <span>{c.feature.replaceAll("_", " ")}</span>
                <b>{numeric(c.value)}</b>
              </div>
            ))}
          </details>
          <ProvenanceDetails provenance={p.provenance} />
        </>
      ) : (
        <div className="prediction-placeholder">
          <span className="dotted-circle">
            <ChartNoAxesCombined size={22} />
          </span>
          <p>
            {state.simulation
              ? "The network is ready for a model estimate."
              : "Simulate a resection to explore model output and uncertainty."}
          </p>
        </div>
      )}
      <button
        className="secondary-button full"
        disabled={
          !state.simulation ||
          !!state.busy ||
          state.method !== "weighted" ||
          !state.patientId.startsWith("DEMO-")
        }
        onClick={state.predict}
      >
        {state.busy === "Estimating synthetic outcome" ? (
          <Spinner label="Fitting model…" />
        ) : (
          <>
            {" "}
            {p ? "Recalculate estimate" : "Estimate synthetic outcome"}
            <ArrowRight size={14} />
          </>
        )}
      </button>
    </section>
  );
}
