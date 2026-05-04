"""
periods.py — Multi-period bibliometric analysis
================================================
Slices a single fetched record set into multiple time windows and runs
the full bibliometric analysis pipeline on each, writing per-period
output subdirectories.

Usage (called automatically by main.py):
    from periods import run_all_periods
    run_all_periods(records, output_root="output")
"""

import os
import pathlib

import config


def _filter_by_period(records: list[dict], start: int, end: int) -> list[dict]:
    """Return records whose publication year falls within [start, end] inclusive."""
    out = []
    for rec in records:
        try:
            yr = int(rec.get("year", 0))
        except (ValueError, TypeError):
            yr = 0
        if yr and start <= yr <= end:
            out.append(rec)
    return out


def run_all_periods(records: list[dict], output_root: str = None) -> dict:
    """
    Run the full analysis pipeline for every period defined in
    config.ANALYSIS_PERIODS.

    Returns a dict keyed by period label containing the analysis results
    for each window.  Also writes per-period output subdirectories and
    a combined summary CSV.
    """
    import analyze
    import report
    import visualize

    output_root = output_root or config.OUTPUT_DIR
    all_results: dict[str, dict] = {}

    for label, start, end in config.ANALYSIS_PERIODS:
        period_records = _filter_by_period(records, start, end)
        n = len(period_records)
        if n == 0:
            print(f"[periods] {label}: no records — skipping")
            continue

        print(f"\n{'='*60}")
        print(f"[periods] {label}: {n:,} records ({start}–{end})")
        print(f"{'='*60}")

        # Per-period output directory
        period_dir = pathlib.Path(output_root) / label
        period_dir.mkdir(parents=True, exist_ok=True)

        # Override OUTPUT_DIR for this period so visualize/report write there
        _orig = config.OUTPUT_DIR
        config.OUTPUT_DIR = str(period_dir)

        try:
            results = analyze.run_analysis(period_records)
            report.run_report(results, period_records)
            visualize.run_visualizations(results)
        finally:
            config.OUTPUT_DIR = _orig

        results["_period"] = {"label": label, "start": start, "end": end, "n": n}
        all_results[label] = results

    # ── Combined summary table ────────────────────────────────────────────────
    _write_period_summary(all_results, output_root)

    return all_results


def _write_period_summary(all_results: dict, output_root: str) -> None:
    """Write a single CSV comparing headline metrics across all time windows."""
    import csv

    rows = []
    for label, res in all_results.items():
        p = res.get("_period", {})
        summary = res.get("summary", {})
        rows.append({
            "period":              label,
            "start_year":          p.get("start", ""),
            "end_year":            p.get("end", ""),
            "total_publications":  p.get("n", ""),
            "total_citations":     summary.get("total_citations", ""),
            "unique_authors":      summary.get("unique_authors", ""),
            "unique_journals":     summary.get("unique_journals", ""),
            "unique_countries":    summary.get("unique_countries", ""),
            "mean_cites_per_pub":  summary.get("mean_cites_per_pub", ""),
            "h_index_field":       summary.get("h_index_field", ""),
        })

    outpath = pathlib.Path(output_root) / "period_comparison.csv"
    if not rows:
        return
    fields = list(rows[0].keys())
    with open(outpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[periods] Period comparison saved → {outpath}")
