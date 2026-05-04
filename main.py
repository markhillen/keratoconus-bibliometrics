#!/usr/bin/env python3
"""
main.py — Keratoconus Bibliometric Analysis Pipeline
=====================================================
Orchestrates the full analysis pipeline:

  1. Fetch PubMed records (cached)
  2. Relevance filtering
  3. Author disambiguation
  4. Country enrichment
  5. Citation enrichment (CrossRef)
  6. Multi-period bibliometric analysis (all-time / last 25/20/15/10/5yr)
  7. Visualization + reports per period
  8. Period comparison summary

Usage:
  python3 main.py --api-key YOUR_NCBI_KEY
  python3 main.py --api-key YOUR_NCBI_KEY --refresh
  python3 main.py --skip-fetch
  python3 main.py --skip-citations
  python3 main.py --pmid-file pmids.txt
  python3 main.py --period all_time          # single period only
"""

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="Keratoconus Bibliometric Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-key",        default="",   help="NCBI API key")
    parser.add_argument("--pmid-file",      default="",   help="Path to PMID list file")
    parser.add_argument("--refresh",        action="store_true", help="Force re-download")
    parser.add_argument("--skip-fetch",     action="store_true", help="Use cached records only")
    parser.add_argument("--skip-citations", action="store_true", help="Skip CrossRef lookup")
    parser.add_argument("--skip-viz",       action="store_true", help="Skip chart generation")
    parser.add_argument("--period",         default="",   help="Single period label to run")
    args = parser.parse_args()

    import config
    if args.api_key:
        config.NCBI_API_KEY = args.api_key
    if args.skip_citations:
        config.FETCH_CITATIONS = False
    if args.period:
        config.ANALYSIS_PERIODS = [p for p in config.ANALYSIS_PERIODS if p[0] == args.period]
        if not config.ANALYSIS_PERIODS:
            print(f"[main] ERROR: Unknown period '{args.period}'.")
            sys.exit(1)

    pathlib.Path(config.CACHE_DIR).mkdir(parents=True, exist_ok=True)
    pathlib.Path(config.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("=" * 60)
    print(f"  {config.PROJECT_NAME} v{config.PROJECT_VERSION}")
    print(f"  All-time fetch: {config.ALL_TIME_START}–{config.END_YEAR}")
    print(f"  Periods: {[p[0] for p in config.ANALYSIS_PERIODS]}")
    print("=" * 60)

    # ── Step 1: Fetch ─────────────────────────────────────────────────────────
    print(f"\n[1/8] Fetching records …")
    cited_path  = pathlib.Path(config.CACHE_DIR) / "records_cited.json"
    disamb_path = pathlib.Path(config.CACHE_DIR) / "records_disambig.json"
    raw_path    = pathlib.Path(config.CACHE_DIR) / "records.json"

    if args.skip_fetch:
        for p in [cited_path, disamb_path, raw_path]:
            if p.exists():
                print(f"[main] Loading {p.name} from cache …")
                with open(p) as f:
                    records = json.load(f)
                print(f"[main] {len(records):,} records loaded")
                break
        else:
            print("[main] ERROR: No cached records. Run without --skip-fetch first.")
            sys.exit(1)
    else:
        if args.pmid_file:
            from fetch import run_fetch_from_pmids
            records = run_fetch_from_pmids(
                pmid_file=args.pmid_file,
                api_key=config.NCBI_API_KEY,
                force_refresh=args.refresh,
            )
        else:
            from fetch import run_fetch
            records = run_fetch(api_key=config.NCBI_API_KEY, force_refresh=args.refresh)
    print(f"[main] {len(records):,} records after filtering")

    # ── Step 2: Disambiguation ────────────────────────────────────────────────
    print(f"\n[2/8] Disambiguating authors …")
    has_ids = any(
        a.get("author_id")
        for rec in records[:50]
        for a in rec.get("authors", [])
    )
    if args.skip_fetch and has_ids:
        print("[main] Author IDs already present — skipping disambiguation")
    else:
        from disambiguate import assign_author_ids
        records, stats = assign_author_ids(records)
        with open(disamb_path, "w") as f:
            json.dump(records, f)
        print(f"[main] {stats.get('unique_authors', '?')} unique authors identified")

    # ── Step 3: Country enrichment ────────────────────────────────────────────
    print(f"\n[3/8] Enriching countries …")
    from geo import enrich_countries
    records = enrich_countries(records)

    # ── Step 4: Citations ─────────────────────────────────────────────────────
    print(f"\n[4/8] Citation enrichment …")
    if config.FETCH_CITATIONS:
        from citations import enrich_citations
        records = enrich_citations(records)
        with open(cited_path, "w") as f:
            json.dump(records, f)
    else:
        print("[main] Skipped")

    # ── Steps 5–8: Multi-period ───────────────────────────────────────────────
    print(f"\n[5–8/8] Multi-period analysis …")
    from periods import run_all_periods
    all_results = run_all_periods(records, output_root=config.OUTPUT_DIR)

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print("  PIPELINE COMPLETE")
    for label, res in all_results.items():
        p = res.get("_period", {})
        print(f"  {label:<14}  {p.get('n', '?'):>7,} records  "
              f"({p.get('start')}–{p.get('end')})")
    print(f"\n  Elapsed: {elapsed:.1f}s  |  Output: {config.OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
