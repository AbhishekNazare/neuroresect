"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Download, FlaskConical } from "lucide-react";
import { api, numeric, poll, post, title } from "@/lib/api";
import type { Experiment, Job } from "@/lib/types";
import { ExperimentCharts } from "./ExperimentCharts";
import { Empty, ProvenanceDetails, Spinner } from "../workspace/primitives";
export function Experiments({ atlasId }: { atlasId: string }) {
  const [name, setName] = useState("Network disruption · A/B/C study"),
    [model, setModel] = useState("logistic"),
    [seed, setSeed] = useState(42),
    [folds, setFolds] = useState(3),
    [cohort, setCohort] = useState(36);
  const [experiments, setExperiments] = useState<Experiment[]>([]),
    [experiment, setExperiment] = useState<Experiment | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [stage, setStage] = useState(""),
    [metric, setMetric] = useState("roc_auc");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    api<Experiment[]>("/experiments", { signal: ac.signal })
      .then(setExperiments)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => {
      ac.abort();
      controller.current?.abort();
    };
  }, []);
  const entries = Object.entries(experiment?.models || {});
  const metricNames = [
    ...new Set(entries.flatMap(([, m]) => Object.keys(m.metrics))),
  ];
  const activeMetric = metricNames.includes(metric)
    ? metric
    : metricNames[0] || "roc_auc";
  async function run() {
    controller.current?.abort();
    const ac = new AbortController();
    controller.current = ac;
    setBusy(true);
    setError("");
    setExperiment(null);
    try {
      const job = await post<Job<Experiment>>(
        "/experiments",
        {
          name,
          seed,
          folds,
          n_patients: cohort,
          model_type: model,
          atlas_id: atlasId,
        },
        ac.signal,
      );
      const result = await poll(
        job,
        (j) => setStage(j.stage || j.status.toLowerCase()),
        ac.signal,
      );
      setExperiment(result);
      setExperiments((current) => [
        result,
        ...current.filter((e) => e.id !== result.id),
      ]);
    } catch (e) {
      if (e instanceof Error && e.name !== "AbortError") setError(e.message);
    } finally {
      if (!ac.signal.aborted) setBusy(false);
    }
  }
  async function open(id: string) {
    setError("");
    try {
      setExperiment(await api<Experiment>(`/experiments/${id}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load experiment.");
    }
  }
  return (
    <div className="analysis-page">
      <div className="section-intro">
        <div>
          <span className="eyebrow">THE RESEARCH QUESTION</span>
          <h2>Does network disruption add predictive value?</h2>
          <p>
            Run patient-separated validation across three feature sets. Let the
            measured results answer.
          </p>
        </div>
        <FlaskConical size={34} />
      </div>
      <div className="model-cards">
        {[
          {
            id: "A",
            title: "Clinical baseline",
            text: "Patient characteristics and resection features.",
          },
          {
            id: "B",
            title: "+ Baseline connectome",
            text: "Add pre-resection network topology.",
          },
          {
            id: "C",
            title: "+ Virtual resection",
            text: "Add simulated post-resection and disruption features.",
          },
        ].map((m) => (
          <article className="model-card" key={m.id}>
            <span>{m.id}</span>
            <div>
              <h3>{m.title}</h3>
              <p>{m.text}</p>
            </div>
          </article>
        ))}
      </div>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">REPRODUCIBLE EXPERIMENT</span>
            <h2>Configure a study</h2>
          </div>
          <span className="tag amber">SYNTHETIC COHORT</span>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="experiment-form">
            <label className="field wide">
              Experiment name
              <input
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={busy}
              />
            </label>
            <label className="field">
              Estimator
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={busy}
              >
                <option value="logistic">Logistic regression</option>
                <option value="random_forest">Random forest</option>
                <option value="svm">Support vector machine</option>
              </select>
            </label>
            <label className="field">
              Synthetic patients
              <input
                type="number"
                min="24"
                max="240"
                step="1"
                value={cohort}
                onChange={(e) => setCohort(Number(e.target.value))}
                disabled={busy}
              />
            </label>
            <label className="field">
              Patient-separated folds
              <input
                type="number"
                min="2"
                max="5"
                value={folds}
                onChange={(e) => setFolds(Number(e.target.value))}
                disabled={busy}
              />
            </label>
            <label className="field">
              Random seed
              <input
                type="number"
                min="0"
                max="2147483647"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                disabled={busy}
              />
            </label>
          </div>
          <div className="form-footer">
            <p>
              <Check size={14} />
              Atlas: {atlasId} · All feature sets use the same patient splits.
            </p>
            <button className="primary-button" disabled={busy} type="submit">
              {busy ? (
                <Spinner label={stage || "Starting experiment…"} />
              ) : (
                <>
                  Run A/B/C experiment
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </div>
        </form>
        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
      </section>
      {experiment ? (
        <section className="panel analysis-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">MEASURED RESULTS</span>
              <h2>{experiment.name}</h2>
            </div>
            <a
              className="secondary-button"
              href={`/api/v1/experiments/${experiment.id}/export`}
              download
            >
              <Download size={14} />
              Export
            </a>
          </div>
          <p className="panel-description">
            Synthetic validation describes this generated cohort only. A higher
            score does not establish clinical benefit.
          </p>
          <label className="inline-select">
            Compare metric
            <select
              value={activeMetric}
              onChange={(e) => setMetric(e.target.value)}
            >
              {metricNames.map((m) => (
                <option key={m} value={m}>
                  {title(m)}
                </option>
              ))}
            </select>
          </label>
          <div className="experiment-bars">
            {entries.map(([key, m]) => {
              const value = m.metrics[activeMetric];
              return (
                <div key={key}>
                  <span className="model-letter">
                    {key.replace("model_", "").toUpperCase()}
                  </span>
                  <div className="model-bar-info">
                    <strong>{m.name}</strong>
                    <div className="bar-track">
                      <div
                        style={{
                          width: `${typeof value === "number" ? Math.min(100, Math.max(0, value * 100)) : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                  <b>
                    {typeof value === "number" ? numeric(value) : "Unavailable"}
                  </b>
                </div>
              );
            })}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  {entries.map(([key]) => (
                    <th key={key}>{key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricNames.map((m) => (
                  <tr key={m}>
                    <td>{title(m)}</td>
                    {entries.map(([key, modelResult]) => (
                      <td key={key}>
                        {typeof modelResult.metrics[m] === "number"
                          ? numeric(modelResult.metrics[m] as number)
                          : "Unavailable"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ExperimentCharts models={experiment.models} />
          <details className="provenance">
            <summary>Inspect patient folds and feature sets</summary>
            <pre>
              {JSON.stringify(
                {
                  folds: experiment.folds,
                  feature_sets: Object.fromEntries(
                    entries.map(([key, m]) => [key, m.feature_set]),
                  ),
                },
                null,
                2,
              )}
            </pre>
          </details>
          <ProvenanceDetails provenance={experiment.provenance} />
        </section>
      ) : (
        <section className="panel">
          <Empty
            title={
              busy
                ? "The research engine is computing your study"
                : "Your experiment results will appear here"
            }
          >
            {busy
              ? "Folds, transformations, model fits, and held-out predictions are computed by the Python engine. You can inspect their provenance when the job completes."
              : "Choose a seed and estimator, then compare A, B, and C on the same synthetic cohort."}
          </Empty>
        </section>
      )}
      {experiments.length > 0 && (
        <section className="panel analysis-panel">
          <div className="panel-heading">
            <h2>Experiment history</h2>
            <span className="tag">{experiments.length} RUNS</span>
          </div>
          <div className="history-list">
            {experiments.map((e) => (
              <button key={e.id} onClick={() => open(e.id)} disabled={busy}>
                <FlaskConical size={16} />
                <span>
                  <strong>{e.name}</strong>
                  <small>
                    {e.atlas_id} · seed {e.seed} · {e.status}
                  </small>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
