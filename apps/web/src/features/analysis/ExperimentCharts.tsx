"use client";
import type { ExperimentModel } from "@/lib/types";

const colors = ["#79cbbc", "#ad9be0", "#e3aa6e"];
export function ExperimentCharts({
  models,
}: {
  models: Record<string, ExperimentModel>;
}) {
  const entries = Object.entries(models);
  const charts = [
    {
      title: "ROC curve",
      x: "False-positive rate",
      y: "True-positive rate",
      series: entries.map(([key, m]) => ({
        key,
        x: m.roc_curve?.fpr || [],
        y: m.roc_curve?.tpr || [],
      })),
    },
    {
      title: "Precision–recall",
      x: "Recall",
      y: "Precision",
      series: entries.map(([key, m]) => ({
        key,
        x: m.precision_recall_curve?.recall || [],
        y: m.precision_recall_curve?.precision || [],
      })),
    },
    {
      title: "Reliability diagnostic",
      x: "Mean predicted probability",
      y: "Observed fraction",
      series: entries.map(([key, m]) => ({
        key,
        x: m.calibration?.predicted || [],
        y: m.calibration?.observed || [],
      })),
    },
  ];
  return (
    <div className="study-charts">
      {charts.map((chart) => (
        <figure key={chart.title}>
          <h3>{chart.title}</h3>
          <svg
            viewBox="0 0 300 245"
            role="img"
            aria-label={`${chart.title}: ${chart.y} versus ${chart.x}, held-out synthetic predictions`}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((t) => (
              <g key={t}>
                <line
                  x1="36"
                  x2="280"
                  y1={208 - t * 184}
                  y2={208 - t * 184}
                  stroke="#263b3b"
                />
                <text
                  x="27"
                  y={212 - t * 184}
                  textAnchor="end"
                  fill="#8ca5a4"
                  fontSize="10"
                >
                  {t}
                </text>
                <text
                  x={36 + t * 244}
                  y="225"
                  textAnchor="middle"
                  fill="#8ca5a4"
                  fontSize="10"
                >
                  {t}
                </text>
              </g>
            ))}
            {chart.series.map((s, i) => (
              <polyline
                key={s.key}
                fill="none"
                stroke={colors[i]}
                strokeWidth="2"
                points={s.x
                  .map((x, j) => `${36 + x * 244},${208 - s.y[j] * 184}`)
                  .join(" ")}
              />
            ))}
          </svg>
          <figcaption>{chart.x}</figcaption>
          <div className="curve-legend">
            {entries.map(([key], i) => (
              <span key={key} style={{ color: colors[i] }}>
                ● Model {key}
              </span>
            ))}
          </div>
        </figure>
      ))}
    </div>
  );
}
