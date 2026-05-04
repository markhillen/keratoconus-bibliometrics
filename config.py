"""
Keratoconus Bibliometrics — Configuration
==========================================
Edit this file to change search parameters, date ranges, API keys, and output paths.
"""

import os
from datetime import date

# ── Project identity ──────────────────────────────────────────────────────────
PROJECT_NAME    = "Keratoconus Bibliometrics"
PROJECT_VERSION = "1.0.0"

# ── API Credentials ───────────────────────────────────────────────────────────
# Get a free NCBI API key at: https://www.ncbi.nlm.nih.gov/account/
# With key: 10 requests/sec  |  Without key: 3 requests/sec
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")

# ── Date Range ────────────────────────────────────────────────────────────────
# ALL_TIME_START: earliest year to include. PubMed has keratoconus records
# from the 1950s; 1950 safely captures the full indexed literature.
ALL_TIME_START = 1950
END_YEAR       = date.today().year   # inclusive; updates automatically

# START_YEAR is used for the default/primary analysis window.
# The multi-period analysis runs all windows defined in ANALYSIS_PERIODS.
START_YEAR = ALL_TIME_START

# ── Analysis time windows ─────────────────────────────────────────────────────
# Each entry: (label, start_year, end_year)
# All windows use the same fetched dataset — no extra API calls.
ANALYSIS_PERIODS = [
    ("all_time",    ALL_TIME_START, END_YEAR),
    ("last_25yr",   END_YEAR - 24,  END_YEAR),
    ("last_20yr",   END_YEAR - 19,  END_YEAR),
    ("last_15yr",   END_YEAR - 14,  END_YEAR),
    ("last_10yr",   END_YEAR - 9,   END_YEAR),
    ("last_5yr",    END_YEAR - 4,   END_YEAR),
]

# ── PubMed Search Query ───────────────────────────────────────────────────────
# Covers keratoconus and its recognised clinical variants / synonyms.
# Does NOT include CXL treatment terms — those belong to the CXL project.
# NOT clause removes non-ophthalmic collagen/structural biology papers that
# incidentally mention "corneal ectasia" in a non-clinical context.
PUBMED_QUERY = (
    '('
    '"keratoconus"[tiab] OR "keratoconus"[MeSH Terms] OR '
    '"corneal ectasia"[tiab] OR '
    '"keratectasia"[tiab] OR '
    '"pellucid marginal degeneration"[tiab] OR '
    '"pellucid marginal corneal degeneration"[tiab] OR '
    '"posterior keratoconus"[tiab] OR '
    '"forme fruste keratoconus"[tiab] OR '
    '"ectatic corneal disease"[tiab] OR '
    '"corneal ectatic disease"[tiab]'
    ') '
    'NOT ('
    '"cartilage"[tiab] OR "polymer"[tiab] OR "hydrogel"[tiab] OR '
    '"scaffold"[tiab] OR "tissue engineering"[tiab] OR '
    '"bone"[tiab] OR "dental"[tiab]'
    ') '
    f'AND ("{ALL_TIME_START}/01/01"[PDAT] : "{END_YEAR}/12/31"[PDAT])'
)

# ── Fetch Settings ─────────────────────────────────────────────────────────────
BATCH_SIZE        = 200
REQUEST_DELAY     = 0.15
MAX_RETRIES       = 3

# ── Author Disambiguation ──────────────────────────────────────────────────────
DISAMBIGUATION_CO_AUTHOR_THRESHOLD = 2
MIN_AUTHOR_PUBS = 3

# ── Citation Enrichment ────────────────────────────────────────────────────────
FETCH_CITATIONS      = True
CITATION_BATCH_DELAY = 0.5

# ── Co-occurrence / Network ────────────────────────────────────────────────────
MIN_KEYWORD_FREQ = 10    # higher than CXL — keratoconus corpus is larger

# ── Output ────────────────────────────────────────────────────────────────────
TOP_N_AUTHORS      = 25
TOP_N_COUNTRIES    = 20
TOP_N_INSTITUTIONS = 20
TOP_N_JOURNALS     = 20
TOP_N_KEYWORDS     = 25

OUTPUT_DIR = os.environ.get("KC_OUTPUT_DIR", "output")
CACHE_DIR  = os.environ.get("KC_CACHE_DIR",  "cache")
