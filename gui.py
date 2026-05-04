#!/usr/bin/env python3
"""
gui.py — CXL Bibliometric Analysis — Local Web GUI
====================================================
Zero extra dependencies beyond the standard library.
Launches a local web server and opens the GUI in your browser.

Run:   python3 gui.py
Then:  browser opens automatically at http://localhost:7432
"""

import http.server
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Paths — all relative to wherever gui.py lives ────────────────────────────
HERE       = pathlib.Path(__file__).resolve().parent
CACHE_DIR  = HERE / "cache"
DATA_DIR   = HERE / "data"
OUTPUT_DIR = HERE / "outputs"

for d in [CACHE_DIR, DATA_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

PORT = 7432

# ── Global state ──────────────────────────────────────────────────────────────
_log_queue:  queue.Queue = queue.Queue()
_run_state = {"running": False, "done": False, "error": False, "pid": None}
_last_config: dict = {}

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CXL Bibliometrics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,300;9..144,600&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0e1117;
    --surface:  #161b27;
    --card:     #1d2535;
    --border:   #2a3347;
    --accent:   #4f8ef7;
    --accent2:  #38d9a9;
    --accent3:  #f7934f;
    --warn:     #f7c94f;
    --danger:   #f7614f;
    --text:     #e2e8f4;
    --muted:    #7a8ba8;
    --mono:     'DM Mono', monospace;
    --serif:    'Fraunces', Georgia, serif;
    --sans:     'DM Sans', sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 15px; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr;
  }

  /* ── Header ── */
  header {
    border-bottom: 1px solid var(--border);
    padding: 1.2rem 2rem;
    display: flex;
    align-items: baseline;
    gap: 1.4rem;
    background: var(--surface);
  }
  header h1 {
    font-family: var(--serif);
    font-weight: 300;
    font-size: 1.55rem;
    letter-spacing: -.02em;
    color: var(--text);
  }
  header h1 span { color: var(--accent); font-weight: 600; }
  header .sub {
    font-size: .78rem;
    color: var(--muted);
    font-family: var(--mono);
  }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--muted);
    display: inline-block;
    margin-left: auto;
    transition: background .3s;
  }
  .status-dot.running { background: var(--accent2); animation: pulse 1.2s infinite; }
  .status-dot.done    { background: var(--accent2); }
  .status-dot.error   { background: var(--danger); }
  @keyframes pulse {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:.5; transform:scale(1.3); }
  }

  /* ── Layout ── */
  main {
    display: grid;
    grid-template-columns: 360px 1fr;
    gap: 0;
    height: calc(100vh - 61px);
    overflow: hidden;
  }

  /* ── Sidebar ── */
  aside {
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 1.6rem 1.4rem;
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
  }
  .section-label {
    font-family: var(--mono);
    font-size: .68rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .12em;
    margin-bottom: .6rem;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.1rem 1.2rem;
  }
  .card h3 {
    font-size: .82rem;
    font-weight: 500;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 1rem;
    font-family: var(--mono);
  }

  /* Presets */
  .presets {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .5rem;
  }
  .preset-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: .45rem .6rem;
    font-size: .8rem;
    font-family: var(--sans);
    cursor: pointer;
    transition: all .15s;
    text-align: center;
  }
  .preset-btn:hover { border-color: var(--accent); color: var(--accent); }
  .preset-btn.active { border-color: var(--accent); background: #1a2a4a; color: var(--accent); }

  /* Year sliders */
  .year-row {
    display: flex;
    align-items: center;
    gap: .8rem;
    margin-bottom: .7rem;
  }
  .year-row label {
    font-size: .78rem;
    color: var(--muted);
    width: 2.8rem;
    font-family: var(--mono);
  }
  .year-row input[type=range] {
    flex: 1;
    -webkit-appearance: none;
    height: 4px;
    border-radius: 2px;
    background: var(--border);
    outline: none;
    cursor: pointer;
  }
  .year-row input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px; height: 14px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    transition: transform .15s;
  }
  .year-row input[type=range]::-webkit-slider-thumb:hover { transform: scale(1.25); }
  .year-display {
    font-family: var(--mono);
    font-size: .88rem;
    color: var(--accent);
    width: 2.4rem;
    text-align: right;
  }
  .year-range-summary {
    font-family: var(--mono);
    font-size: .82rem;
    color: var(--accent2);
    text-align: center;
    padding: .4rem;
    background: #0d1f18;
    border-radius: 5px;
    border: 1px solid #1d4035;
    margin-top: .2rem;
  }

  /* Text inputs */
  .field { margin-bottom: .85rem; }
  .field label {
    display: block;
    font-size: .75rem;
    color: var(--muted);
    margin-bottom: .35rem;
    font-family: var(--mono);
  }
  .field input, .field textarea {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-family: var(--mono);
    font-size: .8rem;
    padding: .5rem .7rem;
    outline: none;
    transition: border-color .15s;
    resize: vertical;
  }
  .field input:focus, .field textarea:focus { border-color: var(--accent); }
  .field .hint {
    font-size: .7rem;
    color: var(--muted);
    margin-top: .3rem;
    line-height: 1.4;
  }

  /* Toggle row */
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: .6rem;
  }
  .toggle-row span {
    font-size: .8rem;
    color: var(--text);
  }
  .toggle-row .hint-inline {
    font-size: .7rem;
    color: var(--muted);
    margin-top: .1rem;
  }
  .toggle {
    position: relative;
    width: 36px; height: 20px;
  }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle-slider {
    position: absolute; inset: 0;
    background: var(--border);
    border-radius: 20px;
    cursor: pointer;
    transition: background .2s;
  }
  .toggle-slider::before {
    content: '';
    position: absolute;
    width: 14px; height: 14px;
    left: 3px; bottom: 3px;
    background: #fff;
    border-radius: 50%;
    transition: transform .2s;
  }
  .toggle input:checked + .toggle-slider { background: var(--accent2); }
  .toggle input:checked + .toggle-slider::before { transform: translateX(16px); }

  /* Run button */
  #run-btn {
    width: 100%;
    padding: .85rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: .95rem;
    font-weight: 500;
    font-family: var(--sans);
    cursor: pointer;
    transition: all .2s;
    letter-spacing: .02em;
  }
  #run-btn:hover:not(:disabled) { background: #6fa3fa; transform: translateY(-1px); }
  #run-btn:disabled {
    background: var(--border);
    color: var(--muted);
    cursor: not-allowed;
    transform: none;
  }
  #run-btn.running { background: var(--danger); }
  #run-btn.running:hover:not(:disabled) { background: #f97a6b; }

  /* ── Main panel ── */
  .main-panel {
    display: grid;
    grid-template-rows: auto 1fr auto;
    overflow: hidden;
  }

  /* Progress bar */
  .progress-bar-wrap {
    height: 3px;
    background: var(--border);
    overflow: hidden;
  }
  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    width: 0%;
    transition: width .4s;
  }
  .progress-bar.indeterminate {
    width: 30%;
    animation: indeterminate 1.5s infinite ease-in-out;
  }
  @keyframes indeterminate {
    0%   { transform: translateX(-100%); }
    100% { transform: translateX(400%); }
  }

  /* Tabs */
  .tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    padding: 0 1.5rem;
    gap: .2rem;
  }
  .tab {
    padding: .7rem 1rem;
    font-size: .82rem;
    font-family: var(--mono);
    color: var(--muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all .15s;
    user-select: none;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab .badge {
    display: inline-block;
    background: var(--border);
    border-radius: 10px;
    font-size: .65rem;
    padding: .05rem .4rem;
    margin-left: .4rem;
    vertical-align: middle;
    color: var(--muted);
  }
  .tab.active .badge { background: #1a2a4a; color: var(--accent); }

  /* Tab panels */
  .tab-panels { overflow: hidden; flex: 1; position: relative; }
  .tab-panel {
    position: absolute;
    inset: 0;
    overflow-y: auto;
    padding: 1.4rem 1.6rem;
    display: none;
  }
  .tab-panel.active { display: block; }

  /* Log panel */
  #log-panel {
    background: var(--bg);
    font-family: var(--mono);
    font-size: .78rem;
    line-height: 1.7;
  }
  .log-line { display: flex; gap: .8rem; }
  .log-time { color: var(--border); min-width: 5rem; }
  .log-msg  { flex: 1; word-break: break-word; }
  .log-msg.info  { color: var(--text); }
  .log-msg.ok    { color: var(--accent2); }
  .log-msg.warn  { color: var(--warn); }
  .log-msg.error { color: var(--danger); }
  .log-msg.head  { color: var(--accent); font-weight: 500; }
  .log-msg.dim   { color: var(--muted); }
  .log-empty { color: var(--muted); text-align: center; margin-top: 3rem; font-size: .85rem; }

  /* Results panel */
  #results-panel { background: var(--bg); }
  .results-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: .8rem;
    margin-bottom: 1.6rem;
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .9rem 1rem;
    text-align: center;
  }
  .stat-card .val {
    font-family: var(--serif);
    font-size: 1.8rem;
    font-weight: 600;
    color: var(--accent);
    line-height: 1;
    margin-bottom: .3rem;
  }
  .stat-card .lbl {
    font-size: .72rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .06em;
    font-family: var(--mono);
  }

  .section-title {
    font-family: var(--serif);
    font-weight: 300;
    font-size: 1.1rem;
    color: var(--text);
    margin: 1.4rem 0 .8rem;
    padding-bottom: .4rem;
    border-bottom: 1px solid var(--border);
  }

  /* Figures grid */
  .figures-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
  }
  .fig-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    transition: border-color .15s, transform .15s;
  }
  .fig-card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .fig-card img { width: 100%; display: block; }
  .fig-card .fig-label {
    padding: .5rem .8rem;
    font-size: .75rem;
    color: var(--muted);
    font-family: var(--mono);
    border-top: 1px solid var(--border);
  }

  /* Downloads */
  .downloads-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: .6rem;
  }
  .dl-btn {
    display: flex;
    align-items: center;
    gap: .6rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: .65rem .9rem;
    color: var(--text);
    text-decoration: none;
    font-size: .8rem;
    font-family: var(--mono);
    transition: all .15s;
    cursor: pointer;
  }
  .dl-btn:hover { border-color: var(--accent2); color: var(--accent2); }
  .dl-btn .icon { font-size: 1.1rem; }
  .dl-btn .size { font-size: .68rem; color: var(--muted); margin-left: auto; }

  /* Lightbox */
  #lightbox {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.85);
    z-index: 999;
    align-items: center;
    justify-content: center;
  }
  #lightbox.open { display: flex; }
  #lightbox img {
    max-width: 92vw;
    max-height: 92vh;
    border-radius: 6px;
    box-shadow: 0 20px 60px rgba(0,0,0,.6);
  }
  #lightbox-close {
    position: fixed;
    top: 1rem; right: 1.5rem;
    font-size: 1.8rem;
    color: #fff;
    cursor: pointer;
    opacity: .7;
    transition: opacity .15s;
  }
  #lightbox-close:hover { opacity: 1; }

  /* Status bar */
  .statusbar {
    border-top: 1px solid var(--border);
    padding: .4rem 1.5rem;
    font-size: .73rem;
    font-family: var(--mono);
    color: var(--muted);
    background: var(--surface);
    display: flex;
    gap: 1.5rem;
  }
  .statusbar span { display: flex; align-items: center; gap: .4rem; }
  .statusbar .ok   { color: var(--accent2); }
  .statusbar .warn { color: var(--warn); }

  /* Source mode tabs */
  .source-tabs {
    display: flex;
    gap: 0;
    border: 1px solid var(--border);
    border-radius: 7px;
    overflow: hidden;
    margin-bottom: .1rem;
  }
  .src-tab {
    flex: 1;
    background: var(--surface);
    border: none;
    color: var(--muted);
    font-size: .75rem;
    font-family: var(--mono);
    padding: .45rem .3rem;
    cursor: pointer;
    transition: all .15s;
    border-right: 1px solid var(--border);
  }
  .src-tab:last-child { border-right: none; }
  .src-tab:hover { color: var(--text); background: var(--card); }
  .src-tab.active { background: #1a2a4a; color: var(--accent); font-weight: 500; }

  /* Textarea override */
  .field textarea {
    min-height: 110px;
    line-height: 1.5;
  }

  /* Action buttons (inline, smaller) */
  .action-btn {
    flex: 1;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: .4rem .6rem;
    font-size: .78rem;
    font-family: var(--sans);
    cursor: pointer;
    transition: background .15s;
    white-space: nowrap;
  }
  .action-btn:hover { background: #6fa3fa; }
  .action-btn:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
  .action-btn.secondary {
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--text);
  }
  .action-btn.secondary:hover { border-color: var(--accent2); color: var(--accent2); }

  /* Query count result pill */
  .count-pill {
    display: inline-flex;
    align-items: center;
    gap: .5rem;
    padding: .4rem .8rem;
    border-radius: 20px;
    font-size: .78rem;
    font-family: var(--mono);
    margin-top: .2rem;
  }
  .count-pill.ok    { background: #0d1f18; border: 1px solid #1d4035; color: var(--accent2); }
  .count-pill.warn  { background: #1f1a08; border: 1px solid #3f3010; color: var(--warn); }
  .count-pill.error { background: #1f0d0d; border: 1px solid #3f1010; color: var(--danger); }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  /* Empty state */
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 60%;
    gap: .8rem;
    color: var(--muted);
  }
  .empty .big { font-size: 3rem; opacity: .3; }
  .empty p { font-size: .85rem; text-align: center; line-height: 1.6; }
</style>
</head>
<body>

<header>
  <h1>CXL <span>Bibliometrics</span></h1>
  <span class="sub">PubMed · CrossRef · VOSviewer-style</span>
  <span class="status-dot" id="status-dot"></span>
</header>

<main>
<!-- ── Sidebar ────────────────────────────────────────────── -->
<aside>

  <div class="card">
    <h3>📅 Date Range</h3>

    <div class="presets" id="presets">
      <button class="preset-btn" data-start="2001" data-end="2025">All (2001–2025)</button>
      <button class="preset-btn" data-start="2016" data-end="2025">Last 10 yr</button>
      <button class="preset-btn" data-start="2021" data-end="2025">Last 5 yr</button>
      <button class="preset-btn" data-start="2023" data-end="2025">Last 3 yr</button>
      <button class="preset-btn" data-start="2001" data-end="2010">2001–2010</button>
      <button class="preset-btn" data-start="2011" data-end="2020">2011–2020</button>
    </div>

    <div style="margin-top:1rem;">
      <div class="year-row">
        <label>From</label>
        <input type="range" id="start-year" min="2001" max="2025" value="2001">
        <span class="year-display" id="start-display">2001</span>
      </div>
      <div class="year-row">
        <label>To</label>
        <input type="range" id="end-year" min="2001" max="2025" value="2025">
        <span class="year-display" id="end-display">2025</span>
      </div>
      <div class="year-range-summary" id="range-summary">
        2001 – 2025 &nbsp;·&nbsp; 25 years
      </div>
    </div>
  </div>

  <div class="card">
    <h3>⚙️ Data Source</h3>

    <!-- Source mode selector -->
    <div class="source-tabs" id="source-tabs">
      <button class="src-tab active" data-mode="pmid"  onclick="setSourceMode('pmid')">PMID File</button>
      <button class="src-tab"        data-mode="query" onclick="setSourceMode('query')">PubMed Query</button>
      <button class="src-tab"        data-mode="cache" onclick="setSourceMode('cache')">Cache Only</button>
    </div>

    <!-- PMID file panel -->
    <div class="src-panel" id="src-pmid">
      <div class="field" style="margin-top:.8rem;margin-bottom:.5rem">
        <label>PMID list file</label>
        <input type="text" id="pmid-file" value="pmids_expanded.txt" placeholder="path/to/pmids.txt">
        <div class="hint">One PMID per line. Date-range filter applied after load.</div>
      </div>
    </div>

    <!-- PubMed query panel -->
    <div class="src-panel" id="src-query" style="display:none">
      <div class="field" style="margin-top:.8rem;margin-bottom:.4rem">
        <label>PubMed search query</label>
        <textarea id="pubmed-query" rows="6"
          placeholder="e.g. &quot;corneal cross-linking&quot;[tiab] AND &quot;keratoconus&quot;[tiab]&#10;&#10;Paste any PubMed query here — the date range sliders above will be appended automatically."
          oninput="onQueryInput()"
        ></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.3rem">
          <div class="hint" id="query-hint">Paste a query from PubMed Advanced Search.</div>
          <span id="query-char-count" style="font-family:var(--mono);font-size:.68rem;color:var(--muted)">0 chars</span>
        </div>
      </div>
      <div style="display:flex;gap:.5rem;margin-bottom:.5rem">
        <button class="action-btn" onclick="validateQuery()" id="validate-btn">
          🔍 Count results
        </button>
        <button class="action-btn secondary" onclick="loadExampleQuery()">
          ↙ CXL example
        </button>
      </div>
      <div id="query-count-result" style="display:none"></div>
    </div>

    <!-- Cache only panel -->
    <div class="src-panel" id="src-cache" style="display:none">
      <div style="margin-top:.8rem;padding:.7rem;background:var(--surface);border-radius:6px;border:1px solid var(--border)">
        <div id="cache-info" style="font-size:.8rem;font-family:var(--mono);color:var(--muted)">
          Checking cache…
        </div>
      </div>
      <div class="hint" style="margin-top:.5rem">Re-runs analysis and charts on already-downloaded records. Fastest option.</div>
    </div>

    <!-- API key always visible -->
    <div class="field" style="margin-top:.9rem;margin-bottom:0">
      <label>NCBI API key</label>
      <input type="password" id="api-key" placeholder="Paste your key (optional)">
      <div class="hint">10 req/s with key vs 3 without. Free at ncbi.nlm.nih.gov/account</div>
    </div>
  </div>

  <div class="card">
    <h3>🔬 Options</h3>

    <div class="toggle-row">
      <div>
        <span>Fetch citation counts</span><br>
        <span class="hint-inline">CrossRef API (~20 min)</span>
      </div>
      <label class="toggle">
        <input type="checkbox" id="fetch-citations">
        <span class="toggle-slider"></span>
      </label>
    </div>

    <div class="toggle-row">
      <div>
        <span>Use cached records</span><br>
        <span class="hint-inline">Skip re-downloading</span>
      </div>
      <label class="toggle">
        <input type="checkbox" id="use-cache" checked>
        <span class="toggle-slider"></span>
      </label>
    </div>

    <div class="toggle-row">
      <div>
        <span>Force full refresh</span><br>
        <span class="hint-inline">Re-download everything</span>
      </div>
      <label class="toggle">
        <input type="checkbox" id="force-refresh">
        <span class="toggle-slider"></span>
      </label>
    </div>

    <div style="margin-top:.8rem; border-top: 1px solid var(--border); padding-top:.8rem;">
      <div class="field" style="margin-bottom:.5rem">
        <label>Min author publications</label>
        <input type="number" id="min-author-pubs" value="3" min="1" max="50"
               style="width:70px; text-align:center;">
      </div>
      <div class="field" style="margin-bottom:0">
        <label>Top N authors/countries/journals</label>
        <input type="number" id="top-n" value="20" min="5" max="100"
               style="width:70px; text-align:center;">
      </div>
    </div>
  </div>

  <button id="run-btn" onclick="runPipeline()">▶ Run Analysis</button>

</aside>

<!-- ── Main panel ─────────────────────────────────────────── -->
<div class="main-panel">

  <div class="progress-bar-wrap">
    <div class="progress-bar" id="progress-bar"></div>
  </div>

  <div style="display:grid; grid-template-rows: auto 1fr; overflow:hidden; height:100%;">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('log')">
        Console <span class="badge" id="log-badge">0</span>
      </div>
      <div class="tab" onclick="switchTab('results')">
        Results <span class="badge" id="results-badge">–</span>
      </div>
      <div class="tab" onclick="switchTab('figures')">
        Figures <span class="badge" id="fig-badge">0</span>
      </div>
      <div class="tab" onclick="switchTab('downloads')">
        Downloads <span class="badge" id="dl-badge">0</span>
      </div>
    </div>

    <div class="tab-panels" style="position:relative; overflow:hidden;">

      <div class="tab-panel active" id="log-panel">
        <div class="log-empty" id="log-empty">
          Configure settings and click <strong>Run Analysis</strong> to begin.
        </div>
      </div>

      <div class="tab-panel" id="results-panel">
        <div class="empty" id="results-empty">
          <div class="big">📊</div>
          <p>Results will appear here after a successful run.<br>
          Summary statistics, top authors, journals, and countries.</p>
        </div>
      </div>

      <div class="tab-panel" id="figures-panel">
        <div class="empty" id="figures-empty">
          <div class="big">📈</div>
          <p>Charts will appear here after a successful run.</p>
        </div>
        <div class="figures-grid" id="figures-grid" style="display:none"></div>
      </div>

      <div class="tab-panel" id="downloads-panel">
        <div class="empty" id="downloads-empty">
          <div class="big">⬇️</div>
          <p>Download links will appear here after a successful run.</p>
        </div>
        <div id="downloads-grid" style="display:none"></div>
      </div>

    </div>
  </div>

  <div class="statusbar">
    <span id="sb-records">Records: —</span>
    <span id="sb-cache">Cache: checking…</span>
    <span id="sb-output" id="sb-output">Output: loading…</span>
  </div>
</div>
</main>

<!-- Lightbox -->
<div id="lightbox" onclick="closeLightbox()">
  <span id="lightbox-close" onclick="closeLightbox()">✕</span>
  <img id="lightbox-img" src="" alt="">
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let logCount = 0;
let pollTimer = null;
let running   = false;

// ── Year range controls ────────────────────────────────────────────────────
const startSlider = document.getElementById('start-year');
const endSlider   = document.getElementById('end-year');
const startDisp   = document.getElementById('start-display');
const endDisp     = document.getElementById('end-display');
const rangeSumm   = document.getElementById('range-summary');

function updateRangeSummary() {
  const s = parseInt(startSlider.value);
  const e = parseInt(endSlider.value);
  if (s > e) { startSlider.value = e; return updateRangeSummary(); }
  startDisp.textContent = s;
  endDisp.textContent   = e;
  const yrs = e - s + 1;
  rangeSumm.textContent = `${s} – ${e}  ·  ${yrs} year${yrs>1?'s':''}`;
  // Deactivate presets that no longer match
  document.querySelectorAll('.preset-btn').forEach(b => {
    b.classList.toggle('active',
      parseInt(b.dataset.start) === s && parseInt(b.dataset.end) === e);
  });
}

startSlider.addEventListener('input', updateRangeSummary);
endSlider.addEventListener('input',   updateRangeSummary);

document.getElementById('presets').addEventListener('click', e => {
  const btn = e.target.closest('.preset-btn');
  if (!btn) return;
  startSlider.value = btn.dataset.start;
  endSlider.value   = btn.dataset.end;
  updateRangeSummary();
});

// Prevent start > end
startSlider.addEventListener('input', () => {
  if (parseInt(startSlider.value) > parseInt(endSlider.value))
    endSlider.value = startSlider.value;
});

// ── Tabs ───────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    const names = ['log','results','figures','downloads'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === name + '-panel');
  });
}

// ── Logging ────────────────────────────────────────────────────────────────
function addLog(msg, cls='info') {
  const panel = document.getElementById('log-panel');
  const empty = document.getElementById('log-empty');
  if (empty) empty.remove();

  const now  = new Date();
  const time = now.toTimeString().slice(0,8);
  const line = document.createElement('div');
  line.className = 'log-line';

  // Detect message type
  if (!cls || cls === 'info') {
    if (msg.startsWith('===') || msg.startsWith('CXL'))         cls = 'head';
    else if (msg.includes('saved') || msg.includes('Done') ||
             msg.includes('complete') || msg.includes('COMPLETE')) cls = 'ok';
    else if (msg.includes('[warn]') || msg.includes('warn'))    cls = 'warn';
    else if (msg.includes('[error]') || msg.includes('ERROR') ||
             msg.includes('Traceback') || msg.includes('Exception')) cls = 'error';
    else if (msg.startsWith('  ') || msg.startsWith('\t'))      cls = 'dim';
  }

  line.innerHTML = `<span class="log-time">${time}</span>
                    <span class="log-msg ${cls}">${escHtml(msg)}</span>`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;

  logCount++;
  document.getElementById('log-badge').textContent = logCount;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Run pipeline ───────────────────────────────────────────────────────────
async function runPipeline() {
  if (running) {
    await fetch('/api/stop', {method:'POST'});
    return;
  }

  const mode = document.querySelector('.src-tab.active')?.dataset.mode || 'pmid';
  const cfg = {
    start_year:       parseInt(startSlider.value),
    end_year:         parseInt(endSlider.value),
    source_mode:      mode,
    pmid_file:        mode === 'pmid'  ? document.getElementById('pmid-file').value.trim() : '',
    pubmed_query:     mode === 'query' ? document.getElementById('pubmed-query').value.trim() : '',
    api_key:          document.getElementById('api-key').value.trim(),
    fetch_citations:  document.getElementById('fetch-citations').checked,
    use_cache:        mode === 'cache' || document.getElementById('use-cache').checked,
    force_refresh:    mode !== 'cache' && document.getElementById('force-refresh').checked,
    min_author_pubs:  parseInt(document.getElementById('min-author-pubs').value) || 3,
    top_n:            parseInt(document.getElementById('top-n').value) || 20,
  };

  // Validate query mode has content
  if (mode === 'query' && !cfg.pubmed_query) {
    addLog('Please enter a PubMed query before running.', 'warn');
    switchTab('log');
    setRunning(false);
    return;
  }

  // Reset UI
  logCount = 0;
  document.getElementById('log-panel').innerHTML = '';
  document.getElementById('log-badge').textContent = '0';
  document.getElementById('results-badge').textContent = '–';
  document.getElementById('fig-badge').textContent = '0';
  document.getElementById('dl-badge').textContent = '0';
  document.getElementById('figures-grid').style.display = 'none';
  document.getElementById('figures-empty').style.display = '';
  document.getElementById('downloads-grid').style.display = 'none';
  document.getElementById('downloads-empty').style.display = '';
  document.getElementById('results-empty').style.display = '';

  switchTab('log');
  setRunning(true);
  addLog('Starting analysis pipeline…', 'head');
  addLog(`Date range: ${cfg.start_year} – ${cfg.end_year}`, 'dim');
  if (cfg.source_mode === 'pmid' && cfg.pmid_file)
    addLog(`PMID file: ${cfg.pmid_file}`, 'dim');
  else if (cfg.source_mode === 'query')
    addLog(`Query: ${cfg.pubmed_query.slice(0,80)}${cfg.pubmed_query.length>80?'…':''}`, 'dim');
  else if (cfg.source_mode === 'cache')
    addLog('Using cached records only (no new fetch)', 'dim');

  const resp = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(cfg)
  });

  if (!resp.ok) {
    addLog('Failed to start pipeline: ' + await resp.text(), 'error');
    setRunning(false);
    return;
  }

  startPolling();
}

function setRunning(state) {
  running = state;
  const btn = document.getElementById('run-btn');
  const dot = document.getElementById('status-dot');
  const bar = document.getElementById('progress-bar');
  btn.disabled  = false;
  btn.textContent = state ? '■ Stop' : '▶ Run Analysis';
  btn.className   = state ? 'running' : '';
  dot.className   = 'status-dot' + (state ? ' running' : '');
  bar.className   = 'progress-bar' + (state ? ' indeterminate' : '');
  if (!state) bar.style.width = '0%';
}

// ── Poll for log lines ─────────────────────────────────────────────────────
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollLogs, 300);
}

async function pollLogs() {
  try {
    const r = await fetch('/api/logs');
    const d = await r.json();
    d.lines.forEach(l => addLog(l));
    if (d.done) {
      clearInterval(pollTimer);
      setRunning(false);
      const dot = document.getElementById('status-dot');
      if (d.error) {
        dot.className = 'status-dot error';
        addLog('Pipeline finished with errors.', 'error');
      } else {
        dot.className = 'status-dot done';
        addLog('Pipeline complete ✓', 'ok');
        loadResults();
        loadFigures();
        loadDownloads();
        switchTab('results');
      }
    }
  } catch(e) { /* server restarting */ }
}

// ── Load results ───────────────────────────────────────────────────────────
async function loadResults() {
  try {
    const r = await fetch('/api/results');
    if (!r.ok) return;
    const d = await r.json();
    renderResults(d);
  } catch(e) {}
}

function renderResults(d) {
  document.getElementById('results-empty').style.display = 'none';
  const panel = document.getElementById('results-panel');

  // Stat cards
  const stats = [
    {val: d.n_records,                    lbl: 'Publications'},
    {val: d.authors?.length || '—',        lbl: 'Authors'},
    {val: d.journals?.length || '—',       lbl: 'Journals'},
    {val: (d.countries||[]).filter(c=>c.country!=='Unknown').length || '—', lbl: 'Countries'},
    {val: Object.keys(d.keywords?.freq||{}).length || '—', lbl: 'Keywords'},
    {val: d.temporal?.years?.[0]+'–'+d.temporal?.years?.slice(-1)[0] || '—', lbl: 'Year Range'},
  ];

  let html = '<div class="results-grid">';
  stats.forEach(s => {
    html += `<div class="stat-card">
      <div class="val">${s.val}</div>
      <div class="lbl">${s.lbl}</div>
    </div>`;
  });
  html += '</div>';
  document.getElementById('sb-records').textContent = `Records: ${d.n_records}`;
  document.getElementById('results-badge').textContent = d.n_records;

  // Top authors table
  if (d.authors?.length) {
    html += '<div class="section-title">Top Authors</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:.8rem;font-family:var(--mono)">';
    html += '<tr style="color:var(--muted);border-bottom:1px solid var(--border)">'
          + '<th style="text-align:left;padding:.4rem .6rem">#</th>'
          + '<th style="text-align:left;padding:.4rem .6rem">Author</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">Pubs</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">1st Author</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">Citations</th>'
          + '</tr>';
    d.authors.slice(0,20).forEach((a,i) => {
      const rowBg = i%2===0 ? '' : 'background:var(--card)';
      html += `<tr style="${rowBg}">
        <td style="padding:.35rem .6rem;color:var(--muted)">${i+1}</td>
        <td style="padding:.35rem .6rem;color:var(--accent)">${escHtml(a.author_id)}</td>
        <td style="padding:.35rem .6rem;text-align:right">${a.pub_count}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--muted)">${a.first_author_count}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--accent2)">${a.citation_total||0}</td>
      </tr>`;
    });
    html += '</table>';
  }

  // Top journals
  if (d.journals?.length) {
    html += '<div class="section-title">Top Journals</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:.8rem;font-family:var(--mono)">';
    html += '<tr style="color:var(--muted);border-bottom:1px solid var(--border)">'
          + '<th style="text-align:left;padding:.4rem .6rem">#</th>'
          + '<th style="text-align:left;padding:.4rem .6rem">Journal</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">Pubs</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">%</th>'
          + '</tr>';
    d.journals.slice(0,15).forEach((j,i) => {
      const rowBg = i%2===0 ? '' : 'background:var(--card)';
      html += `<tr style="${rowBg}">
        <td style="padding:.35rem .6rem;color:var(--muted)">${i+1}</td>
        <td style="padding:.35rem .6rem">${escHtml(j.abbr||j.journal)}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--accent)">${j.count}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--muted)">${j.percentage}%</td>
      </tr>`;
    });
    html += '</table>';
  }

  // Top countries
  if (d.countries?.length) {
    html += '<div class="section-title">Top Countries</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:.8rem;font-family:var(--mono)">';
    html += '<tr style="color:var(--muted);border-bottom:1px solid var(--border)">'
          + '<th style="text-align:left;padding:.4rem .6rem">#</th>'
          + '<th style="text-align:left;padding:.4rem .6rem">Country</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">Pubs</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">%</th>'
          + '<th style="text-align:right;padding:.4rem .6rem">Citations</th>'
          + '</tr>';
    d.countries.filter(c=>c.country!=='Unknown').slice(0,15).forEach((c,i) => {
      const rowBg = i%2===0 ? '' : 'background:var(--card)';
      html += `<tr style="${rowBg}">
        <td style="padding:.35rem .6rem;color:var(--muted)">${i+1}</td>
        <td style="padding:.35rem .6rem">${escHtml(c.country)}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--accent)">${c.count}</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--muted)">${c.percentage}%</td>
        <td style="padding:.35rem .6rem;text-align:right;color:var(--accent2)">${c.citations||0}</td>
      </tr>`;
    });
    html += '</table>';
  }

  // Inject
  const existing = panel.querySelector('.results-content');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.className = 'results-content';
  div.innerHTML = html;
  panel.appendChild(div);
}

// ── Load figures ───────────────────────────────────────────────────────────
async function loadFigures() {
  try {
    const r = await fetch('/api/figures');
    if (!r.ok) return;
    const d = await r.json();
    if (!d.figures?.length) return;

    document.getElementById('figures-empty').style.display = 'none';
    const grid = document.getElementById('figures-grid');
    grid.style.display = '';
    grid.innerHTML = '';

    d.figures.forEach(f => {
      const card = document.createElement('div');
      card.className = 'fig-card';
      card.innerHTML = `<img src="/api/figure?name=${encodeURIComponent(f.name)}&t=${Date.now()}"
                             alt="${f.label}" loading="lazy">
                        <div class="fig-label">${f.label}</div>`;
      card.querySelector('img').addEventListener('click', () => openLightbox('/api/figure?name=' + encodeURIComponent(f.name)));
      grid.appendChild(card);
    });

    document.getElementById('fig-badge').textContent = d.figures.length;
  } catch(e) {}
}

// ── Load downloads ─────────────────────────────────────────────────────────
async function loadDownloads() {
  try {
    const r = await fetch('/api/downloads');
    if (!r.ok) return;
    const d = await r.json();
    if (!d.files?.length) return;

    document.getElementById('downloads-empty').style.display = 'none';
    const grid = document.getElementById('downloads-grid');
    grid.style.display = '';

    const icons = {png:'🖼️', xlsx:'📊', csv:'📄', json:'📋', txt:'📝', md:'📝'};

    // Group by type
    const imgs  = d.files.filter(f => f.ext === 'png');
    const data  = d.files.filter(f => f.ext !== 'png');

    let html = '';
    if (data.length) {
      html += '<div class="section-title" style="margin-top:0">Data Files</div>';
      html += '<div class="downloads-grid">';
      data.forEach(f => {
        html += `<a class="dl-btn" href="/api/download?name=${encodeURIComponent(f.name)}" download="${f.name}">
          <span class="icon">${icons[f.ext]||'📄'}</span>
          <span>${f.name}</span>
          <span class="size">${f.size}</span>
        </a>`;
      });
      html += '</div>';
    }
    if (imgs.length) {
      html += '<div class="section-title">Figures</div>';
      html += '<div class="downloads-grid">';
      imgs.forEach(f => {
        html += `<a class="dl-btn" href="/api/download?name=${encodeURIComponent(f.name)}" download="${f.name}">
          <span class="icon">🖼️</span>
          <span>${f.name}</span>
          <span class="size">${f.size}</span>
        </a>`;
      });
      html += '</div>';
    }

    grid.innerHTML = html;
    document.getElementById('dl-badge').textContent = d.files.length;
  } catch(e) {}
}

// ── Lightbox ───────────────────────────────────────────────────────────────
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
}
document.addEventListener('keydown', e => { if(e.key==='Escape') closeLightbox(); });

// ── Cache status ───────────────────────────────────────────────────────────
async function checkCache() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const sb = document.getElementById('sb-cache');
    if (d.cached_records) {
      sb.innerHTML = `<span class="ok">✓ Cache: ${d.cached_records} records</span>`;
    } else {
      sb.innerHTML = `Cache: none`;
    }
    if (d.output_dir) {
      document.getElementById('sb-output').textContent = `Output: ${d.output_dir}`;
    }
  } catch(e) {}
}

// ── Source mode switching ──────────────────────────────────────────────────
let _sourceMode = 'pmid';

function setSourceMode(mode) {
  _sourceMode = mode;
  document.querySelectorAll('.src-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.mode === mode));
  document.querySelectorAll('.src-panel').forEach(p => p.style.display = 'none');
  document.getElementById('src-' + mode).style.display = '';

  // Auto-toggle "use-cache" toggle for UX clarity
  const useCache = document.getElementById('use-cache');
  if (mode === 'cache') {
    useCache.checked = true;
    useCache.disabled = true;
  } else {
    useCache.disabled = false;
  }

  if (mode === 'cache') refreshCacheInfo();
}

function refreshCacheInfo() {
  fetch('/api/status').then(r => r.json()).then(d => {
    const el = document.getElementById('cache-info');
    if (d.cached_records) {
      el.innerHTML = `<span style="color:var(--accent2)">✓ ${d.cached_records} records cached</span>`
                   + (d.cache_date ? `<br><span style="color:var(--muted);font-size:.7rem">Last fetched: ${d.cache_date}</span>` : '');
    } else {
      el.innerHTML = '<span style="color:var(--danger)">✗ No cache found — fetch records first using PMID File or PubMed Query mode.</span>';
    }
  });
}

// ── Query input / validation ────────────────────────────────────────────────
const CXL_EXAMPLE_QUERY = `("corneal cross-linking"[tiab] OR "corneal crosslinking"[tiab] OR "corneal collagen cross-linking"[tiab] OR "riboflavin ultraviolet"[tiab] OR "PACK-CXL"[tiab] OR "Corneal Cross-Linking"[MeSH Terms]) AND ("cornea"[tiab] OR "keratoconus"[tiab] OR "ectasia"[tiab] OR "keratitis"[tiab] OR "cornea"[MeSH Terms]) NOT ("cartilage"[tiab] OR "dental"[tiab] OR "bone"[tiab] OR "hydrogel"[tiab] OR "polymer"[tiab])`;

function loadExampleQuery() {
  document.getElementById('pubmed-query').value = CXL_EXAMPLE_QUERY;
  onQueryInput();
}

function onQueryInput() {
  const q = document.getElementById('pubmed-query').value;
  document.getElementById('query-char-count').textContent = q.length + ' chars';
  // Reset count result if query changed
  const res = document.getElementById('query-count-result');
  res.style.display = 'none';
}

let _validateTimer = null;
async function validateQuery() {
  const q = document.getElementById('pubmed-query').value.trim();
  if (!q) return;

  const btn = document.getElementById('validate-btn');
  const res = document.getElementById('query-count-result');
  const s   = parseInt(startSlider.value);
  const e   = parseInt(endSlider.value);
  const key = document.getElementById('api-key').value.trim();

  btn.disabled = true;
  btn.textContent = '⏳ Counting…';
  res.style.display = 'none';

  try {
    const resp = await fetch('/api/validate_query', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({query: q, start_year: s, end_year: e, api_key: key})
    });
    const d = await resp.json();

    let cls = 'ok', icon = '✓';
    if (d.error)        { cls = 'error'; icon = '✗'; }
    else if (d.count === 0) { cls = 'warn';  icon = '⚠'; }
    else if (d.count > 20000) { cls = 'warn'; icon = '⚠'; }

    const msg = d.error
      ? `Error: ${d.error}`
      : `${d.count.toLocaleString()} results for ${s}–${e}`;

    res.innerHTML = `<div class="count-pill ${cls}">${icon} ${msg}</div>`;
    if (!d.error && d.count > 20000)
      res.innerHTML += `<div class="hint" style="margin-top:.4rem;color:var(--warn)">Large result set — consider narrowing your query.</div>`;
    if (!d.error && d.count === 0)
      res.innerHTML += `<div class="hint" style="margin-top:.4rem;">No results — check your syntax at pubmed.ncbi.nlm.nih.gov</div>`;
    res.style.display = '';
  } catch(err) {
    res.innerHTML = `<div class="count-pill error">✗ Could not reach NCBI — check your internet connection.</div>`;
    res.style.display = '';
  }

  btn.disabled = false;
  btn.textContent = '🔍 Count results';
}

// ── Init ───────────────────────────────────────────────────────────────────
checkCache();
updateRangeSummary();
// Mark "All" preset as active by default
document.querySelector('.preset-btn[data-start="2001"]').classList.add('active');
</script>
</body>
</html>
"""

# ── HTTP Request Handler ───────────────────────────────────────────────────────

def _esearch_count(query: str, api_key: str = "") -> int:
    """Return total result count for a PubMed query via esearch."""
    import urllib.request, urllib.parse
    params = {
        "db":      "pubmed",
        "term":    query,
        "retmax":  "0",
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    return int(data["esearchresult"]["count"])


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if path == "/" or path == "/index.html":
            self._send(200, "text/html", HTML.encode())

        elif path == "/api/logs":
            lines = []
            try:
                while True:
                    lines.append(_log_queue.get_nowait())
            except queue.Empty:
                pass
            payload = json.dumps({
                "lines": lines,
                "done":  _run_state["done"],
                "error": _run_state["error"],
            }).encode()
            self._send(200, "application/json", payload)

        elif path == "/api/results":
            p = DATA_DIR / "analysis.json"
            if p.exists():
                self._send(200, "application/json", p.read_bytes())
            else:
                self._send(404, "text/plain", b"not ready")

        elif path == "/api/figures":
            figs = []
            labels = {
                "fig1_temporal_trends":  "Temporal Trends",
                "fig2_top_journals":     "Top Journals",
                "fig3_top_countries":    "Top Countries",
                "fig4_top_authors":      "Top Authors",
                "fig5_author_keywords":  "Author Keywords",
                "fig5_mesh_terms":       "MeSH Terms",
                "fig5b_mesh_terms":      "MeSH Terms",
                "fig6_pub_types":        "Publication Types",
                "fig7_country_collab":   "Country Collaboration",
                "fig8_keyword_trends":   "Keyword Trends",
                "fig9_institutions":     "Institutions",
                "fig10_author_network":  "Author Network",
            }
            for f in sorted(OUTPUT_DIR.glob("fig*.png")):
                stem = f.stem
                figs.append({"name": f.name, "label": labels.get(stem, stem)})
            self._send(200, "application/json", json.dumps({"figures": figs}).encode())

        elif path == "/api/figure":
            name = params.get("name", "")
            p = OUTPUT_DIR / name
            if p.exists() and p.suffix == ".png":
                self._send(200, "image/png", p.read_bytes())
            else:
                self._send(404, "text/plain", b"not found")

        elif path == "/api/downloads":
            files = []
            for f in sorted(OUTPUT_DIR.iterdir()):
                if f.suffix in (".png", ".csv", ".xlsx", ".json", ".md", ".txt"):
                    sz = f.stat().st_size
                    if sz > 1024*1024:
                        size_str = f"{sz/1024/1024:.1f} MB"
                    elif sz > 1024:
                        size_str = f"{sz/1024:.0f} KB"
                    else:
                        size_str = f"{sz} B"
                    files.append({"name": f.name, "ext": f.suffix.lstrip("."),
                                  "size": size_str})
            self._send(200, "application/json", json.dumps({"files": files}).encode())

        elif path == "/api/download":
            name = params.get("name", "")
            p = OUTPUT_DIR / name
            if p.exists():
                ct = {
                    ".png":  "image/png",
                    ".csv":  "text/csv",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".json": "application/json",
                    ".md":   "text/markdown",
                }.get(p.suffix, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
                self.send_header("Content-Length", str(p.stat().st_size))
                self.end_headers()
                self.wfile.write(p.read_bytes())
            else:
                self._send(404, "text/plain", b"not found")

        elif path == "/api/status":
            rec_cache = CACHE_DIR / "records.json"
            cached = 0
            cache_date = ""
            if rec_cache.exists():
                try:
                    data = json.loads(rec_cache.read_text())
                    cached = len(data)
                    import datetime
                    mtime = rec_cache.stat().st_mtime
                    cache_date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            self._send(200, "application/json",
                       json.dumps({"cached_records": cached,
                                   "cache_date": cache_date,
                                   "output_dir": str(OUTPUT_DIR)}).encode())

        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""

        if path == "/api/run":
            if _run_state["running"]:
                self._send(409, "text/plain", b"already running")
                return
            try:
                cfg = json.loads(body)
            except Exception:
                self._send(400, "text/plain", b"bad json")
                return
            threading.Thread(target=_run_pipeline, args=(cfg,), daemon=True).start()
            self._send(200, "application/json", b'{"ok":true}')

        elif path == "/api/stop":
            _run_state["done"]    = True
            _run_state["running"] = False
            _run_state["error"]   = True
            _log_queue.put("Run stopped by user.")
            self._send(200, "application/json", b'{"ok":true}')

        elif path == "/api/validate_query":
            # Run an esearch count for the given query + date range
            try:
                req_data = json.loads(body)
                q     = req_data.get("query", "").strip()
                sy    = int(req_data.get("start_year", 2001))
                ey    = int(req_data.get("end_year",   2025))
                akey  = req_data.get("api_key", "").strip()
                if not q:
                    self._send(200, "application/json",
                               json.dumps({"error": "Empty query"}).encode())
                    return
                # Build date-bounded query
                full_q = f'({q}) AND ("{sy}/01/01"[PDAT] : "{ey}/12/31"[PDAT])'
                count = _esearch_count(full_q, akey)
                self._send(200, "application/json",
                           json.dumps({"count": count, "query": full_q}).encode())
            except Exception as exc:
                self._send(200, "application/json",
                           json.dumps({"error": str(exc)}).encode())

        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ── Pipeline runner (runs in background thread) ────────────────────────────────

def _log(msg: str):
    _log_queue.put(msg)


def _run_pipeline(cfg: dict):
    global _last_config
    _last_config = cfg
    _run_state.update({"running": True, "done": False, "error": False})

    try:
        import importlib
        import sys
        sys.path.insert(0, str(HERE))

        # ── Patch config ──────────────────────────────────────────────────
        import config as conf
        conf.START_YEAR        = cfg["start_year"]
        conf.END_YEAR          = cfg["end_year"]
        conf.FETCH_CITATIONS   = cfg["fetch_citations"]
        conf.MIN_AUTHOR_PUBS   = cfg["min_author_pubs"]
        conf.TOP_N_AUTHORS     = cfg["top_n"]
        conf.TOP_N_COUNTRIES   = cfg["top_n"]
        conf.TOP_N_JOURNALS    = cfg["top_n"]
        conf.TOP_N_KEYWORDS    = 50
        if cfg.get("api_key"):
            conf.NCBI_API_KEY  = cfg["api_key"]

        # Patch the PUBMED_QUERY date range
        conf.PUBMED_QUERY = conf.PUBMED_QUERY.rsplit('AND (', 1)[0].rstrip() + \
            f' AND ("{cfg["start_year"]}/01/01"[PDAT] : "{cfg["end_year"]}/12/31"[PDAT])'

        # ── Step 1: Fetch / load ───────────────────────────────────────────
        mode       = cfg.get("source_mode", "pmid")
        cache_file = pathlib.Path(conf.CACHE_DIR) / "records.json"
        use_cache  = (mode == "cache") or (
                        cfg["use_cache"] and cache_file.exists() and not cfg["force_refresh"])

        _log(f"[1/6] Loading records ({cfg['start_year']}–{cfg['end_year']}) …")
        _log(f"  Source mode: {mode}")

        import json as _json

        if use_cache and mode != "query":
            # Use cached records (skip network entirely)
            if not cache_file.exists():
                _log("  ERROR: No cache found. Switch to PMID File or PubMed Query mode first.")
                raise FileNotFoundError("No cached records")
            _log(f"  Loading from cache …")
            with open(cache_file) as f:
                records = _json.load(f)
            _log(f"  Loaded {len(records)} cached records")

        elif mode == "pmid":
            pmid_file = cfg.get("pmid_file", "").strip()
            if not pmid_file:
                _log("  ERROR: No PMID file specified.")
                raise ValueError("No PMID file")
            pf = pathlib.Path(pmid_file)
            if not pf.is_absolute():
                pf = HERE / pf
            if not pf.exists():
                _log(f"  ERROR: PMID file not found: {pf}")
                raise FileNotFoundError(str(pf))
            importlib.invalidate_caches()
            import fetch as fetch_mod
            importlib.reload(fetch_mod)
            records = fetch_mod.run_fetch_from_pmids(
                str(pf), api_key=conf.NCBI_API_KEY, force_refresh=True)

        elif mode == "query":
            raw_query = cfg.get("pubmed_query", "").strip()
            if not raw_query:
                _log("  ERROR: No PubMed query provided.")
                raise ValueError("Empty query")
            # Build date-bounded full query and set on config
            full_query = (f'({raw_query}) AND '
                          f'("{cfg["start_year"]}/01/01"[PDAT] : "{cfg["end_year"]}/12/31"[PDAT])')
            conf.PUBMED_QUERY = full_query
            _log(f"  Query: {raw_query[:100]}{'…' if len(raw_query)>100 else ''}")
            import fetch as fetch_mod
            importlib.reload(fetch_mod)
            records = fetch_mod.run_fetch(
                api_key=conf.NCBI_API_KEY, force_refresh=True)

        else:
            _log(f"  ERROR: Unknown source mode: {mode}")
            raise ValueError(f"Unknown mode: {mode}")

        # Filter to selected date range
        _log(f"  Filtering to {cfg['start_year']}–{cfg['end_year']} …")
        before = len(records)
        records = [r for r in records
                   if cfg["start_year"] <= int(r.get("year") or 0) <= cfg["end_year"]]
        _log(f"  {len(records)} records in range (dropped {before - len(records)})")

        if not records:
            _log("  ERROR: No records in selected date range.")
            raise ValueError("No records in range")

        # ── Step 2: Author disambiguation ─────────────────────────────────
        _log("[2/6] Disambiguating authors …")
        import disambiguate as da
        importlib.reload(da)
        records, _ = da.assign_author_ids(records)

        # ── Step 3: Country enrichment ────────────────────────────────────
        _log("[3/6] Extracting countries from affiliations …")
        import geo
        importlib.reload(geo)
        records = geo.enrich_countries(records)

        # ── Step 4: Citations ─────────────────────────────────────────────
        if cfg["fetch_citations"]:
            _log("[4/6] Fetching citation counts from CrossRef …")
            import citations as cit
            importlib.reload(cit)
            records = cit.enrich_citations(records)
        else:
            _log("[4/6] Citation fetch skipped.")

        # ── Step 5: Analyse ───────────────────────────────────────────────
        _log("[5/6] Running bibliometric analysis …")
        import analyze as an
        importlib.reload(an)
        results = an.run_analysis(records)

        import json as _json
        pathlib.Path(conf.DATA_DIR).mkdir(parents=True, exist_ok=True)
        with open(pathlib.Path(conf.DATA_DIR) / "analysis.json", "w") as f:
            _json.dump(results, f, indent=2, default=str)

        _log(f"  {results['n_records']} records · "
             f"{len(results['authors'])} authors · "
             f"{len(results['journals'])} journals · "
             f"{len(results['countries'])} countries")

        # ── Step 6: Visualise + report ────────────────────────────────────
        _log("[6/6] Generating figures and reports …")
        import visualize as viz
        importlib.reload(viz)
        viz.run_visualizations(results, records)

        import report as rep
        importlib.reload(rep)
        rep.generate_reports(results)

        _log("=" * 50)
        _log("PIPELINE COMPLETE ✓")
        _log(f"  Publications : {results['n_records']}")
        _log(f"  Authors      : {len(results['authors'])}")
        _log(f"  Journals     : {len(results['journals'])}")
        _log(f"  Countries    : {len([c for c in results['countries'] if c['country']!='Unknown'])}")
        _log(f"  Outputs in   : {conf.OUTPUT_DIR}")
        _run_state.update({"running": False, "done": True, "error": False})

    except Exception as exc:
        import traceback
        _log(f"ERROR: {exc}")
        for line in traceback.format_exc().splitlines():
            _log(line)
        _run_state.update({"running": False, "done": True, "error": True})


# ── Server launch ─────────────────────────────────────────────────────────────

def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url    = f"http://localhost:{PORT}"

    print(f"""
╔══════════════════════════════════════════════════╗
║     CXL Bibliometrics — Local Web GUI            ║
╠══════════════════════════════════════════════════╣
║  Server: {url:<40}║
║  Press Ctrl+C to quit                            ║
╚══════════════════════════════════════════════════╝
""")

    # Open browser after short delay
    def _open():
        time.sleep(0.8)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
