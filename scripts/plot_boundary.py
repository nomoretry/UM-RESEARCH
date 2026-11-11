"""Render actual boundary results and unchanged task/plug-window diagrams."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.result_dir / "metrics.json").read_text(encoding="utf-8"))
    task = json.loads((args.result_dir / "task_windows.json").read_text(encoding="utf-8"))
    target = args.result_dir / "figures"
    target.mkdir(exist_ok=True)
    def save(fig, name):
        for ext in ("png", "svg"):
            fig.savefig(target / f"{name}.{ext}", dpi=180)
        plt.close(fig)
    colors = {"drive": "#E69F00", "park": "#D9D9D9", "warehouse": "#009E73", "port": "#0072B2"}
    fig, ax = plt.subplots(figsize=(11, 4.7), layout="constrained")
    for y, case in enumerate(task["cases"]):
        for slot in case["slots"]:
            key = "drive" if slot["activity"] == "drive" else (
                "warehouse" if slot["plug_allowed"] and slot["from"] == "WAREHOUSE" else
                "port" if slot["plug_allowed"] else "park")
            ax.barh(y, slot["end_minute"] - slot["start_minute"], left=slot["start_minute"], height=.65,
                    color=colors[key], edgecolor="white", linewidth=.5)
    ax.set(yticks=range(len(task["cases"])), yticklabels=[f"W = {c['warehouse_window_minutes']} min" for c in task["cases"]],
           xticks=range(0, 241, 30), xlim=(0, 240), xlabel="Minutes from cycle start",
           title="Same task chain for all three trucks; only warehouse plug eligibility changes\nPort to warehouse (20 kWh) | dwell | warehouse to port (20 kWh) | dwell")
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    handles=[Patch(color=colors[k], label=v) for k,v in [("drive","Driving; no charging"),("park","Parked; no plug eligibility"),("warehouse","Warehouse plug eligible"),("port","Port plug eligible")]]
    fig.legend(handles=handles,loc="outside lower center",ncol=2,frameon=False)
    save(fig,"task_and_windows")

    powers, windows = [50,75,100,125,150], [0,15,30,45,60]
    fig, axes = plt.subplots(1,2,figsize=(11,5.7),layout="constrained",sharey=True)
    cmap=plt.colormaps["YlGnBu"].copy(); cmap.set_bad("#DDDDDD")
    for ax,policy,title in zip(axes,["slot_boundary_switching","fixed_dwell_connection"],
                               ["Switching at slot boundaries","Connection held for entire plug window"]):
        selected=[[next(r for r in rows if r["connector_policy"]==policy and r["charging_scope"]=="two_sites"
                         and r["port_available_power_kw"]==h and r["warehouse_window_minutes"]==w)
                   for w in windows] for h in powers]
        matrix=np.array([[r["investment_cost"] if r["status"]=="optimal" else np.nan for r in line] for line in selected])
        im=ax.imshow(matrix,cmap=cmap,vmin=0,vmax=110,aspect="auto")
        for i,line in enumerate(selected):
            for j,r in enumerate(line):
                if r["status"] not in ("optimal","infeasible"): raise ValueError("Unresolved result cannot be plotted as infeasible")
                label="X" if r["status"]=="infeasible" else f"{r['investment_cost']:.0f}" + (" *" if len(r["enumeration_best_hardware"])>1 else "")
                ax.text(j,i,label,ha="center",va="center",color="white" if r["investment_cost"] is not None and r["investment_cost"]>=65 else "black",fontsize=11)
        ax.set(xticks=range(5),xticklabels=windows,yticks=range(5),yticklabels=powers,
               xlabel="Warehouse plug window (minutes)",title=title)
    axes[0].set_ylabel("Port existing available power (kW)\nPaid upgrades remain selectable")
    fig.colorbar(im,ax=axes,label="Added investment (synthetic currency / 4-hour cycle)",shrink=.8)
    fig.suptitle("Two-site optimal investment; operating cost = 133.333 for each feasible case\nX: infeasible   *: multiple optimal facility configurations",fontsize=12)
    save(fig,"investment_boundary")
    (target/"plot_environment.json").write_text(json.dumps({"matplotlib":matplotlib.__version__,"numpy":np.__version__,
        "scope":"Separate plotting environment; input from curated actual results and audited task windows"},indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
