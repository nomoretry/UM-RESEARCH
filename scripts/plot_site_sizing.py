"""Plot the matched-service boundary and annual costs from the curated study JSON."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Patch, Rectangle
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies/fleet-service"
UNSAMPLED = "#f1f3f4"
INELIGIBLE = "#e2e7e9"
NEEDS_PRICE = "#f2e5c4"
BORDER = "#122a30"


def paint(ax, x, y, color, text="", *, text_color=BORDER, outline=False):
    ax.add_patch(Rectangle((x - .5, y - .5), 1, 1, facecolor=color,
                           edgecolor="white", linewidth=1.1))
    if text:
        ax.text(x, y, text, ha="center", va="center", fontsize=8, color=text_color)
    if outline:
        ax.add_patch(Rectangle((x - .44, y - .44), .88, .88, fill=False,
                               edgecolor=BORDER, linewidth=1.65))


def readable_on(rgba):
    r, g, b = rgba[:3]
    return "white" if .2126 * r + .7152 * g + .0722 * b < .52 else BORDER


def make_figure(data):
    rows = data["service"]
    reference = len(data["reference_service"])
    keys = sorted({(r["port_plugs"], r["port_kw"]) for r in rows})
    warehouse = sorted({r["warehouse_kw"] for r in rows})
    cells = {(r["port_plugs"], r["port_kw"], r["warehouse_kw"]): r for r in rows}
    bills = {r["design"]: r for r in data["cost_rows"] if r["scenario"] == "official"}
    official = {r["connection_basis"]: r["design"] for r in data["winners"] if r["scenario"] == "official"}
    totals = [t / 1000 for row in bills.values() for t in row["total_eur"].values() if t is not None]
    cost_scale = Normalize(vmin=np.floor(min(totals)), vmax=np.ceil(max(totals)) + .001)
    cost_palette = matplotlib.colormaps["viridis_r"]
    service_palette = matplotlib.colormaps["Blues"]
    fig, axes = plt.subplots(1, 3, figsize=(17.6, 6.5))
    fig.subplots_adjust(left=.062, right=.983, top=.79, bottom=.285, wspace=.16)
    titles = ("Maximum service", "New connections", "Existing connections")
    modes = (None, "new", "existing")
    single_end = sum(plugs < 2 for plugs, _ in keys)
    for ax, title, mode in zip(axes, titles, modes, strict=True):
        ax.set_title(title, loc="left", fontsize=13, weight="bold", pad=10)
        ax.set_xlim(-.5, len(keys) - .5)
        ax.set_ylim(-.5, len(warehouse) - .5)
        labels = [str(kw) if plugs < 2 else f"{kw}" + chr(10) + "2×50" for plugs, kw in keys]
        ax.set_xticks(range(len(keys)), labels)
        ax.set_yticks(range(len(warehouse)), warehouse)
        ax.tick_params(length=0, labelsize=8, labelleft=mode is None, pad=5)
        ax.set_xlabel("Port connection (kW)", labelpad=9)
        ax.spines[:].set_visible(False)
        if mode is None:
            ax.set_ylabel("Warehouse connection (kW)", labelpad=7)
        for x, (plugs, port) in enumerate(keys):
            for y, w in enumerate(warehouse):
                row = cells.get((plugs, port, w))
                if row is None:
                    paint(ax, x, y, UNSAMPLED)
                elif row["completed"] is None:
                    paint(ax, x, y, INELIGIBLE, "?")
                elif mode is None:
                    color = service_palette(.17 + .67 * row["completed"] / reference)
                    paint(ax, x, y, color, str(row["completed"]),
                          text_color=readable_on(color), outline=row["same_service"])
                elif not row["same_service"]:
                    paint(ax, x, y, INELIGIBLE)
                elif row["design"] not in bills:
                    paint(ax, x, y, INELIGIBLE, "?")
                else:
                    bill = bills[row["design"]]
                    total = bill["total_eur"][mode]
                    if total is None:
                        paint(ax, x, y, NEEDS_PRICE, "quote")
                    else:
                        color = cost_palette(cost_scale(total / 1000))
                        mark = "*" if bill["dispatch_status"] == "bounded" else ""
                        paint(ax, x, y, color, f"{total / 1000:.2f}{mark}", text_color=readable_on(color),
                              outline=row["design"] == official[mode])
        if single_end < len(keys):
            ax.axvline(single_end - .5, color="#849497", linewidth=1.1)
    fig.suptitle("Where to install charging power for the same truck service",
                 x=.062, y=.963, ha="left", fontsize=19, weight="bold", color=BORDER)
    fig.text(.062, .89, f"Matched set {reference}/{data['sample_truck_days']} truck-days"
             "   ·   300 kWh batteries, zero-changeover cost scan"
             "   ·   Netze BW official 2024 medium-voltage tariff",
             fontsize=10, color="#40545a")
    handles = [Patch(facecolor=UNSAMPLED, label="Outside evaluated grid"),
               Patch(facecolor=INELIGIBLE, label="Service gap or unresolved"),
               Patch(facecolor=NEEDS_PRICE, label="Equipment quote required"),
               Patch(facecolor="white", edgecolor=BORDER,
                     label="Same 54 days / lowest evaluated priced cost")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(.058, .088),
               ncol=4, frameon=False, fontsize=9)
    color_ax = fig.add_axes((.536, .174, .411, .018))
    bar = fig.colorbar(matplotlib.cm.ScalarMappable(norm=cost_scale, cmap=cost_palette),
                       cax=color_ax, orientation="horizontal")
    bar.ax.tick_params(labelsize=8, length=3)
    bar.set_label("Annual cost (thousand euros, 2025 purchasing power)", fontsize=9)
    fig.text(.062, .047, "One port charger unless labelled 2 × 50. Cost cells use replayed schedules. "
             "An asterisk denotes a timed-out dispatch with a retained wholesale-cost interval.",
             fontsize=9, color="#40545a")
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=STUDY / "site_sizing.json")
    parser.add_argument("--output", type=Path, default=STUDY / "figures/site_sizing.png")
    args = parser.parse_args()
    versions = json.loads((STUDY / "figures/plot_environment.json").read_text(encoding="utf-8"))
    if (matplotlib.__version__, np.__version__) != (versions["matplotlib"], versions["numpy"]):
        raise ValueError("Use the pinned plotting environment for the fleet study")
    fig = make_figure(json.loads(args.input.read_text(encoding="utf-8")))
    fig.savefig(args.output, dpi=190, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
