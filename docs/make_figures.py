import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RESULTS = REPORTS / "serving_results"
OUT = ROOT / "docs" / "img"
BLUE, ORANGE, GRAY = "#2a6fb0", "#d9822b", "#7a7a7a"


def ablation_chart() -> None:
    """Plot test PR-AUC per ablation variant."""
    data = json.loads((REPORTS / "ablation.json").read_text())
    names = list(data)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    width = 0.38
    for i, (pop, label, color) in enumerate(
        [("transfer_cash_out", "TRANSFER and CASH_OUT rows", BLUE), ("all_rows", "All rows", ORANGE)]
    ):
        vals = [data[n]["pr_auc"][pop] for n in names]
        xs = [j + (i - 0.5) * width for j in range(len(names))]
        bars = ax.bar(xs, vals, width, label=label, color=color)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.3f}", ha="center", fontsize=7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace(" + ", "\n+ ", 1) for n in names], fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Test PR-AUC")
    ax.set_title("Test PR-AUC by additive ablation variant")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "ablation_pr_auc.png", dpi=150)
    plt.close(fig)


def hpa_chart() -> None:
    """Plot HPA replica count against p95 latency around the load step."""
    meta = json.loads((RESULTS / "hpa_step.json").read_text())
    step = meta["step_start_epoch"]
    with open(RESULTS / "raw" / "hpa_step" / "load_stats_history.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["Name"] == "Aggregated" and r["95%"] not in ("", "N/A", "0")]
    t = [float(r["Timestamp"]) - step for r in rows]
    p95 = [float(r["95%"]) for r in rows]
    series = meta["series"]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(t, p95, color=ORANGE, lw=1.2, label="p95 latency")
    ax.set_xlabel("Seconds relative to the load step")
    ax.set_ylabel("p95 latency (ms)", color=ORANGE)
    ax.axvline(0, color=GRAY, ls="--", lw=0.8)
    ax.axvline(meta["load"]["step_seconds"], color=GRAY, ls="--", lw=0.8)
    ax2 = ax.twinx()
    ax2.step([s["t"] for s in series], [s["current"] for s in series], where="post", color=BLUE, lw=2, label="Replicas")
    ax2.set_ylabel("Replicas", color=BLUE)
    ax2.set_ylim(0, meta["max_replicas"] + 1)
    ax.set_title("HPA replica count and p95 latency, step profile")
    fig.tight_layout()
    fig.savefig(OUT / "hpa_step_replicas_p95.png", dpi=150)
    plt.close(fig)


def selfheal_chart() -> None:
    """Plot self-heal recovery time per failure type."""
    data = json.loads((RESULTS / "selfheal.json").read_text())
    labels = ["Pod deleted\n(replacement Ready)", "Liveness failure\n(restart, Ready again)"]
    vals = [data["pod_delete"]["replacement_ready_seconds"], data["liveness_failure"]["ready_after_seconds"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, vals, color=[BLUE, ORANGE], width=0.5)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.2, f"{v:.1f} s", ha="center")
    ax.set_ylabel("Seconds")
    ax.set_ylim(0, max(vals) * 1.25)
    ax.set_title("Self-heal recovery time")
    fig.tight_layout()
    fig.savefig(OUT / "selfheal_recovery.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ablation_chart()
    hpa_chart()
    selfheal_chart()
