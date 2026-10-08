"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  Box,
  Check,
  Database,
  GitBranch,
  Network,
  Sparkles,
} from "lucide-react";
import type { WorkspaceState } from "../workspace/useWorkspace";
import { numeric, percent } from "@/lib/api";
import { Empty, ProvenanceDetails } from "../workspace/primitives";
function Matrix({ state }: { state: WorkspaceState }) {
  const canvas = useRef<HTMLCanvasElement>(null),
    [view, setView] = useState<"before" | "after">("before"),
    [cell, setCell] = useState<{ x: number; y: number; value: number } | null>(
      null,
    );
  const graph = state.connectome,
    edges =
      view === "after" && state.simulation
        ? state.simulation.edges
        : graph?.edges;
  const matrix = graph
    ? Array.from(
        { length: graph.nodes.length },
        () => Array(graph.nodes.length).fill(0) as number[],
      )
    : [];
  const indices = new Map(graph?.nodes.map((n, i) => [n.id, i]));
  edges?.forEach((e) => {
    const i = indices.get(e.source),
      j = indices.get(e.target);
    if (i !== undefined && j !== undefined) {
      matrix[i][j] = e.weight;
      matrix[j][i] = e.weight;
    }
  });
  useEffect(() => {
    const c = canvas.current;
    if (!c || !graph) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const size = 640;
    c.width = size;
    c.height = size;
    const step = size / matrix.length;
    const max = Math.max(...graph.edges.map((e) => e.weight), 0.001);
    ctx.fillStyle = "#101c1c";
    ctx.fillRect(0, 0, size, size);
    matrix.forEach((row, i) =>
      row.forEach((value, j) => {
        const t = Math.sqrt(value / max);
        ctx.fillStyle = `rgb(${Math.round(15 + t * 116)},${Math.round(28 + t * 185)},${Math.round(29 + t * 147)})`;
        ctx.fillRect(
          j * step + 0.4,
          i * step + 0.4,
          Math.max(0.5, step - 0.7),
          Math.max(0.5, step - 0.7),
        );
      }),
    );
  }, [state.connectome, state.simulation, view]);
  return (
    <div className="matrix-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">INSIDE THE CONNECTOME</span>
          <h2>Weighted adjacency matrix</h2>
        </div>
        <div className="segmented">
          <button
            className={view === "before" ? "active" : ""}
            onClick={() => setView("before")}
          >
            Before
          </button>
          <button
            className={view === "after" ? "active" : ""}
            disabled={!state.simulation}
            onClick={() => setView("after")}
          >
            After
          </button>
        </div>
      </div>
      {graph ? (
        <>
          <div className="matrix-wrap">
            <span className="matrix-axis">REGION i</span>
            <canvas
              ref={canvas}
              aria-label={`${view} weighted connectivity matrix for ${graph.nodes.length} regions. Connection data is available in the scenario JSON export.`}
              onMouseMove={(e) => {
                const bounds = e.currentTarget.getBoundingClientRect();
                const x = Math.min(
                  matrix.length - 1,
                  Math.floor(
                    ((e.clientX - bounds.left) / bounds.width) * matrix.length,
                  ),
                );
                const y = Math.min(
                  matrix.length - 1,
                  Math.floor(
                    ((e.clientY - bounds.top) / bounds.height) * matrix.length,
                  ),
                );
                setCell({ x, y, value: matrix[y][x] });
              }}
              onMouseLeave={() => setCell(null)}
            />
            <span className="matrix-axis bottom">REGION j</span>
          </div>
          <div className="matrix-legend">
            <span>No connection</span>
            <div />
            <span>Strongest</span>
          </div>
          <div className="matrix-caption" aria-live="polite">
            {cell
              ? `${graph.nodes[cell.y].name} ↔ ${graph.nodes[cell.x].name} · weight ${numeric(cell.value)}`
              : `${graph.nodes.length} × ${graph.nodes.length} symmetric matrix · hover to inspect weights`}
          </div>
        </>
      ) : (
        <Empty title="Load a connectome">
          The matrix will display the real weighted edges returned by the
          research API.
        </Empty>
      )}
    </div>
  );
}
export function Pipeline({ state }: { state: WorkspaceState }) {
  const c = state.connectome,
    s = state.simulation;
  const stages = [
    {
      id: "01",
      name: "Structural network",
      icon: Database,
      done: !!c,
      detail: c
        ? `${c.nodes.length} regions · ${c.edges.length} edges`
        : "Awaiting connectome",
    },
    {
      id: "02",
      name: "Virtual resection",
      icon: Box,
      done: !!s,
      detail: `${state.regions.length} selected regions · ${state.method}`,
    },
    {
      id: "03",
      name: "Graph measurement",
      icon: Network,
      done: !!s,
      detail: s
        ? `Efficiency Δ ${numeric(s.delta.efficiency)}`
        : "Awaiting simulation",
    },
    {
      id: "04",
      name: "Model estimate",
      icon: Sparkles,
      done: !!state.prediction,
      detail: state.prediction
        ? "Bootstrap interval available"
        : "Awaiting prediction",
    },
  ];
  return (
    <div className="analysis-page">
      <div className="section-intro">
        <div>
          <span className="eyebrow">OPEN THE BLACK BOX</span>
          <h2>From connections to consequences.</h2>
          <p>
            Every result traces back to a graph, a resection definition, and a
            reproducible calculation.
          </p>
        </div>
        <GitBranch size={34} />
      </div>
      <div className="pipeline-stages">
        {stages.map((stage, i) => (
          <div
            className={`pipeline-stage ${stage.done ? "done" : ""}`}
            key={stage.id}
          >
            <div className="stage-top">
              <span>{stage.id}</span>
              {stage.done ? <Check size={15} /> : <stage.icon size={17} />}
            </div>
            <h3>{stage.name}</h3>
            <p>{stage.detail}</p>
            {i < 3 && <ArrowRight className="stage-arrow" size={17} />}
          </div>
        ))}
      </div>
      <div className="pipeline-columns">
        <section className="panel analysis-panel">
          <Matrix state={state} />
        </section>
        <div className="pipeline-explanations">
          <section className="panel analysis-panel">
            <span className="eyebrow">THE TRANSFORMATION</span>
            <h2>A resection changes the edges.</h2>
            <p className="panel-description">
              Each atlas region is a node. A weighted edge represents structural
              connectivity between two nodes. Removal fractions modify these
              connections.
            </p>
            <div className="equation">
              <span>
                {state.method === "weighted"
                  ? "w′ᵢⱼ = wᵢⱼ (1 − rᵢ) (1 − rⱼ)"
                  : "w′ᵢⱼ = 0 if rᵢ ≥ 0.5 or rⱼ ≥ 0.5"}
              </span>
              <small>
                {state.method === "weighted"
                  ? "Original weight × retained source × retained target"
                  : "Nodes removed by at least 50% lose every incident connection"}
              </small>
            </div>
            <div className="equation-key">
              <span>
                <b>w</b> connection weight
              </span>
              <span>
                <b>r</b> fraction removed
              </span>
            </div>
            <ArrowDown className="flow-arrow" size={20} />
            <div className="explain-result">
              <Network size={22} />
              <div>
                <h3>Recompute the entire graph</h3>
                <p>
                  Efficiency, density, clustering, modularity, components, and
                  hub disruption are calculated in the independent Python
                  engine.
                </p>
              </div>
            </div>
            {s && (
              <div className="actual-result">
                <span>Computed total connection weight loss</span>
                <b>{percent(s.connectivity_loss)}</b>
              </div>
            )}
          </section>
          <section className="panel analysis-panel">
            <span className="eyebrow">WHAT THE SCENE REPRESENTS</span>
            <h2>Synthetic anatomy. Explicit limits.</h2>
            <p className="panel-description">
              The folded 3D surface is a procedural illustration, not a
              segmented MRI. Demo coordinates, connections, resections, and
              outcome labels are synthetic. An imported connectome retains its
              own provenance.
            </p>
            <p className="panel-description">
              Network change is a mathematical result for the supplied graph. It
              does not establish a safe surgical boundary or predict a real
              clinical outcome.
            </p>
          </section>
        </div>
      </div>
      {s && (
        <section className="panel analysis-panel">
          <span className="eyebrow">REPRODUCIBILITY</span>
          <h2>The record behind the result</h2>
          <ProvenanceDetails
            provenance={s.provenance}
            label="Inspect simulation provenance"
          />
        </section>
      )}
    </div>
  );
}
