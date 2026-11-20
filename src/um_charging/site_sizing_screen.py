"""Screen priced site-sizing operating points using archived weekly proofs."""

from argparse import ArgumentParser
import ast
from collections import Counter
from contextlib import ExitStack, contextmanager
import math
from pathlib import Path
from statistics import mean
import subprocess
from unittest.mock import patch

from scipy import optimize

from . import site_sizing as sizing
from .__main__ import checked_output, digest, write_json
from .site_sizing_bounds import AnnualBillBounds
from .site_sizing_screen_evidence import BacktestFailure, backtest, load_evidence
from .site_sizing_screen_thresholds import quote_threshold_ranges


COST_MARGIN_EUR = 1e-6
WORKERS = 8
ROOT = Path(__file__).resolve().parents[2]
ACCOUNTING_EDITS = {
    "src/um_charging/site_sizing.py": {"annual_capital_costs", "annual_tables"},
    "src/um_charging/cabinet_tariff.py": {"annual_repeats", "annual_factors", "network_rates", "settle"},
}
SOLVER_SOURCES = (
    "src/um_charging/site_sizing.py",
    "src/um_charging/fleet_changeover.py",
    "src/um_charging/energy_boundary.py",
    "src/um_charging/cabinet_model.py",
    "src/um_charging/cabinet_audit.py",
    "src/um_charging/fleet_service.py",
    "src/um_charging/fleet_market.py",
    "src/um_charging/cabinet_tariff.py",
)


def _model_ast(content, accounting):
    return [ast.dump(node) for node in ast.parse(content).body
            if not isinstance(node, ast.FunctionDef) or node.name not in accounting]


def verify_solver_source(pilot_source):
    """Verify the archived pilot and this workload have the same solve path."""
    if pilot_source["dirty"]:
        raise ValueError("The pilot must identify a clean source commit")
    commit = pilot_source["commit"]
    git = ("git", "-C", str(ROOT))
    for file in SOLVER_SOURCES:
        old = subprocess.check_output((*git, "show", f"{commit}:{file}"))
        new = (ROOT / file).read_bytes()
        accounting = ACCOUNTING_EDITS.get(file, set())
        if _model_ast(old, accounting) != _model_ast(new, accounting):
            raise ValueError(f"The archived pilot's solver source changed in {file}")
    diff = subprocess.check_output(
        (*git, "-c", "core.autocrlf=false", "diff", "--no-ext-diff", "--unified=0", commit, "--", *SOLVER_SOURCES),
        encoding="utf-8",
    )
    return {"pilot_commit": commit, "verified_files": list(SOLVER_SOURCES),
            "excluded_accounting_functions": {path: sorted(names) for path, names in ACCOUNTING_EDITS.items()},
            "diff": diff}


def _solver_forbidden(*args, **kwargs):
    raise RuntimeError("Site-sizing screening must not call the solver")


@contextmanager
def without_solver():
    """Keep archived replay and tariff arithmetic independent of optimization."""
    with ExitStack() as guards:
        for module in (sizing, sizing.fc, sizing.eb, optimize):
            for name in ("solve", "milp", "linprog"):
                if hasattr(module, name):
                    guards.enter_context(patch.object(module, name, _solver_forbidden))
        guards.enter_context(patch.object(sizing.Evidence, "call", _solver_forbidden))
        yield


def _weekly_jobs(missing):
    return [{"week": week, "design": build.label, "caps_kw": caps}
            for week, build, caps in missing]


def estimate_wall_time(weekly_jobs, pilot):
    """Expand the archived wall time of each sampled stratum to this workload."""
    seconds = {(row["week"], row["two_port_plugs"], row["both_sites_active"]):
               mean(row["observed_seconds"]) for row in pilot["trial_strata"]}
    population = Counter((week, build.port_plugs == 2, all(caps)) for week, build, caps in weekly_jobs)
    strata = [{"week": week, "two_port_plugs": dual, "both_sites_active": both,
               "weekly_groups": count, "pilot_mean_seconds": seconds[week, dual, both]}
              for (week, dual, both), count in sorted(population.items())]
    processing = math.fsum(row["weekly_groups"] * row["pilot_mean_seconds"] for row in strata)
    tail = pilot["estimate"]["longest_sample_seconds"] if weekly_jobs else 0.
    overhead = pilot["estimate"]["observed_overhead_seconds"] if weekly_jobs else 0.
    return {"workers": WORKERS, "unique_weekly_groups": len(weekly_jobs), "strata": strata,
            "estimated_work_seconds": processing, "estimated_tail_seconds": tail,
            "estimated_overhead_seconds": overhead,
            "estimated_wall_seconds": processing / WORKERS + tail + overhead}


def screen(evidence, bounds):
    incumbent = {(row["scenario"], row["connection_basis"]): row["annual_total_eur"]
                 for row in evidence.publication["winners"]}
    if set(incumbent) != {(scenario, basis) for scenario in evidence.scenarios for basis in ("new", "existing")}:
        raise ValueError("All twelve published minimum bills are required")
    points, excluded = [], []
    relaxed_infeasible = 0
    jobs = set()
    lower_bound_only = Counter()
    for earlier in evidence.prescan_points:
        design = evidence.cases[earlier["design"]]
        caps = tuple(earlier["caps_kw"])
        plan = evidence.point_plan(design, caps)
        lower = bounds.annual_lower_bounds(design, caps, evidence.records_by_week)
        totals = {key: lower["total_eur"][key[0]][key[1]] for key in incumbent}
        above_incumbent = all(totals[key] > incumbent[key] + COST_MARGIN_EUR for key in incumbent)
        lower_bound_only["excluded" if above_incumbent else "retained"] += 1
        comparisons = [
            {"scenario": scenario, "connection_basis": basis, "published_minimum_eur": incumbent[scenario, basis],
             "lower_eur": total if math.isfinite(total) else None,
             "margin_eur": total - incumbent[scenario, basis] if math.isfinite(total) else None,
             "no_relaxed_load_split": total == math.inf}
            for (scenario, basis), total in totals.items()
        ]
        if any(math.isnan(total) or total == -math.inf for total in totals.values()):
            raise ValueError(f"Invalid lower bound for {design.label} at {caps}")
        status = plan.status
        if status == "needs_solves" and above_incumbent:
            status = "excluded_by_annual_lower_bound"
            if all(math.isfinite(total) for total in totals.values()):
                excluded.append((design, caps, totals))
            elif all(total == math.inf for total in totals.values()):
                relaxed_infeasible += 1
            else:
                raise ValueError(f"Inconsistent network relaxation for {design.label} at {caps}")
        if status == "needs_solves":
            jobs.update(plan.missing)
        points.append({
            "design": design.label, "caps_kw": caps, "status": status,
            "weekly_infeasibility_proof": plan.proof.proof if plan.proof else None,
            "wholesale_lower_eur_2025": lower["purchase_eur"],
            "wholesale_weekly_proofs": [
                {"week": week, "design": proof.design.label, "caps_kw": proof.caps,
                 "lower_eur_2021": proof.lower_eur, "proof": proof.proof}
                for week, proof in lower["weekly"].items()
            ],
            "annual_comparison": comparisons,
            "weekly_groups_to_solve": _weekly_jobs(plan.missing) if status == "needs_solves" else [],
        })

    if len(points) != len({(row["design"], row["caps_kw"]) for row in points}):
        raise ValueError("Repeated operating point in the prior inventory")
    counts = Counter(row["status"] for row in points)
    thresholds = quote_threshold_ranges(evidence.publication, excluded)
    return {
        "annual_currency_basis": "EUR 2025 per year",
        "cost_exclusion_margin_eur": COST_MARGIN_EUR,
        "prior_pending_priced_points": len(points),
        "counts": dict(counts),
        "lower_bound_only_counts_before_pilot_infeasibility": dict(lower_bound_only),
        "no_relaxed_load_split_count": relaxed_infeasible,
        "points": points,
        "unique_weekly_groups_to_solve": _weekly_jobs(sorted(jobs)),
        "wall_time": estimate_wall_time(jobs, evidence.pilot_summary),
        "quote_thresholds_for_excluded_points": thresholds,
    }


def run(coarse_archive, pilot_archive, output, *, publication_path=None):
    """Read archives, backtest, and screen. The optimizer is disabled throughout."""
    with without_solver():
        evidence = load_evidence(coarse_archive, pilot_archive, publication_path=publication_path)
        provenance = verify_solver_source(evidence.pilot_summary["source"])
        bounds = AnnualBillBounds(tuple(evidence.periods.values()), evidence.reference,
                                  evidence.network, evidence.materials)
        try:
            report = backtest(evidence, bounds)
        except BacktestFailure as failure:
            write_json(output / "backtest.json", failure.report)
            raise
        write_json(output / "backtest.json", report)
        result = screen(evidence, bounds)
        result.update(source=sizing.source_state(), inputs_sha256=evidence.publication["inputs_sha256"],
                      archive_sha256=evidence.archive_sha256, pilot_solver_source=provenance,
                      solver_calls=0, backtest_sha256=digest(output / "backtest.json"))
        write_json(output / "screening.json", result)
    return report, result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--coarse-archive", type=Path, required=True)
    parser.add_argument("--pilot-archive", type=Path, required=True)
    parser.add_argument("--published-baseline", type=Path,
                        help="Archived publication used to register the original coarse and fine points")
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory inside the local offline records repository")
    args = parser.parse_args()
    output = checked_output(args.output, ROOT)
    output.mkdir()
    _, result = run(args.coarse_archive, args.pilot_archive, output,
                    publication_path=args.published_baseline)
    print("Priced points", result["counts"])
    print("Remaining weekly groups", result["wall_time"]["unique_weekly_groups"])
    print("Estimated wall hours", result["wall_time"]["estimated_wall_seconds"] / 3600)


if __name__ == "__main__":
    main()
