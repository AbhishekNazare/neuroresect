"""Generate aggregate ROC/calibration figures from an exported real-data experiment."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve

parser = argparse.ArgumentParser()
parser.add_argument("results")
parser.add_argument("--output", required=True)
args = parser.parse_args()
report = json.loads(Path(args.results).read_text())
y = [row["target"] for row in report["predictions"]]
plt.rcParams.update({"font.size": 11, "svg.hashsalt": "neuroresect-ideas-v1"})
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
for key, color in zip(("A", "B", "C"), ("#226b80", "#bb633c", "#6956a3"), strict=True):
    probabilities = [row[key] for row in report["predictions"]]
    fpr, tpr, _ = roc_curve(y, probabilities)
    auc = report["models"][key]["metrics"]["roc_auc"]
    axes[0].plot(fpr, tpr, color=color, label=f"{key}: AUC {auc:.3f}", linewidth=2)
    reliability = report["models"][key]["reliability"]
    axes[1].plot(
        reliability["mean_predicted"],
        reliability["observed_fraction"],
        marker="o",
        color=color,
        label=key,
    )
for axis in axes:
    axis.plot([0, 1], [0, 1], "--", color="#888888", linewidth=1)
    axis.set(xlim=(0, 1), ylim=(0, 1))
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False)
axes[0].set(title="Held-out ROC", xlabel="False positive rate", ylabel="True positive rate")
axes[1].set(
    title="Held-out calibration (5 quantile bins)",
    xlabel="Mean predicted probability",
    ylabel="Observed class-1 fraction",
)
fig.suptitle(
    f"IDEAS II: {report['patient_count']} surgical patients · first-year ILAE 1 vs 2–6\nRetrospective internal validation · no demonstrated network-feature benefit",
    fontsize=12,
)
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(output, metadata={"Date": None} if output.suffix == ".svg" else None, dpi=160)
plt.close(fig)
