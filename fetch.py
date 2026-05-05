"""
fetch.py — PubMed retrieval via NCBI E-utilities
=================================================
Downloads all CXL records and caches them as JSON.
Run standalone:  python3 fetch.py [--api-key YOUR_KEY]
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import pathlib
import argparse

# ── allow running standalone or imported ─────────────────────────────────────
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def _get(url: str, retries: int = config.MAX_RETRIES) -> str:
    """HTTP GET with retry/back-off."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            wait = 2 ** attempt
            print(f"  [warn] GET failed ({e}), retry {attempt+1}/{retries} in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch: {url[:120]}")


def esearch(query: str, retmax: int = 100_000, api_key: str = "") -> list[str]:
    """Return list of PMIDs matching query."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "usehistory": "n",
    }
    if api_key:
        params["api_key"] = api_key
    url = BASE_URL + "esearch.fcgi?" + urllib.parse.urlencode(params)
    print(f"[esearch] Querying PubMed …")
    data = json.loads(_get(url))
    pmids = data["esearchresult"]["idlist"]
    total = int(data["esearchresult"]["count"])
    print(f"[esearch] Found {total} total records; retrieved {len(pmids)} PMIDs")
    return pmids


def efetch_batch(pmids: list[str], api_key: str = "") -> list[dict]:
    """Fetch full records for a list of PMIDs in batches."""
    records = []
    total = len(pmids)
    batch_size = config.BATCH_SIZE
    delay = config.REQUEST_DELAY if api_key else 0.34

    for i in range(0, total, batch_size):
        batch = pmids[i: i + batch_size]
        pct = (i + len(batch)) / total * 100
        print(f"  fetching records {i+1}–{i+len(batch)} / {total}  ({pct:.1f}%)", end="\r")

        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key
        url = BASE_URL + "efetch.fcgi?" + urllib.parse.urlencode(params)
        xml_text = _get(url)
        records.extend(_parse_pubmed_xml(xml_text))
        time.sleep(delay)

    print(f"\n[efetch] Parsed {len(records)} records")
    return records


# ── XML parsing ───────────────────────────────────────────────────────────────

def _text(elem, path, default=""):
    node = elem.find(path)
    return (node.text or "").strip() if node is not None else default


def _parse_author(auth_elem) -> dict:
    """Parse a single <Author> element."""
    last   = _text(auth_elem, "LastName")
    fore   = _text(auth_elem, "ForeName")
    initials = _text(auth_elem, "Initials")
    # Collect affiliations
    affils = [
        (aff.text or "").strip()
        for aff in auth_elem.findall("AffiliationInfo/Affiliation")
    ]
    # ORCID if present
    orcid = ""
    for ident in auth_elem.findall("Identifier"):
        if ident.get("Source") == "ORCID":
            orcid = (ident.text or "").replace("http://orcid.org/", "").strip()
    collective = _text(auth_elem, "CollectiveName")
    return {
        "last": last,
        "fore": fore,
        "initials": initials,
        "affils": affils,
        "orcid": orcid,
        "collective": collective,
    }


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubmedArticleSet XML into list of record dicts."""
    records = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"\n  [warn] XML parse error: {e}")
        return records

    for article in root.findall(".//PubmedArticle"):
        rec = {}

        # ── PMID ──────────────────────────────────────────────────────────
        rec["pmid"] = _text(article, ".//PMID")

        # ── Publication date ───────────────────────────────────────────────
        pub_date = article.find(".//PubMedPubDate[@PubStatus='pubmed']")
        if pub_date is None:
            pub_date = article.find(".//PubDate")
        year  = _text(pub_date, "Year")  if pub_date is not None else ""
        month = _text(pub_date, "Month") if pub_date is not None else ""
        rec["year"]  = year
        rec["month"] = month

        # ── Article title ──────────────────────────────────────────────────
        rec["title"] = _text(article, ".//ArticleTitle")

        # ── Abstract ──────────────────────────────────────────────────────
        abstract_parts = []
        for ab in article.findall(".//AbstractText"):
            label = ab.get("Label", "")
            text  = (ab.text or "").strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        rec["abstract"] = " ".join(abstract_parts)

        # ── Journal ───────────────────────────────────────────────────────
        rec["journal"]     = _text(article, ".//Journal/Title")
        rec["journal_abbr"]= _text(article, ".//Journal/ISOAbbreviation")
        rec["issn"]        = _text(article, ".//Journal/ISSN")
        rec["volume"]      = _text(article, ".//Volume")
        rec["issue"]       = _text(article, ".//Issue")

        # ── DOI ───────────────────────────────────────────────────────────
        doi = ""
        for eloc in article.findall(".//ELocationID"):
            if eloc.get("EIdType") == "doi":
                doi = (eloc.text or "").strip()
        if not doi:
            for aid in article.findall(".//ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = (aid.text or "").strip()
        rec["doi"] = doi

        # ── Publication type ──────────────────────────────────────────────
        rec["pub_types"] = [
            (pt.text or "").strip()
            for pt in article.findall(".//PublicationTypeList/PublicationType")
        ]

        # ── Authors ───────────────────────────────────────────────────────
        authors = [
            _parse_author(a)
            for a in article.findall(".//AuthorList/Author")
            if _parse_author(a)["last"] or _parse_author(a)["collective"]
        ]

        # ── Affiliation fallbacks for legacy PubMed record formats ────────
        # Format A (pre-~2013): single <Affiliation> at Article level,
        # path is MedlineCitation/Article/Affiliation — shared by all authors.
        if not any(a["affils"] for a in authors):
            legacy = (
                article.findtext("MedlineCitation/Article/Affiliation") or
                article.findtext(".//Article/Affiliation") or
                ""
            ).strip()
            if legacy:
                for a in authors:
                    a["affils"] = [legacy]

        # Format B (mid-era ~2010–2013): only the first author has
        # <AffiliationInfo>; co-authors are blank. Propagate to blanks.
        if authors:
            first_affils = next(
                (a["affils"] for a in authors if a["affils"]), []
            )
            if first_affils:
                for a in authors:
                    if not a["affils"]:
                        a["affils"] = first_affils

        rec["authors"] = authors

        # ── MeSH terms ────────────────────────────────────────────────────
        rec["mesh"] = [
            _text(mh, "DescriptorName")
            for mh in article.findall(".//MeshHeadingList/MeshHeading")
        ]

        # ── Keywords ──────────────────────────────────────────────────────
        rec["keywords"] = [
            (kw.text or "").strip()
            for kw in article.findall(".//KeywordList/Keyword")
        ]

        # ── Grant info ────────────────────────────────────────────────────
        rec["grants"] = [
            {
                "id":      _text(g, "GrantID"),
                "agency":  _text(g, "Agency"),
                "country": _text(g, "Country"),
            }
            for g in article.findall(".//GrantList/Grant")
        ]

        # ── Language ──────────────────────────────────────────────────────
        rec["language"] = _text(article, ".//Language")

        # ── Country of publication ────────────────────────────────────────
        rec["pub_country"] = _text(article, ".//MedlineJournalInfo/Country")

        # ── Citation count placeholder ─────────────────────────────────────
        rec["citation_count"] = None

        records.append(rec)

    return records


# ── Top-level runner ──────────────────────────────────────────────────────────

def is_kc_relevant(rec: dict) -> tuple[bool, str]:
    """
    Return (True, "") if the record is a legitimate keratoconus / corneal
    ectasia publication, or (False, reason) if it should be excluded.

    The PubMed query occasionally retrieves records where keratoconus or
    ectasia terms appear incidentally in non-ophthalmic contexts (structural
    biology, polymer science, etc.).  This filter expels them.

    Checks applied in order (cheapest first):
      1. Journal-level exclusion — definitively non-ophthalmic journals.
      2. MeSH-level exclusion — non-ophthalmic primary MeSH headings.
      3. Title + abstract must contain at least one ophthalmic term.
    """
    title    = (rec.get("title",    "") or "").lower()
    abstract = (rec.get("abstract", "") or "").lower()
    journal  = (rec.get("journal",  "") or "").lower()
    mesh     = [m.lower() for m in rec.get("mesh", [])]
    combined = title + " " + abstract

    # ── 1. Journal-level exclusion ────────────────────────────────────────────
    _EXCLUDED_JOURNALS = (
        "plastic", "aesthetic", "rhinoplasty", "reconstructive surgery",
        "annals of surgery", "dental", "oral", "maxillofacial",
        "orthodont", "endodont", "periodon", "biomaterials", "acta biomater",
        "polymer", "hydrogel", "tissue engineering", "wound repair",
        "cartilage", "bone", "spine", "orthop", "dermatol", "skin",
        "vascular", "cardiovasc", "thoracic", "urology", "gynaecol",
        "gynecol", "obstet", "hepatol", "gastroenter", "neurosurg",
        "psychiatr", "oncol", "hematol", "endocrinol", "nephrol",
        "pulmonol", "respirat",
    )
    for jkw in _EXCLUDED_JOURNALS:
        if jkw in journal:
            return False, f"Non-ophthalmic journal: {rec.get('journal', '')}"

    # ── 2. MeSH-level exclusion ───────────────────────────────────────────────
    _EXCLUDED_MESH = (
        "rhinoplasty", "plastic surgery", "reconstructive surgical procedures",
        "skin transplantation", "cartilage", "bone and bones", "dental enamel",
        "dentin", "tooth", "dental pulp", "periodontal", "orthodontic",
        "tissue scaffolds", "tissue engineering", "cardiovascular", "aorta",
        "blood vessels",
    )
    for mkw in _EXCLUDED_MESH:
        if any(mkw in m for m in mesh):
            return False, f"Excluded MeSH term: {mkw}"

    # ── 3. Title + abstract must contain at least one ECTASIA-SPECIFIC term ──
    # A paper about keratoconus/ectasia must mention one of these conditions
    # explicitly. "keratitis" or generic ophthalmic terms alone are NOT
    # sufficient — this prevents PACK-CXL (infectious keratitis), PDT, and
    # other corneal infection papers leaking through.
    _ECTASIA_TERMS = (
        "keratoconus", "keratoconic", "corneal ectasia", "keratectasia",
        "ectatic cornea", "ectatic disease", "corneal ectatic",
        "pellucid marginal", "pellucid marginal degeneration", "pmd",
        "keratoglobus", "posterior keratoconus", "forme fruste",
        "post-lasik ectasia", "post lasik ectasia", "post-refractive ectasia",
        "post refractive ectasia", "iatrogenic ectasia", "ectasia after",
        "corneal thinning disorder", "corneal biomechanics",
        "bowman layer", "bowman's layer", "bowman membrane",
        "stromal thinning", "corneal protrusion", "corneal bulging",
        "vogt striae", "fleischer ring", "munson sign",
        "intrastromal corneal ring", "icrs", "intacs", "ferrara ring",
        "deep anterior lamellar", "dalk", "penetrating keratoplasty",
        "corneal transplant", "keratoplasty", "corneal graft",
        "contact lens for kerato", "scleral lens", "rigid gas permeable",
        "topography-guided", "corneal topography", "scheimpflug",
        "corneal tomography", "pentacam", "corvis", "ocular response",
        "collagen cross-link", "corneal cross-link", "crosslink",
        "kmax", "k-max", "flat k", "steep k", "belin",
        "amsler", "rabinowitz", "thinnest point", "pachymetry",
        "corneal pachymetry", "corneal thickness",
        "genetic", "genome", "gwas", "heritability",
        "artificial intelligence", "deep learning", "machine learning",
    )
    if not any(term in combined for term in _ECTASIA_TERMS):
        return False, "No keratoconus/ectasia-specific term found in title or abstract"

    return True, ""


def filter_records(records: list[dict]) -> list[dict]:
    """Apply is_kc_relevant() and return only relevant records, logging exclusions."""
    kept = []
    excluded_count = 0
    for rec in records:
        relevant, reason = is_kc_relevant(rec)
        if relevant:
            kept.append(rec)
        else:
            excluded_count += 1
            if excluded_count <= 20:
                pmid  = rec.get("pmid", "?")
                title = (rec.get("title", "") or "")[:80]
                print(f"  [filter] Excluded PMID {pmid}: {reason} | \"{title}\"")
    if excluded_count > 20:
        print(f"  [filter] ... and {excluded_count - 20} more excluded (not shown)")
    print(f"[filter] {len(kept)} records retained, {excluded_count} excluded")
    return kept


def run_fetch(api_key: str = "", force_refresh: bool = False) -> list[dict]:
    """
    Full fetch pipeline. Returns list of record dicts.
    Results cached to CACHE_DIR/records.json.
    """
    cache_path = pathlib.Path(config.CACHE_DIR) / "records.json"

    if cache_path.exists() and not force_refresh:
        print(f"[fetch] Loading cached records from {cache_path}")
        with open(cache_path) as f:
            records = json.load(f)
        print(f"[fetch] Loaded {len(records)} cached records")
        return records

    api_key = api_key or config.NCBI_API_KEY
    pmids = esearch(config.PUBMED_QUERY, api_key=api_key)

    # Cache PMIDs
    pmid_path = pathlib.Path(config.CACHE_DIR) / "pmids.json"
    with open(pmid_path, "w") as f:
        json.dump(pmids, f)
    print(f"[fetch] Saved {len(pmids)} PMIDs to {pmid_path}")

    records = efetch_batch(pmids, api_key=api_key)
    records = filter_records(records)

    with open(cache_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"[fetch] Saved {len(records)} records to {cache_path}")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch CXL PubMed records")
    parser.add_argument("--api-key", default="", help="NCBI API key")
    parser.add_argument("--refresh", action="store_true", help="Force re-download")
    args = parser.parse_args()
    records = run_fetch(api_key=args.api_key, force_refresh=args.refresh)
    print(f"\nDone. {len(records)} records ready.")


# ── PMID-file entry point ─────────────────────────────────────────────────────

def load_pmids_from_file(filepath: str) -> list[str]:
    """Load PMIDs from a plain text file (one per line)."""
    lines = pathlib.Path(filepath).read_text().strip().splitlines()
    pmids = [l.strip() for l in lines if l.strip() and l.strip().isdigit()]
    print(f"[fetch] Loaded {len(pmids)} PMIDs from {filepath}")
    return pmids


def run_fetch_from_pmids(pmid_file: str, api_key: str = "",
                         force_refresh: bool = False) -> list[dict]:
    """
    Fetch full records for a provided PMID list file.
    Skips esearch entirely — uses the given PMIDs directly.
    Results cached to CACHE_DIR/records.json.
    """
    cache_path = pathlib.Path(config.CACHE_DIR) / "records.json"

    if cache_path.exists() and not force_refresh:
        print(f"[fetch] Loading cached records from {cache_path}")
        with open(cache_path) as f:
            records = json.load(f)
        print(f"[fetch] Loaded {len(records)} cached records")
        return records

    api_key = api_key or config.NCBI_API_KEY
    pmids = load_pmids_from_file(pmid_file)

    # Save PMID list to cache
    pmid_path = pathlib.Path(config.CACHE_DIR) / "pmids.json"
    with open(pmid_path, "w") as f:
        json.dump(pmids, f)

    records = efetch_batch(pmids, api_key=api_key)
    records = filter_records(records)

    with open(cache_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"[fetch] Saved {len(records)} records to {cache_path}")
    return records
