"""Build the paper's CSV tables and booktabs fragments from published JSON."""
import argparse
import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CASE = HERE.parent
METHODS = {"rule1": "Rule I", "rule2": "Rule II", "rule3": "Rule III",
           "rule4": "Rule IV", "weekly_union": "Weekly union"}
OUTCOMES = {"守住": "Held", "未守住": "Failed", "未定": "Undetermined", "不可评": "Not evaluable"}
CONSTRAINTS = {"single_truck_leg_boundary": "Post-trip reserve",
               "single_truck_terminal_energy": "Terminal energy"}


def load(name):
    return json.loads((CASE / name).read_bytes())


def feasible(build, period):
    return all(state == "feasible" for state in build[period].values())


def span(values):
    return " to ".join(f"{n:,.2f}" for n in values)


def pair(values):
    return " / ".join(map(str, values))


def tables():
    public = load("external_test.json")
    cohorts = load("external_designs.json")["cohorts"]
    segments = load("external_segments.json")["segments"]
    policies = load("second_holdout.json")["operating_policies"]
    overview, failures, rules, operations = [], [], [], []
    for label, cohort in cohorts.items():
        designs = cohort["designs"]
        counts = [sum(feasible(d, phase) for d in designs.values()) for phase in ("selection", "evaluation")]
        role = "Post hoc reference" if cohort["reference_role"] == "post_hoc" else "Primary"
        outcome = (public["original_posthoc_reference"]["verdict"] if role == "Post hoc reference"
                   else public["cohorts"][label]["primary"])
        overview.append([label, role, pair(cohort["complete_days"]), pair(cohort["registered_days"]),
                         pair(counts), OUTCOMES[outcome]])
        for segment in segments:
            if segment["cohort"] == label:
                bill = designs[segment["selected"]]["selection_bill"]["new"]
                failures.append([label, segment["selected"], span(bill), OUTCOMES[outcome],
                                 " to ".join(segment["dates"]), CONSTRAINTS[segment["constraint"]],
                                 f"{segment['deficit_kwh']:.3f}"])
        for row in cohort["comparisons"]:
            if row["method"] in METHODS:
                rules.append([label, row["basis"].title(), METHODS[row["method"]], row["design"],
                              span(row["premium"]), OUTCOMES[row["test"]]])
    for label, cohort in public["cohorts"].items():
        if cohort["role"] == "secondary":
            overview.append([label, "Secondary", pair(cohort["complete_days"]), "", "", OUTCOMES[cohort["primary"]]])
    for basis in ("new", "existing"):
        for policy, row in policies[f"official_{basis}"].items():
            surplus = row.get("terminal_surplus_eur_2025_per_year")
            operations.append([basis.title(), policy.replace("_", " ").title(), row["design"], pair(row["caps_kw"]),
                               span(row["annual_cost_eur_2025"]), "" if surplus is None else f"{surplus:,.2f}"])
    return {
        "table1_cohorts": (["Ranks", "Role", "Complete days", "Registered days", "Feasible builds", "Outcome"], overview),
        "table2_failures": (["Ranks", "Selected build", "Bill (EUR/yr)", "Outcome", "Failed segment",
                             "Constraint", "Gap (kWh)"], failures),
        "table3_rules": (["Ranks", "Connection", "Rule", "Build", "Premium (EUR/yr)", "Outcome"], rules),
        "table5_operations": (["Connection", "Policy", "Build", "Caps (kW)", "Bill (EUR/yr)",
                               "Of which surplus (EUR/yr)"], operations),
    }


NOTES = {
    "table1_cohorts": "Pairs give selection / evaluation. Feasible builds are counted among the 35 rated designs. Blank cells follow the complete-duty gate.",
    "table2_failures": "Official new connections, rated settings, selection bills in 2025 EUR. The two-day row identifies one failed segment.",
    "table3_rules": "Selection premium against the original minimum for the same cohort and connection basis, in 2025 EUR. Outcome is subsequent service.",
    "table5_operations": "Ranks 1--5, selection period, official network charges, policy-specific minima. Surplus is the disclosed portion of the metered bill.",
}


def tex_cell(value):
    return str(value).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_") or "---"


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in tables().items():
        with (output / (name + ".csv")).open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerows([header, *rows])
        lines = ["% Requires booktabs and graphicx.", r"\begin{minipage}{\linewidth}",
                 r"\small\setlength{\tabcolsep}{3pt}", r"\sbox0{%",
                 r"\begin{tabular}{" + "l" * len(header) + "}", r"\toprule"]
        for i, row in enumerate([header, *rows]):
            lines.append(" & ".join(map(tex_cell, row)) + r" \\")
            if i == 0:
                lines.append(r"\midrule")
        lines.extend([r"\bottomrule", r"\end{tabular}}%",
                      r"\ifdim\wd0>\linewidth\resizebox{\linewidth}{!}{\usebox0}\else\usebox0\fi",
                      r"\par\smallskip\footnotesize " + NOTES[name], r"\end{minipage}"])
        (output / (name + ".tex")).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    generate(parser.parse_args().output)
