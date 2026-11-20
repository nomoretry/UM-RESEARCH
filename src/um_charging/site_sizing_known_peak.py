"""Verify the priced refinement and equipment thresholds using archived schedules."""

from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
from tempfile import mkdtemp
from time import monotonic

from . import site_sizing as ss
from .__main__ import digest, write_json
from .site_sizing_known_peak_audit import backtest, classify_remaining, load_archive
from .site_sizing_known_peak_quotes import recompute_quote_thresholds
from .site_sizing_screen import ROOT, verify_solver_source, without_solver
from .site_sizing_screen_evidence import BacktestFailure


def run(runs, output):
    """Write the three audit products in order. A failed gate stops publication."""
    started = monotonic()
    coarse = runs / "20261120_site_sizing"
    pilot = runs / "20261120_site_sizing_fine"
    screen = runs / "20261120_site_sizing_screen"
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"Use an empty output directory: {output}")

    def save(name, report):
        write_json(output / name, report)
        print(f"{monotonic() - started:.2f} s  {name}", flush=True)

    with without_solver():
        archive = load_archive(coarse, pilot, screen)
        verify_solver_source(archive.summary["source"])
        print(f"{monotonic() - started:.2f} s  archive verified", flush=True)
        try:
            checks = backtest(archive)
        except BacktestFailure as failure:
            save("backtest.json", failure.report)
            raise
        save("backtest.json", checks)
        ranking = classify_remaining(archive)
        save("classification.json", ranking)
        if ranking["status"] != "passed":
            raise ValueError("A priced point remains unresolved")
        quotes = recompute_quote_thresholds(archive)
        save("thresholds.json", quotes)

        # Per-build cells in the figure show the lowest replayed invoice for
        # that build. Screening proves the global ranking, not every cell price.
        options = defaultdict(list)
        for point in archive.ranked_settlements:
            options[point.design].append(point.dispatch)
        bills, _ = ss.annual_tables(options, archive.evidence.materials, archive.evidence.scenarios)
        save("settled_cost_rows.json", [dict(design=label, scenario=case, **row)
                                        for (label, case), row in sorted(bills.items())])
    save("manifest.json", dict(
        status="passed", solver_calls=0, source=ss.source_state(), inputs_sha256=archive.summary["inputs_sha256"],
        screen_archive_sha256={name: digest(screen / name) for name in
                              ("published_baseline.json", "formal/summary.json", "phase2_audit.json",
                               "screening.json", "threshold_points.json", "witness_ranges_on_published_minima.json",
                               "relaxed_capacity_infeasible.json")},
        output_sha256={name: digest(output / name) for name in
                       ("backtest.json", "classification.json", "thresholds.json", "settled_cost_rows.json")},
    ))
    print(f"{checks['checks']} holdout bills; {len(ranking['points'])} points excluded; "
          f"{len(quotes['quote_thresholds'])} tariff/connection cases. Output: {output}", flush=True)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, help="Offline runs directory (defaults to the local records config)")
    parser.add_argument("--output", type=Path, help="Empty result directory (defaults to a fresh temporary directory)")
    args = parser.parse_args()
    runs = args.runs
    if runs is None:
        local = ss.eb.read_json(ROOT / ".um-records.local.json")
        runs = Path(local["records_root"]) / "conversations/0001_records/runs"
    run(runs, args.output or Path(mkdtemp(prefix="um-site-sizing-known-peak-")))


if __name__ == "__main__":
    main()
