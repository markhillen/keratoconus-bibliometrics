# Keratoconus Bibliometrics

A reproducible, open-source bibliometric analysis pipeline for the global scientific literature on **keratoconus and corneal ectasia**.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

This pipeline retrieves, processes, and analyses all PubMed-indexed publications on keratoconus and corneal ectasia from 1950 to the present day. It produces:

- Publication volume and growth trend figures (all-time, last 25/20/15/10/5 years)
- Geographic distribution and per-capita output maps
- Author productivity, first/last authorship, and citation efficiency rankings
- Institution-level analysis (first-author attribution)
- Journal distribution (Bradford's Law of Scattering)
- Author co-authorship networks (static PNG + interactive HTML)
- Keyword co-occurrence and temporal trajectory figures
- A cross-period comparison table (headline metrics across all time windows)

The pipeline is designed to be fully reproducible: all data derive from the open PubMed E-utilities API and the CrossRef REST API. No institutional database access is required.

---

## Search Strategy

```
(keratoconus OR "corneal ectasia" OR keratectasia OR
 "pellucid marginal degeneration" OR "posterior keratoconus" OR
 "forme fruste keratoconus" OR "ectatic corneal disease")
NOT (cartilage OR polymer OR hydrogel OR scaffold OR "tissue engineering"
     OR bone OR dental)
Date: 1950/01/01 – present
Database: PubMed (NCBI E-utilities)
```

A post-fetch relevance filter expels records from non-ophthalmic journals or records lacking any ophthalmic/corneal term in title or abstract.

---

## Time Windows

The pipeline runs the full analysis for six overlapping time windows from a single fetch:

| Label       | Years           |
|-------------|-----------------|
| `all_time`  | 1950 – present  |
| `last_25yr` | 2001 – present  |
| `last_20yr` | 2006 – present  |
| `last_15yr` | 2011 – present  |
| `last_10yr` | 2016 – present  |
| `last_5yr`  | 2021 – present  |

---

## Installation

```bash
git clone https://github.com/markhillen/keratoconus-bibliometrics.git
cd keratoconus-bibliometrics
pip install -r requirements.txt
```

Get a free NCBI API key at https://www.ncbi.nlm.nih.gov/account/ (optional but recommended — raises rate limit from 3 to 10 requests/sec).

---

## Usage

### Full pipeline (recommended first run)

```bash
python3 main.py --api-key YOUR_NCBI_KEY
```

### Using a pre-curated PMID list

```bash
python3 main.py --api-key YOUR_NCBI_KEY --pmid-file pmids.txt
```

### Re-run analysis from cache (no API calls)

```bash
python3 main.py --skip-fetch --skip-citations
```

### Single time window only

```bash
python3 main.py --skip-fetch --skip-citations --period last_10yr
```

### GUI (browser-based interface)

```bash
python3 gui.py
```
Opens at http://localhost:7432

---

## Output Structure

```
output/
├── all_time/
│   ├── fig1_annual_output.png
│   ├── fig2_cumulative.png
│   ├── fig3_top_countries.png        # 4 panels incl. per-capita
│   ├── fig4_top_authors.png          # total / first / last authorship
│   ├── fig5_top_journals.png
│   ├── fig6_bradford.png
│   ├── fig7_keywords_top.png
│   ├── fig8_keyword_trends.png
│   ├── fig9_institutions.png         # first-author attribution
│   ├── fig10_author_network.png
│   ├── author_network_interactive.html
│   ├── authors_top.csv
│   ├── countries_top.csv             # incl. pubs_per_million
│   ├── journals_top.csv
│   └── institutions_top.csv
├── last_25yr/
│   └── [same structure]
├── last_20yr/ …
├── last_15yr/ …
├── last_10yr/ …
├── last_5yr/  …
└── period_comparison.csv             # headline metrics across all windows
```

---

## Author Disambiguation

Author identity is resolved using a four-layer heuristic algorithm:

1. **ORCID** — gold standard, merged unconditionally
2. **Exact forename** — identical normalised last name + full forename
3. **Co-author network overlap** — ≥2 shared co-authors required to merge initials-only variants
4. **Institution-aware splitting** — common surnames (Zhang, Kim, Singh, …) with confirmed distinct institutional affiliations are kept separate

Known family pairs and same-name collisions in the keratoconus literature are protected by manual safelists in `disambiguate.py` (`KNOWN_DISTINCT` and `KNOWN_DISTINCT_AFFIL`).

---

## Citation

If you use this pipeline in published research, please cite:

> [Authors]. Global Research Trends in Keratoconus: A Comprehensive Bibliometric Analysis of the Scientific Literature. *Contact Lens & Anterior Eye*. [in preparation].

---

## Repository

https://github.com/markhillen/keratoconus-bibliometrics

---

## Corresponding author

[Name], [Institution], [email]

---

## License

MIT — see [LICENSE](LICENSE).
