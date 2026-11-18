"""Plot the two cabinet comparisons from the published summary JSON only."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies/fleet-service"
LABELS = {"one": "E1   One port connector", "two_independent": "E2   Independent cabinets",
          "two_shared_rule": "E3   Shared, 2 × 25 kW", "two_shared_pool": "E4   Shared, flexible pool"}
COLORS = ("#175d78", "#b55322")


def save(figure, folder, name):
    for suffix in ("svg", "png"):
        figure.savefig(folder / f"cabinet_demand_{name}.{suffix}", dpi=180,
                       metadata={"Date": None} if suffix == "svg" else {})
    plt.close(figure)


def study_comparison(summary, folder):
    rows = {(r["equipment"], r["policy"]): r for r in summary["main"] if r["scenario"] == "frank"}
    policies = ("P1", "P2")
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.1), sharey=True)
    fig.subplots_adjust(left=.23, right=.97, top=.77, bottom=.19, wspace=.22)
    fig.suptitle("Peak charging demand and the value of a second port connector",
                 x=.035, y=.96, ha="left", fontsize=15, weight="bold")
    for j, policy in enumerate(policies):
        for idx, name in enumerate(LABELS):
            y = 2*(3-idx) + (.28 if j == 0 else -.28)
            row = rows[name, policy]
            values = (row["sites"]["PORT"]["peak_kw"], row["annual_operating_value_eur_2025"])
            for ax, value in zip(axes, values):
                ax.scatter(value, y, s=36, color=COLORS[j], marker=("o", "D")[j], zorder=3)
                ax.annotate(f"{value:,.1f}", (value, y), xytext=(6, 0),
                            textcoords="offset points", va="center", color=COLORS[j], fontsize=9)
    axes[0].set_title("Port meter peak (kW)", loc="left", fontsize=12)
    axes[1].set_title("Annual operating value vs E1 (€2025)", loc="left", fontsize=12)
    for ax in axes:
        ax.margins(x=.20)
        ax.set_ylim(-.85, 6.85)
        ax.set_yticks([6, 4, 2, 0], list(LABELS.values()))
        ax.tick_params(axis="y", length=0, pad=8)
        ax.grid(axis="x", color="#dce2e5", linewidth=.7)
        for y in (1, 3, 5):
            ax.axhline(y, color="#e1e5e8", linewidth=.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
    axes[1].axvline(0, color="#69767b", linewidth=.9)
    fig.legend(handles=[plt.Line2D([], [], ls="", marker=m, color=c, label=label)
                        for m,c,label in zip(("o", "D"), COLORS, ("P1   Energy-only dispatch",
                                                                   "P2   Peak-aware dispatch"))],
               loc="upper left", bbox_to_anchor=(.026,.90), ncol=2, frameon=False, fontsize=9)
    count = rows["one", "P1"]["completed"]
    fig.text(.035, .045, f"{count} common truck-days   ·   300 kWh battery   ·   Cross-day energy carry-over"
             "   ·   Frank et al., Table 4 network tariff", fontsize=9, color="#47575d")
    save(fig, folder, "peak_value")


def pilot_comparison(summary, folder):
    pilot = summary["pilot"]
    edges = np.arange(len(pilot["quarters"])+1) / 4
    fig, axes = plt.subplots(4, 1, figsize=(10.5, 7.5), sharex=True, sharey=True)
    fig.subplots_adjust(left=.085, right=.97, top=.82, bottom=.12, hspace=.55)
    fig.suptitle(f"Two trucks at the port on {pilot['date']}", x=.035, y=.97,
                 ha="left", fontsize=16, weight="bold")
    for name, ax in zip(LABELS, axes):
        powers = np.array([row["port_kw"][name] for row in pilot["quarters"]])
        a, b = powers.T
        ax.stairs(a, edges, fill=True, color=COLORS[0], label=f"Truck {pilot['vehicles'][0]}")
        ax.stairs(a+b, edges, baseline=a, fill=True, color=COLORS[1], label=f"Truck {pilot['vehicles'][1]}")
        ax.set_title(LABELS[name], loc="left", fontsize=10.5, pad=4)
        ax.set_yticks([0, 50, 100])
        ax.set_ylim(0, 106)
        ax.set_xlim(0, 24)
        ax.grid(axis="y", color="#dce2e5", linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
    axes[-1].set_xticks(np.arange(0, 25, 2), [f"{h:02}:00" for h in range(0,25,2)])
    axes[-1].set_xlabel("Europe/Berlin local time")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.025,.923),
               frameon=False, ncol=2, fontsize=9)
    fig.text(.035, .865, "Stacked 15-minute mean power (kW). The top edge is the port meter load.",
             fontsize=9, color="#47575d")
    save(fig, folder, "pilot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=STUDY / "cabinet_demand.json")
    parser.add_argument("--output", type=Path, default=STUDY / "figures")
    args = parser.parse_args()
    summary = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.hashsalt": "UM-cabinet-demand",
                         "svg.fonttype": "none", "axes.labelcolor": "#26393f", "text.color": "#26393f"})
    study_comparison(summary, args.output)
    pilot_comparison(summary, args.output)
    environment = dict(matplotlib=matplotlib.__version__, numpy=np.__version__,
                       scope="Separate plotting environment. Input: curated cabinet_demand.json only.")
    (args.output / "plot_environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
