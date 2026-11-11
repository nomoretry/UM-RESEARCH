"""Plot curated time-grid results; no optimization or input modification."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.metrics.read_text(encoding="utf-8"))
    cases = [("port_only_joint", "Port only: joint", "#0072B2"),
             ("two_sites_interfaces_only", "Two sites: interfaces only", "#D55E00"),
             ("two_sites_joint", "Two sites: joint", "#009E73")]
    policies = [("slot_boundary_switching", "Switching at slot boundaries"),
                ("fixed_dwell_connection", "Connection held for entire dwell")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True, layout="constrained")
    x = np.arange(3)
    for ax, (policy, title) in zip(axes, policies):
        for index, (case, label, color) in enumerate(cases):
            selected = [next(r for r in rows if r["connector_policy"] == policy and r["scenario"] == case
                             and r["slot_minutes"] == minutes) for minutes in (60, 30, 15)]
            if any(r["status"] != "optimal" or not r["validation_passed"] for r in selected):
                raise ValueError("Do not plot missing or unverified costs as zero")
            bars = ax.bar(x + (index - 1) * .25, [r["investment_cost"] for r in selected],
                          width=.24, label=label, color=color)
            ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=9)
        ax.set(title=title, xlabel="Time step (minutes)", xticks=x, xticklabels=[60, 30, 15], ylim=(0, 120))
        ax.grid(axis="y", alpha=.25)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Added investment (synthetic currency / cycle)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Same 4-hour task chain and parking windows\nOperating cost = 133.333 per cycle for every feasible case", fontsize=13)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(args.output_dir / f"investment_by_time_step.{ext}", dpi=180)
    plt.close(fig)
    (args.output_dir / "plot_environment.json").write_text(json.dumps(
        {"matplotlib": matplotlib.__version__, "numpy": np.__version__, "source_metrics": args.metrics.name,
         "note": "Plotting-only environment, separate from the MILP environment"}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
