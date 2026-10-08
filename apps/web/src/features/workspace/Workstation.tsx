"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  ChevronDown,
  CircleHelp,
  CirclePause,
  CirclePlay,
  Database,
  FlaskConical,
  GitBranch,
  GitCompareArrows,
  Layers3,
  Network,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { useWorkspace } from "./useWorkspace";
import { Logo, ProvenanceDetails, Spinner } from "./primitives";
import { RegionEditor } from "./RegionEditor";
import { MetricCards, PredictionPanel } from "./Results";
import { Scenarios } from "../analysis/Scenarios";
import { Experiments } from "../analysis/Experiments";
import { Pipeline } from "../analysis/Pipeline";
import type { Tab } from "@/lib/types";
import { post } from "@/lib/api";
const BrainScene = dynamic(() => import("../brain/BrainScene"), {
  ssr: false,
  loading: () => (
    <div className="scene-loading">
      <Spinner label="Preparing 3D workspace…" />
    </div>
  ),
});
const nav = [
  { id: "workspace" as Tab, label: "Workspace", icon: Box },
  { id: "scenarios" as Tab, label: "Scenarios", icon: GitCompareArrows },
  { id: "experiments" as Tab, label: "Experiments", icon: FlaskConical },
  { id: "pipeline" as Tab, label: "How it works", icon: GitBranch },
];
export function Workstation() {
  const state = useWorkspace();
  const [tab, setTab] = useState<Tab>("workspace"),
    [mode, setMode] = useState<
      "anatomy" | "network" | "resection" | "sensitivity"
    >("network"),
    [threshold, setThreshold] = useState(0.35),
    [transition, setTransition] = useState(0),
    [hemisphere, setHemisphere] = useState<"both" | "left" | "right">("both"),
    [hovered, setHovered] = useState<number | null>(null),
    [autoRotate, setAutoRotate] = useState(true),
    [motionAllowed, setMotionAllowed] = useState(false),
    [help, setHelp] = useState(false),
    [importing, setImporting] = useState(false),
    [importNotice, setImportNotice] = useState("");
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setMotionAllowed(!mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!state.simulation || !motionAllowed) {
      setTransition(state.simulation ? 1 : 0);
      return;
    }
    let frame = 0;
    const started = performance.now();
    const animate = (time: number) => {
      const t = Math.min(1, (time - started) / 900);
      setTransition(t * t * (3 - 2 * t));
      if (t < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [state.simulation, motionAllowed]);
  useEffect(() => {
    setHovered(null);
    setHemisphere("both");
  }, [state.patientId, state.atlasId]);
  useEffect(() => {
    if (!help) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setHelp(false);
      if (e.key === "Tab") {
        const items = Array.from(
          document.querySelectorAll<HTMLButtonElement>(".guide-modal button"),
        );
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.querySelector<HTMLButtonElement>(".help-trigger")?.focus();
    };
  }, [help]);
  const c = state.connectome;
  const maxWeight = c ? Math.max(...c.edges.map((e) => e.weight), 0.001) : 1;
  const visibleEdges =
    c?.edges.filter((e) => e.weight / maxWeight >= threshold).length || 0;
  function selectRegion(id: number) {
    const existing = state.regions.some((r) => r.region_id === id);
    state.editRegions(
      existing
        ? state.regions.filter((r) => r.region_id !== id)
        : [...state.regions, { region_id: id, fraction_removed: 0.5 }],
    );
  }
  async function importFile(file?: File) {
    if (!file) return;
    setImporting(true);
    setImportNotice("");
    state.setError("");
    try {
      if (file.size > 8 * 1024 * 1024)
        throw new Error("Choose a connectome JSON file smaller than 8 MiB.");
      const data = JSON.parse(await file.text());
      await post("/datasets/import", data);
      setImportNotice("Connectome imported. Select its patient to explore.");
      state.retry();
    } catch (e) {
      state.setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setImporting(false);
      if (upload.current) upload.current.value = "";
    }
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Logo />
          <span className="version-label">RESEARCH WORKSTATION / 01</span>
        </div>
        <div className="workspace-label">
          <span className="live-dot" />
          CONNECTOME LAB<span>⌘</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
              aria-current={tab === item.id ? "page" : undefined}
            >
              <item.icon size={17} />
              <span>{item.label}</span>
              {tab === item.id && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <div className="sidebar-section">
          <div className="section-label">
            RESEARCH SUBJECT
            <span className="tag tiny">
              {state.patient && !state.patient.synthetic ? "IMPORTED" : "DEMO"}
            </span>
          </div>
          <label className="patient-select">
            <span className="patient-avatar">
              <Activity size={19} />
            </span>
            <select
              aria-label="Research patient"
              value={state.patientId}
              onChange={(e) => state.changePatient(e.target.value)}
              disabled={!state.patients.length}
            >
              {!state.patients.length && <option>Loading subjects…</option>}
              {state.patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label || p.id}
                </option>
              ))}
            </select>
            <ChevronDown size={13} />
          </label>
          {state.patient && (
            <div className="subject-details">
              <div>
                <span>Subject ID</span>
                <b>{state.patient.id}</b>
              </div>
              <div>
                <span>Age / sex</span>
                <b>
                  {state.patient.age ?? "Unknown"} /{" "}
                  {state.patient.sex ?? "Unknown"}
                </b>
              </div>
              <div>
                <span>Epilepsy duration</span>
                <b>
                  {state.patient.epilepsy_duration == null
                    ? "Unknown"
                    : `${state.patient.epilepsy_duration} years`}
                </b>
              </div>
            </div>
          )}
        </div>
        <div className="sidebar-section">
          <label className="section-label" htmlFor="atlas">
            BRAIN PARCELLATION
          </label>
          <div className="atlas-select">
            <Layers3 size={15} />
            <select
              id="atlas"
              value={state.atlasId}
              onChange={(e) => state.changeAtlas(e.target.value)}
              disabled={!state.atlases.length}
            >
              {state.atlases
                .filter(
                  (a) =>
                    !state.patient ||
                    state.patient.available_atlases.includes(a.id),
                )
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </select>
            <ChevronDown size={12} />
          </div>
          <div className="atlas-note">
            {c ? `${c.nodes.length} atlas regions` : "Atlas-defined regions"}
            <span>Two hemispheres</span>
          </div>
        </div>
        <div className="sidebar-bottom">
          <input
            ref={upload}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(e) => importFile(e.target.files?.[0])}
          />
          <button
            className="import-button"
            onClick={() => upload.current?.click()}
            disabled={importing}
          >
            <Upload size={15} />
            {importing ? "Validating import…" : "Import connectome"}
            <ArrowUpRight size={13} />
          </button>
          <div className="research-notice">
            <div className="notice-icon">
              <FlaskConical size={16} />
            </div>
            <strong>Built for discovery.</strong>
            <p>
              Research use only.
              <br />
              Not for clinical decision-making.
            </p>
          </div>
          <div className="sidebar-footer">
            <span className={`status-dot ${c ? "" : "offline"}`} />
            {c
              ? "Research engine connected"
              : state.loading
                ? "Connecting to engine"
                : "Engine unavailable"}
            <span>v0.1</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Research</span>
            <span>/</span>
            <strong>{nav.find((n) => n.id === tab)?.label}</strong>
          </div>
          <div className="topbar-actions">
            <span className="environment-tag">
              <span />
              {c && !c.synthetic ? "IMPORTED RESEARCH" : "SYNTHETIC RESEARCH"}
            </span>
            <button
              className="icon-button help-trigger"
              onClick={() => setHelp(true)}
              aria-label="Open workstation guide"
            >
              <CircleHelp size={18} />
            </button>
            <div className="user-avatar" title="Local research workspace">
              NR
            </div>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="tiny-line" />
                STRUCTURAL CONNECTOMICS
              </div>
              <h1>
                {tab === "workspace" ? (
                  <>
                    Understand the network.
                    <br className="mobile-break" />
                    <span> Explore the impact.</span>
                  </>
                ) : (
                  nav.find((n) => n.id === tab)?.label
                )}
              </h1>
              <p>
                {tab === "workspace"
                  ? "A virtual resection workspace for brain network research."
                  : `${state.patient?.label || "Research workspace"} · ${state.atlasId} · Reproducible by design`}
              </p>
            </div>
            {state.scenario ? (
              <a
                className="secondary-button export-button"
                href={`/api/v1/scenarios/${state.scenario.id}/export`}
                download
              >
                <ArrowDownToLine size={14} />
                Export scenario
              </a>
            ) : (
              <button
                className="secondary-button export-button"
                onClick={() => setTab("pipeline")}
              >
                <GitBranch size={14} />
                Explore the pipeline
                <ArrowUpRight size={13} />
              </button>
            )}
          </div>
          <div className="research-banner">
            <FlaskConical size={14} />
            <span>
              <strong>
                {c && !c.synthetic
                  ? "Imported research connectome."
                  : "Synthetic research environment."}
              </strong>{" "}
              Illustrative surface geometry. No clinical interpretation.
            </span>
            <span className="banner-tag">TRANSPARENT BY DESIGN</span>
          </div>
          {state.error && (
            <div className="error-banner" role="alert">
              <div>
                <strong>Unable to complete this request</strong>
                <p>{state.error}</p>
              </div>
              <button className="secondary-button" onClick={state.retry}>
                <RefreshCw size={14} />
                Reconnect
              </button>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => state.setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {importNotice && (
            <div className="success-banner" role="status">
              <Check size={16} />
              {importNotice}
              <button
                className="icon-button"
                aria-label="Dismiss import notification"
                onClick={() => setImportNotice("")}
              >
                <X size={14} />
              </button>
            </div>
          )}
          {state.busy && (
            <div className="job-progress" role="status">
              <Spinner label={state.busy} />
              <span>{state.job?.stage || "Preparing job"}</span>
              <progress
                max="100"
                value={
                  state.job
                    ? state.job.progress <= 1
                      ? state.job.progress * 100
                      : state.job.progress
                    : 0
                }
              />
            </div>
          )}
          {tab === "workspace" && (
            <>
              <div className="workspace-grid">
                <div className="viewer-column">
                  <section className="brain-panel panel">
                    <div className="brain-toolbar">
                      <div className="scene-title">
                        <span className="live-dot" />
                        <strong>Brain network</strong>
                        <span className="tag">3D VIEW</span>
                      </div>
                      <div className="segmented" aria-label="Brain view mode">
                        {(
                          [
                            "anatomy",
                            "network",
                            "resection",
                            "sensitivity",
                          ] as const
                        ).map((m) => (
                          <button
                            key={m}
                            className={mode === m ? "active" : ""}
                            onClick={() => setMode(m)}
                          >
                            {m[0].toUpperCase() + m.slice(1)}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="scene-container">
                      <div className="scene-meta">
                        <span>{state.patientId || "CONNECTING"}</span>
                        <span>
                          {state.atlasId.toUpperCase()} ·{" "}
                          {c?.nodes.length || "—"} NODES
                        </span>
                      </div>
                      <div className="scene-orientation left">L</div>
                      <div className="scene-orientation right">R</div>
                      {c ? (
                        <BrainScene
                          connectome={c}
                          regions={
                            state.method === "binary"
                              ? state.regions.map((r) => ({
                                  ...r,
                                  fraction_removed:
                                    r.fraction_removed >= 0.5 ? 1 : 0,
                                }))
                              : state.regions
                          }
                          mode={mode}
                          threshold={threshold}
                          transition={transition}
                          sensitivityScores={state.sensitivity?.region_scores}
                          hemisphere={hemisphere}
                          onSelect={selectRegion}
                          hovered={hovered}
                          onHover={setHovered}
                          autoRotate={autoRotate && motionAllowed}
                        />
                      ) : (
                        <div className="scene-loading">
                          {state.loading ? (
                            <Spinner label="Loading the structural connectome…" />
                          ) : (
                            <>
                              <Network size={34} />
                              <h3>Connect to the research engine</h3>
                              <p>
                                Start the API to load subjects, atlases, and
                                network data.
                              </p>
                              <button
                                className="secondary-button"
                                onClick={state.retry}
                              >
                                <RefreshCw size={14} />
                                Try again
                              </button>
                            </>
                          )}
                        </div>
                      )}
                      <div className="scene-bottom-label">
                        <span className="tag outline">
                          {mode === "sensitivity"
                            ? state.sensitivity
                              ? "HEATMAP · EFFICIENCY SENSITIVITY"
                              : "RUN SENSITIVITY IN SCENARIOS TO COLOR REGIONS"
                            : "PROCEDURAL SYNTHETIC ANATOMY"}
                        </span>
                        <div>
                          <span className="legend-dot teal" />
                          Atlas region
                          <span className="legend-dot amber" />
                          Selected resection
                        </div>
                      </div>
                    </div>
                    <div className="scene-controls">
                      <div className="scene-settings">
                        <label>
                          Hemisphere
                          <select
                            aria-label="Visible hemisphere"
                            value={hemisphere}
                            onChange={(e) =>
                              setHemisphere(e.target.value as typeof hemisphere)
                            }
                          >
                            <option value="both">Both hemispheres</option>
                            <option value="left">Left only</option>
                            <option value="right">Right only</option>
                          </select>
                        </label>
                        <label className="threshold-label">
                          Edge threshold <span>{threshold.toFixed(2)}</span>
                          <input
                            aria-label="Display edge threshold"
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={threshold}
                            onChange={(e) =>
                              setThreshold(Number(e.target.value))
                            }
                          />
                        </label>
                        <button
                          className={`icon-button rotation-button ${autoRotate && motionAllowed ? "active" : ""}`}
                          onClick={() => setAutoRotate((v) => !v)}
                          aria-label={
                            autoRotate
                              ? "Pause automatic rotation"
                              : "Enable automatic rotation"
                          }
                          aria-pressed={autoRotate && motionAllowed}
                          disabled={!motionAllowed}
                        >
                          {autoRotate && motionAllowed ? (
                            <CirclePause size={19} />
                          ) : (
                            <CirclePlay size={19} />
                          )}
                        </button>
                      </div>
                      <div className="transition-control">
                        <span>Before resection</span>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step=".01"
                          value={transition}
                          onChange={(e) =>
                            setTransition(Number(e.target.value))
                          }
                          disabled={!state.simulation}
                          aria-label="Before and after resection transition"
                        />
                        <span>After resection</span>
                        <b>{Math.round(transition * 100)}%</b>
                      </div>
                      <div className="scene-footnote">
                        <span>
                          Drag to orbit · scroll to zoom · click a node to
                          select
                        </span>
                        <span>
                          {visibleEdges} displayed edges · visual filter only
                        </span>
                      </div>
                    </div>
                  </section>
                  <MetricCards state={state} />
                  <div className="workspace-bottom-note">
                    <span>
                      <span className="status-dot" />
                      {state.simulation
                        ? "Metrics computed by neurocore"
                        : "Ready to explore · simulate to compute metrics"}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => setTab("pipeline")}
                    >
                      See how it works
                      <ArrowRight size={12} />
                    </button>
                  </div>
                  {state.simulation && (
                    <ProvenanceDetails
                      provenance={state.simulation.provenance}
                    />
                  )}
                </div>
                <div className="inspector-column">
                  <RegionEditor state={state} onHover={setHovered} />
                  <PredictionPanel state={state} />
                </div>
              </div>
            </>
          )}
          {tab === "scenarios" && (
            <Scenarios
              state={state}
              openWorkspace={() => setTab("workspace")}
            />
          )}
          {tab === "experiments" && <Experiments atlasId={state.atlasId} />}{" "}
          {tab === "pipeline" && <Pipeline state={state} />}
          <footer className="page-footer">
            <span>
              NEURORESECT<span className="footer-separator">/</span>From
              structure to insight.
            </span>
            <span>Independent science. Reproducible research.</span>
          </footer>
        </main>
      </div>
      {help && (
        <div className="modal-overlay" onClick={() => setHelp(false)}>
          <section
            className="guide-modal panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="guide-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-heading">
              <Logo small />
              <button
                className="icon-button"
                onClick={() => setHelp(false)}
                aria-label="Close guide"
                autoFocus
              >
                <X size={19} />
              </button>
            </div>
            <span className="eyebrow">A QUICK ORIENTATION</span>
            <h2 id="guide-title">Your research workspace.</h2>
            <ol>
              <li>
                <strong>Choose a subject and atlas.</strong>
                <p>
                  The demo includes synthetic networks with reproducible
                  connections.
                </p>
              </li>
              <li>
                <strong>Define a virtual resection.</strong>
                <p>
                  Click 3D nodes or browse the region editor. Adjust removal
                  fractions and simulate.
                </p>
              </li>
              <li>
                <strong>Follow the consequences.</strong>
                <p>
                  Inspect graph changes, compare scenarios, or run an A/B/C
                  experiment.
                </p>
              </li>
              <li>
                <strong>Inspect the evidence.</strong>
                <p>
                  Open How it works for the actual adjacency matrix,
                  transformation, and provenance.
                </p>
              </li>
            </ol>
            <button
              className="primary-button full"
              onClick={() => setHelp(false)}
            >
              Start exploring
              <ArrowRight size={15} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
