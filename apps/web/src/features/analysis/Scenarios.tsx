"use client";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Download,
  FlaskConical,
  GitCompareArrows,
  Shield,
} from "lucide-react";
import { api, numeric, percent } from "@/lib/api";
import type { Simulation } from "@/lib/types";
import type { WorkspaceState } from "../workspace/useWorkspace";
import { Empty, ProvenanceDetails, Spinner } from "../workspace/primitives";
export function Scenarios({
  state,
  openWorkspace,
}: {
  state: WorkspaceState;
  openWorkspace: () => void;
}) {
  const [coverage, setCoverage] = useState(0.8),
    [protectedRegions, setProtectedRegions] = useState<number[]>([]);
  const [saved, setSaved] = useState<Record<string, Simulation>>({}),
    [comparisonError, setComparisonError] = useState("");
  useEffect(() => {
    setProtectedRegions([]);
  }, [state.patientId, state.atlasId]);
  useEffect(() => {
    const ac = new AbortController();
    setSaved({});
    setComparisonError("");
    Promise.all(
      state.scenarios.map(async (s) => {
        try {
          return [
            s.id,
            await api<Simulation>(`/scenarios/${s.id}/simulation`, {
              signal: ac.signal,
            }),
          ] as const;
        } catch (e) {
          if (
            e instanceof Error &&
            e.name !== "AbortError" &&
            !("status" in e && e.status === 404)
          )
            throw e;
          return null;
        }
      }),
    )
      .then((results) => {
        if (!ac.signal.aborted)
          setSaved(
            Object.fromEntries(
              results.filter((r): r is NonNullable<typeof r> => !!r),
            ),
          );
      })
      .catch((e) => {
        if (!ac.signal.aborted) setComparisonError(e.message);
      });
    return () => ac.abort();
  }, [
    state.scenarios.length,
    state.patientId,
    state.atlasId,
    state.simulation,
  ]);
  return (
    <div className="analysis-page">
      <div className="section-intro">
        <div>
          <span className="eyebrow">TEST THE WHAT-IFS</span>
          <h2>Every resection tells a different story.</h2>
          <p>
            Compare saved network changes, test boundary sensitivity, and search
            within explicit constraints.
          </p>
        </div>
        <GitCompareArrows size={34} />
      </div>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">SAVED SCENARIOS</span>
            <h2>Compare network disruption</h2>
          </div>
          <span className="tag">{state.scenarios.length} SAVED</span>
        </div>
        {comparisonError && (
          <div className="inline-error" role="alert">
            {comparisonError}
          </div>
        )}
        {!state.scenarios.length ? (
          <Empty title="Your first comparison starts with a simulation">
            Create and simulate a resection in the workspace. Each changed
            selection creates a new saved scenario.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Regions</th>
                  <th>Efficiency</th>
                  <th>Weight loss</th>
                  <th>Hub damage</th>
                  <th>Open</th>
                </tr>
              </thead>
              <tbody>
                {state.scenarios.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.label}</strong>
                      <small>
                        {s.method} ·{" "}
                        {new Date(s.created_at).toLocaleDateString()}
                      </small>
                    </td>
                    <td>{s.regions.length}</td>
                    <td>{numeric(saved[s.id]?.post.efficiency)}</td>
                    <td>
                      {saved[s.id]
                        ? percent(saved[s.id].connectivity_loss)
                        : "Not simulated"}
                    </td>
                    <td>
                      {saved[s.id] ? percent(saved[s.id].hub_damage) : "—"}
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Open ${s.label}`}
                        onClick={() => {
                          state.loadScenario(s);
                          openWorkspace();
                        }}
                      >
                        <ArrowRight size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="analysis-columns">
        <section className="panel analysis-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">BOUNDARY ROBUSTNESS</span>
              <h2>Sensitivity analysis</h2>
            </div>
            <FlaskConical size={20} />
          </div>
          <p className="panel-description">
            Perturb the selected removal fractions and recompute the graph.
            Large changes reveal a sensitive boundary.
          </p>
          <button
            className="secondary-button full"
            disabled={
              !state.connectome || !state.regions.length || !!state.busy
            }
            onClick={state.analyzeSensitivity}
          >
            {state.busy === "Testing resection boundaries" ? (
              <Spinner label="Computing variants…" />
            ) : (
              <>
                Test resection boundaries
                <ArrowRight size={14} />
              </>
            )}
          </button>
          {state.sensitivity ? (
            <>
              <div
                className="bar-chart"
                aria-label="Connectivity loss by boundary perturbation"
              >
                {state.sensitivity.variants.map((v, i) => (
                  <div className="bar-row" key={`${v.label}-${i}`}>
                    <span>{v.label}</span>
                    <div className="bar-track">
                      <div
                        style={{
                          width: `${Math.max(1, v.connectivity_loss * 100)}%`,
                        }}
                      />
                    </div>
                    <b>{percent(v.connectivity_loss)}</b>
                  </div>
                ))}
              </div>
              <div className="chart-caption">
                Bar length = total connection weight lost
              </div>
              <div className="sensitivity-scores">
                <h3>Most sensitive regions</h3>
                {[...state.sensitivity.region_scores]
                  .sort((a, b) => b.score - a.score)
                  .slice(0, 5)
                  .map((r) => (
                    <div key={r.region_id}>
                      <span>
                        {state.connectome?.nodes.find(
                          (n) => n.id === r.region_id,
                        )?.name || r.region_id}
                      </span>
                      <b>{numeric(r.score)}</b>
                    </div>
                  ))}
              </div>
              <ProvenanceDetails provenance={state.sensitivity.provenance} />
            </>
          ) : (
            <Empty title="How stable is this scenario?">
              Select at least one region, then run boundary analysis to see
              computed variants.
            </Empty>
          )}
        </section>
        <section className="panel analysis-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">CONSTRAINED SEARCH</span>
              <h2>Counterfactual alternatives</h2>
            </div>
            <Shield size={20} />
          </div>
          <p className="panel-description">
            Explore candidate resections that preserve target coverage and
            exclude your protected regions. These are research comparisons.
          </p>
          <label className="control-label" htmlFor="coverage">
            Minimum target fraction coverage <b>{percent(coverage, 0)}</b>
          </label>
          <input
            type="range"
            id="coverage"
            min="0"
            max="100"
            step="5"
            value={coverage * 100}
            onChange={(e) => setCoverage(Number(e.target.value) / 100)}
          />
          <details className="protected-regions">
            <summary>
              Protect atlas regions{" "}
              <span>{protectedRegions.length} selected</span>
            </summary>
            <div>
              {state.connectome?.nodes.map((n) => (
                <label key={n.id}>
                  <input
                    type="checkbox"
                    checked={protectedRegions.includes(n.id)}
                    onChange={(e) =>
                      setProtectedRegions((current) =>
                        e.target.checked
                          ? [...current, n.id]
                          : current.filter((id) => id !== n.id),
                      )
                    }
                  />
                  {n.name}
                </label>
              ))}
            </div>
          </details>
          <button
            className="secondary-button full"
            disabled={
              !state.connectome ||
              !state.regions.length ||
              !!state.busy ||
              state.method !== "weighted"
            }
            onClick={() =>
              state.analyzeCounterfactuals(coverage, protectedRegions)
            }
          >
            {state.busy === "Searching constrained alternatives" ? (
              <Spinner label="Searching candidates…" />
            ) : (
              <>
                Find alternatives
                <ArrowRight size={14} />
              </>
            )}
          </button>
          {state.counterfactual && (
            <>
              {!state.counterfactual.candidates.length ? (
                <Empty title="No feasible candidates">
                  No candidate satisfies these constraints. Adjust target
                  coverage or protected regions and search again.
                </Empty>
              ) : (
                <div className="candidate-list">
                  {state.counterfactual.candidates.map((c) => (
                    <article key={c.id}>
                      <div>
                        <h3>{c.label}</h3>
                        <p>
                          {percent(c.target_coverage, 0)} coverage{" "}
                          <span>·</span> {percent(c.connectivity_loss)} weight
                          loss
                        </p>
                      </div>
                      <button
                        className="icon-button"
                        aria-label={`Use ${c.label}`}
                        onClick={() => {
                          state.editRegions(c.regions);
                          openWorkspace();
                        }}
                      >
                        <ArrowRight size={16} />
                      </button>
                    </article>
                  ))}
                </div>
              )}
              <ProvenanceDetails provenance={state.counterfactual.provenance} />
            </>
          )}
        </section>
      </div>
      {state.scenario && (
        <a
          className="download-link"
          href={`/api/v1/scenarios/${state.scenario.id}/export`}
          download
        >
          <Download size={15} />
          Export current scenario, results & provenance
        </a>
      )}
    </div>
  );
}
