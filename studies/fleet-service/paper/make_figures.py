"""Rebuild all figures and tables with: python make_figures.py --all"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from make_tables import HERE, feasible, generate as generate_tables, load


STYLE = {"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 11,
         "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
         "hatch.linewidth": 0.6}
BLUE, GRAY = "#164c69", "#d4d8da"


def design_timeline(report):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    model = report["model"]
    ax.text(0, .98, "Study design and evidence timeline", fontsize=15, weight="bold", va="top")
    periods = [("Selection", "selection_dates"), ("Evaluation", "evaluation_dates")]
    x = 0
    for (name, field), weeks, color in zip(periods, model["calendar_weeks"], [BLUE, "#4e5255"]):
        width = weeks / sum(model["calendar_weeks"])
        ax.add_patch(Rectangle((x, .71), width - .006, .16, facecolor=color))
        date_range = " to ".join(model[field])
        ax.text(x + .018, .815, f"{name} · {weeks} weeks", color="white", weight="bold", fontsize=11)
        ax.text(x + .018, .748, date_range, color="white")
        x += width
    rows = [("1-5", "Post hoc reference", "Preregistered second holdout")]
    for label, cohort in report["cohorts"].items():
        role = "Primary external" if cohort["role"] == "primary" else "Secondary external"
        detail = ("Sealed service test" if cohort["role"] == "primary" else
                  f"{cohort['complete_days'][1]} complete evaluation days (gate requires {model['complete_day_thresholds'][1]})")
        rows.append((label, role, detail))
    for i, (label, role, detail) in enumerate(rows):
        y = .62 - .08 * i
        ax.text(.015, y, "Ranks " + label, weight="bold")
        ax.text(.23, y, role)
        ax.text(.51, y, detail)
    ax.text(0, .245, "Registration and external opening · UTC", weight="bold", fontsize=11)
    timeline = report["report_details"]["timeline"]
    events = [("Manifest", "manifest_created_utc"), ("Bitcoin block", "block_utc"), ("Opening authorised", "authorization")]
    for i, (name, key) in enumerate(events):
        x = i * .344
        dt = datetime.fromisoformat(timeline[key]).astimezone(timezone.utc)
        ax.text(x, .155, name, weight="bold", color=BLUE)
        ax.text(x, .09, dt.strftime("%Y-%m-%d %H:%M:%S"))
        if i < 2:
            ax.annotate("", (x + .325, .166), (x + .245, .166), arrowprops={"arrowstyle": "->", "color": "#555"})
    fig.subplots_adjust(left=.055, right=.97, top=.97, bottom=.02)
    return fig


def cost_outcomes(cohorts, report):
    fig, axes = plt.subplots(3, 1, figsize=(7.8, 6), sharex=True)
    fig.suptitle("Selection cost and subsequent service", x=.14, ha="left", fontsize=15, weight="bold")
    for ax, (label, cohort) in zip(axes, cohorts.items()):
        best = report["report_details"]["posthoc"][label]["design"]
        selected = cohort["selected"]
        builds = sorted((sum(d["selection_bill"]["new"]) / 2 / 1000, name, feasible(d, "evaluation"))
                        for name, d in cohort["designs"].items() if d["selection_bill"])
        # Stagger nearby costs within a category so coincident builds remain visible.
        used = {False: [], True: []}
        for cost, name, held in builds:
            lanes = used[held]
            i = next((i for i, last in enumerate(lanes) if cost - last > .65), len(lanes))
            if i == len(lanes):
                lanes.append(cost)
            else:
                lanes[i] = cost
            offset = (0, .16, -.16, .29, -.29)[i % 5]
            marker, color, size = ("s", BLUE, 6.5) if name == selected else (
                ("*", "black", 11) if name == best else ("o", "white", 5))
            artist, = ax.plot(cost, int(held) + offset, marker, color="black", markerfacecolor=color,
                              markersize=size, markeredgewidth=.8)
            artist.set_gid(name)
        role = "post hoc reference" if cohort["reference_role"] == "post_hoc" else "primary"
        ax.set_title(f"Ranks {label} ({role})     Selected {selected}     First held {best}", loc="left", fontsize=9)
        ax.set(yticks=[0, 1], yticklabels=["Failed", "Held"], ylim=(-.45, 1.45))
        ax.grid(axis="x", linewidth=.45, color="#ccd0d1")
        ax.set_axisbelow(True)
    axes[-1].set_xlabel("Selection bill at rated operation (thousand 2025 EUR/year, interval midpoint)")
    handles = [Line2D([], [], marker=m, lw=0, mec="black", mfc=c, ms=s, label=l)
               for m, c, s, l in [("o","white",5,"Other build"),("s",BLUE,6,"Selected"),
                                   ("*","black",9,"Cheapest build serving both periods")]]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(.5, 0))
    fig.subplots_adjust(left=.14, right=.97, bottom=.17, top=.86, hspace=.66)
    return fig


def feasible_counts(cohorts, report):
    fig, ax = plt.subplots(figsize=(6.8, 3.7))
    for i, phase in enumerate(("selection", "evaluation")):
        counts = [sum(feasible(d, phase) for d in c["designs"].values()) for c in cohorts.values()]
        bars = ax.bar([j + (i - .5) * .32 for j in range(len(cohorts))], counts, .32,
                      color=[BLUE, "white"][i], edgecolor="black", hatch=["", "///"][i],
                      label=phase.title(), linewidth=.8)
        ax.bar_label(bars, padding=3)
    labels = [label + ("\n(post hoc)" if c["reference_role"] == "post_hoc" else "\n(primary)") for label,c in cohorts.items()]
    ax.set(xticks=range(len(labels)), xticklabels=labels, ylim=(0, report["model"]["hardware_count"]),
           ylabel="Feasible rated designs", xlabel="Vehicle rank interval")
    ax.set_title("Designs completing all registered duties", loc="left", weight="bold", fontsize=14)
    ax.legend(frameon=False, ncol=2, loc="upper right")
    fig.text(.12, .02, "Registration is defined by the dual-site baseline in each period.", fontsize=8)
    fig.subplots_adjust(left=.12, right=.97, top=.85, bottom=.27)
    return fig


def envelope(segment, family, payload):
    """Debit trips at arrival. Stop the selected trace at the first infeasible event."""
    xs, ys = [0.0], [payload["initial_kwh"]]
    port, warehouse = segment[family].split("-")[1:]
    ratings = {"PORT": int(port), "WAREHOUSE": int(warehouse[1:])}
    for event in segment["events"]:
        value = event[family + "_upper_kwh"]
        if value is None:
            break
        a, b = event["start_h"], event["end_h"]
        last = ys[-1]
        xs.append(a)
        ys.append(last)
        if event["kind"] == "trip":
            xs.append(b)
            ys.append(last)
        elif value == payload["capacity_kwh"]:
            slope = ratings[event["site"]] * payload["efficiency"]
            if slope:
                xs.append(min(b, a + (value - last) / slope))
                ys.append(value)
        xs.append(b)
        ys.append(value)
    return xs, ys


def energy_segments(payload):
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 6.8), sharey=True)
    for ax, seg in zip(axes.flat, payload["segments"]):
        for y in (payload["reserve_kwh"], payload["initial_kwh"]):
            ax.axhline(y, color="#676767", ls=":", lw=.9)
        for event in seg["events"]:
            if event["kind"] == "window":
                port = event["site"] == "PORT"
                ax.axvspan(event["start_h"], event["end_h"], ymin=.025 if port else .083,
                           ymax=.072 if port else .13, facecolor=GRAY if port else "white",
                           edgecolor="#555", hatch=None if port else "////", lw=.65)
        for family, color, style, width in [("baseline", "#575757", "--", 2.4), ("selected", BLUE, "-", 1.35)]:
            x, y = envelope(seg, family, payload)
            line, = ax.plot(x, y, color=color, ls=style, lw=width)
            line.set_gid(family)
            if family == "selected":
                ax.plot(x[-1], y[-1], "x", color=BLUE, ms=6)
        dates = " to ".join(seg["dates"])
        ax.set_title(f"{seg['label']}  ·  Ranks {seg['cohort']}  ·  {seg['selected']}\n"
                     f"{dates}  ·  Gap {seg['deficit_kwh']:.2f} kWh", loc="left", fontsize=9)
        ax.set_ylim(-30, payload["capacity_kwh"] * 1.06)
        ax.set_xlim(left=0)
        ax.set_yticks([30, 100, 150, 200, 300])
    for ax in axes[-1]:
        ax.set_xlabel("Hours since first midnight")
    for ax in axes[:, 0]:
        ax.set_ylabel("Reachable upper bound (kWh)")
    handles = [Line2D([],[],color=BLUE,label="Selected"), Line2D([],[],color="#575757",ls="--",label="Baseline"),
               Patch(facecolor=GRAY,edgecolor="#555",label="Port window"),
               Patch(facecolor="white",edgecolor="#555",hatch="////",label="Warehouse window")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(.5, .017))
    fig.suptitle("Reachable energy on the four failed segments", x=.09, ha="left", weight="bold", fontsize=15)
    fig.subplots_adjust(top=.85, bottom=.16, left=.09, right=.98, hspace=.46, wspace=.15)
    return fig


def segment_ratings(cohorts):
    fig, axes = plt.subplots(2, len(cohorts), figsize=(8, 5.3), sharex=True, sharey=True)
    levels = sorted({level for c in cohorts.values() for rows in c["required_ratings_kw"].values()
                     for r in rows for level in r.values() if level is not None})
    for j, (label, cohort) in enumerate(cohorts.items()):
        for i, phase in enumerate(("selection", "evaluation")):
            ax = axes[i,j]
            rows = cohort["required_ratings_kw"][phase]
            counts = Counter((r["PORT"], r["WAREHOUSE"]) for r in rows)
            assert all(None not in pair for pair in counts)
            for (p, w), n in counts.items():
                x, y = levels.index(p), levels.index(w)
                ax.add_patch(Rectangle((x - .47, y - .47), .94, .94, facecolor="#e3e7e8", edgecolor="none"))
                ax.text(x, y, str(n), ha="center", va="center", weight="bold")
            ax.set(xticks=range(len(levels)), xticklabels=levels, yticks=range(len(levels)), yticklabels=levels,
                   xlim=(-.5,len(levels)-.5), ylim=(-.5,len(levels)-.5), aspect="equal")
            ax.set_title(f"Ranks {label} · {phase.title()}\n{len(rows)} segments", fontsize=9)
            if i == 1:
                ax.set_xlabel("Port (kW)")
            if j == 0:
                ax.set_ylabel("Warehouse (kW)")
    fig.suptitle("Minimum station ratings for individual registered segments", x=.085, ha="left",
                 weight="bold", fontsize=14)
    fig.text(.085, .015, "Cell entries count segments. Blank cells have zero segments. The other site is fixed at its grid maximum.", fontsize=8)
    fig.subplots_adjust(top=.81,bottom=.15,left=.08,right=.99,wspace=.17,hspace=.46)
    return fig


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    report, cohorts = load("external_test.json"), load("external_designs.json")["cohorts"]
    segments = load("external_segments.json")
    with plt.rc_context(STYLE):
        figures = [("figure1_timeline", design_timeline(report)), ("figure2_cost_service", cost_outcomes(cohorts, report)),
                   ("figure3_feasible", feasible_counts(cohorts, report)), ("figure4_energy", energy_segments(segments)),
                   ("figure5_ratings", segment_ratings(cohorts))]
        for name, fig in figures:
            fig.savefig(output / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None})
            fig.savefig(output / (name + ".png"), dpi=300)
            plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="also rebuild the tables")
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    generate(args.output)
    if args.all:
        generate_tables(args.output)
