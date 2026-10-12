"use client";
import { useEffect, useState } from "react";
import { Download, Database, ArrowRight } from "lucide-react";
import { api, numeric, title } from "@/lib/api";
import type { RealStudy } from "@/lib/types";
import { Spinner } from "../workspace/primitives";
import { ExperimentCharts } from "./ExperimentCharts";

const metrics = {
  roc_auc: "ROC-AUC",
  pr_auc: "Average precision",
  balanced_accuracy: "Balanced accuracy",
  brier: "Brier score",
};

export function RealStudyResults() {
  const [study, setStudy] = useState<RealStudy | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [metric, setMetric] = useState<keyof typeof metrics>("roc_auc");
  const [model, setModel] = useState("A");
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api<RealStudy>("/research-studies/ideas-year1-baseline-v1", {
      signal: controller.signal,
    })
      .then(setStudy)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [retry]);
  if (error)
    return (
      <section className="analysis-page">
        <div role="alert" className="panel analysis-panel">
          <h2>Real study unavailable</h2>
          <p>{error}</p>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setRetry((value) => value + 1)}
          >
            Retry real study
          </button>
        </div>
      </section>
    );
  if (!study)
    return (
      <div className="analysis-page">
        <Spinner label="Loading saved real study…" />
      </div>
    );
  const { cohort, methods } = study;
  const features = study.models[model].feature_set;
  const interval = study.paired_auc_C_minus_A.conditional_95_percent_interval;
  return (
    <div className="analysis-page real-study">
      <div className="section-intro">
        <div>
          <span className="eyebrow">SAVED REAL-DATA BENCHMARK</span>
          <h2>{study.name}</h2>
          <p>
            Actual IDEAS data. Retrospective, patient-separated evaluation. This
            saved report does not run a new fit or enable patient predictions.
          </p>
        </div>
        <Database size={34} />
      </div>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">FROM SOURCE TO COHORT</span>
            <h2>Who entered the analysis?</h2>
          </div>
          <span className="tag amber">REAL DATA · RESEARCH ONLY</span>
        </div>
        <div className="real-cohort-flow">
          <article>
            <strong>{cohort.network_subjects}</strong>
            <span>Network subjects</span>
            <small>{cohort.healthy_controls} healthy controls excluded</small>
          </article>
          <ArrowRight aria-hidden="true" />
          <article>
            <strong>{cohort.surgical_patients}</strong>
            <span>Surgical patients</span>
            <small>
              {Object.entries(cohort.surgical_exclusions)
                .map(
                  ([reason, count]) =>
                    `${count} ${title(reason).toLowerCase()}`,
                )
                .join(" · ")}
            </small>
          </article>
          <ArrowRight aria-hidden="true" />
          <article>
            <strong>{cohort.eligible_patients}</strong>
            <span>Eligible patients</span>
            <small>
              {cohort.class_counts["1"]} class 1 · {cohort.class_counts["0"]}{" "}
              classes 2–6
            </small>
          </article>
        </div>
        <p className="real-study-note">
          Endpoint: {study.endpoint.definition}. Exclusion reasons can overlap.
          Region names are mapped; patient anatomy is not registered.
        </p>
      </section>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">HELD-OUT EVIDENCE</span>
            <h2>Compare the three feature sets</h2>
          </div>
          <a
            className="secondary-button"
            href={`/api/v1/research-studies/${study.id}/export`}
            download
          >
            <Download size={16} />
            Export aggregate report
          </a>
        </div>
        <div className="real-study-finding">
          <strong>No useful discrimination in this baseline.</strong>
          <p>
            Adding network and simulated-resection features did not improve
            prediction. These results do not establish clinical utility.
          </p>
        </div>
        <label className="field">
          Comparison metric
          <select
            aria-label="Real study metric"
            value={metric}
            onChange={(event) =>
              setMetric(event.target.value as keyof typeof metrics)
            }
          >
            {Object.entries(metrics).map(([key, label]) => (
              <option value={key} key={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className="real-study-note">
          {metric === "brier"
            ? "Lower Brier scores indicate better probability accuracy."
            : "Higher values indicate better performance on this metric."}{" "}
          All comparisons use identical held-out patients.
        </p>
        <div className="real-metric-cards">
          {Object.entries(study.models).map(([key, value]) => (
            <button
              type="button"
              key={key}
              aria-pressed={model === key}
              aria-label={`Inspect real model ${key}`}
              onClick={() => setModel(key)}
            >
              <span className="tag">MODEL {key}</span>
              <strong>{numeric(value.metrics[metric] ?? undefined, 3)}</strong>
              <span>{value.name}</span>
            </button>
          ))}
        </div>
        <div className="real-feature-detail">
          <h3>Model {model} inputs</h3>
          <div>
            {(Array.isArray(features) ? features : [features]).map(
              (feature) => (
                <span key={feature} className="tag">
                  {title(feature)}
                </span>
              ),
            )}
          </div>
        </div>
        <ExperimentCharts
          models={study.models}
          predictionLabel="held-out real IDEAS patient predictions"
        />
        <p className="real-study-note">
          C − A ROC-AUC: {numeric(study.paired_auc_C_minus_A.estimate, 4)}.
          Conditional 95% interval: [{numeric(interval[0], 4)},{" "}
          {numeric(interval[1], 4)}]. {study.paired_auc_C_minus_A.method}. This
          is not full model-training uncertainty.
        </p>
      </section>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">HOW THIS RESULT WAS PRODUCED</span>
            <h2>Methods and limits</h2>
          </div>
        </div>
        <dl className="real-methods">
          <div>
            <dt>Connectivity</dt>
            <dd>
              {methods.tractography} · {methods.atlas} · {methods.measure}
            </dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>
              {methods.folds} patient-separated folds · seed {methods.seed}
            </dd>
          </div>
          <div>
            <dt>Estimator</dt>
            <dd>
              {methods.estimator} · threshold {methods.threshold}
            </dd>
          </div>
          <div>
            <dt>Preprocessing</dt>
            <dd>{methods.preprocessing}</dd>
          </div>
        </dl>
        <p className="real-study-note">
          Resection entries are interpreted as fractions in [0,1], despite the
          source website’s percentage wording. This assumption still requires
          confirmation against source imaging or methods.
        </p>
        <ul className="real-limitations">
          {study.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
        <details className="real-provenance">
          <summary>Inspect source hashes and runtime versions</summary>
          <pre>{JSON.stringify(study.provenance, null, 2)}</pre>
        </details>
      </section>
    </div>
  );
}
