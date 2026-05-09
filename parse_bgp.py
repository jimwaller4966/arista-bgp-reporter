#!/usr/bin/env python3
"""
parse_bgp.py — Parse 'show ip bgp detail vrf all' output and render an HTML report.
Usage:
    python3 parse_bgp.py                  # scans output/ for bgp files
    python3 parse_bgp.py -i output/       # explicit input directory
    python3 parse_bgp.py -o report.html   # custom output filename
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from parsers import bgp_detail as PARSER
except ImportError:
    print("ERROR: Cannot find parsers/bgp_detail.py")
    sys.exit(1)

OUTPUT_DIR     = "output"
DEFAULT_OUTPUT = "bgp_report.html"

# ── File loading ──────────────────────────────────────────────────────────────
def load_files(input_dir):
    records = []
    p = Path(input_dir)
    if not p.exists():
        print(f"ERROR: Input directory '{input_dir}' not found.")
        sys.exit(1)
    found = []
    for slug in PARSER.COMMAND_SLUGS:
        found.extend(sorted(p.glob(f"*_{slug}.txt")))
    if not found:
        slugs = ", ".join(f"*_{s}.txt" for s in PARSER.COMMAND_SLUGS)
        print(f"No matching files found in {input_dir}/")
        print(f"Expected filenames matching: {slugs}")
        sys.exit(1)
    for f in found:
        host = f.name.split("_")[0]
        raw  = f.read_text(encoding="utf-8", errors="replace")
        recs = PARSER.parse(host, raw)
        vrfs = sorted(set(r["vrf"] for r in recs))
        print(f"  Parsed {host}: {len(recs)} paths across VRFs: {vrfs}")
        records.extend(recs)
    return records

# ── HTML report ───────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BGP Route Detail Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Syne:wght@400;600;800&display=swap');

  :root {
    --bg:        #0a0e14;
    --bg2:       #0f1520;
    --bg3:       #141c2e;
    --border:    #1e2d4a;
    --accent:    #00d4ff;
    --accent2:   #7c3aed;
    --accent3:   #10b981;
    --warn:      #f59e0b;
    --danger:    #ef4444;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --best:      #10b981;
    --tag-bg:    #1a2640;
    --tag-text:  #7dd3fc;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    min-height: 100vh;
  }

  /* ── Header ── */
  header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 20px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
  }

  .header-left h1 {
    font-family: 'Syne', sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.5px;
  }

  .header-left .cmd-badge {
    display: inline-block;
    margin-top: 4px;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
  }

  .header-right {
    color: var(--muted);
    font-size: 11px;
    text-align: right;
  }

  /* ── Stats bar ── */
  .stats {
    display: flex;
    gap: 0;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 0 28px;
    flex-wrap: wrap;
  }

  .stat {
    padding: 14px 24px 14px 0;
    margin-right: 24px;
    border-right: 1px solid var(--border);
  }
  .stat:last-child { border-right: none; }

  .stat-val {
    font-family: 'Syne', sans-serif;
    font-size: 26px;
    font-weight: 800;
    line-height: 1;
    color: var(--accent);
  }
  .stat-val.green  { color: var(--accent3); }
  .stat-val.purple { color: var(--accent2); }
  .stat-val.amber  { color: var(--warn); }

  .stat-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
  }

  /* ── Filters ── */
  .filters {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 12px 28px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
  }

  .filters input, .filters select {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 4px;
    outline: none;
    transition: border-color 0.15s;
  }
  .filters input:focus, .filters select:focus {
    border-color: var(--accent);
  }
  .filters input::placeholder { color: var(--muted); }

  .filter-label {
    color: var(--muted);
    font-size: 11px;
    white-space: nowrap;
  }

  .community-search {
    flex: 1;
    min-width: 200px;
  }

  .btn-reset {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-reset:hover { border-color: var(--accent); color: var(--accent); }

  .row-count {
    margin-left: auto;
    color: var(--muted);
    font-size: 11px;
    white-space: nowrap;
  }

  /* ── Table ── */
  .table-wrap {
    overflow-x: auto;
    padding: 0 28px 28px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 16px;
    font-size: 12px;
  }

  thead th {
    background: var(--bg3);
    color: var(--muted);
    font-size: 10px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 10px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }
  thead th:hover { color: var(--accent); }
  thead th.sorted { color: var(--accent); }

  tbody tr {
    border-bottom: 1px solid var(--border);
    transition: background 0.1s;
  }
  tbody tr:hover { background: var(--bg3); }
  tbody tr.best-path { background: rgba(16,185,129,0.04); }
  tbody tr.best-path:hover { background: rgba(16,185,129,0.09); }

  td {
    padding: 7px 10px;
    color: var(--text);
    white-space: nowrap;
    vertical-align: middle;
  }

  td.prefix  { color: var(--accent); font-weight: 500; }
  td.as-path { color: #94a3b8; }
  td.nexthop { color: #cbd5e1; }

  .badge-vrf {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .vrf-default { background: #1e3a5f; color: #7dd3fc; }
  .vrf-PROD    { background: #2d1b4e; color: #c4b5fd; }
  .vrf-MGMT    { background: #1a3a2a; color: #6ee7b7; }
  .vrf-other   { background: #2a2a1a; color: #fde68a; }

  .check { color: var(--best); font-weight: 700; }

  .communities {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  .community-tag {
    display: inline-block;
    background: var(--tag-bg);
    color: var(--tag-text);
    border: 1px solid #1e3a5f;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    white-space: nowrap;
  }
  .community-tag.highlight {
    background: #1a3a20;
    color: #6ee7b7;
    border-color: #2d6a40;
  }
  .no-community { color: var(--muted); font-size: 11px; }

  .hidden { display: none !important; }
</style>
</head>
<body>

<header>
  <div class="header-left">
    <h1>BGP Route Detail</h1>
    <span class="cmd-badge">show ip bgp detail vrf all</span>
  </div>
  <div class="header-right">
    Generated __GENERATED__<br>
    __DEVICE_COUNT__ devices &nbsp;·&nbsp; __VRF_COUNT__ VRFs
  </div>
</header>

<div class="stats">
  <div class="stat">
    <div class="stat-val">__TOTAL_PATHS__</div>
    <div class="stat-label">Total Paths</div>
  </div>
  <div class="stat">
    <div class="stat-val green">__TOTAL_PREFIXES__</div>
    <div class="stat-label">Unique Prefixes</div>
  </div>
  <div class="stat">
    <div class="stat-val purple">__PATHS_WITH_COMMUNITIES__</div>
    <div class="stat-label">Paths w/ Communities</div>
  </div>
  <div class="stat">
    <div class="stat-val amber">__UNIQUE_COMMUNITIES__</div>
    <div class="stat-label">Unique Communities</div>
  </div>
  <div class="stat">
    <div class="stat-val">__BEST_PATHS__</div>
    <div class="stat-label">Best Paths</div>
  </div>
</div>

<div class="filters">
  <span class="filter-label">Device</span>
  <select id="f-device"><option value="">All</option></select>

  <span class="filter-label">VRF</span>
  <select id="f-vrf"><option value="">All</option></select>

  <span class="filter-label">Prefix</span>
  <input id="f-prefix" type="text" placeholder="e.g. 10.10" style="width:130px">

  <span class="filter-label">AS Path</span>
  <input id="f-aspath" type="text" placeholder="e.g. 65002" style="width:110px">

  <span class="filter-label">Community (regex)</span>
  <input id="f-community" type="text" placeholder="e.g. 65001:12200 or :10$" class="community-search">

  <label style="color:var(--muted);font-size:11px;display:flex;align-items:center;gap:5px;">
    <input type="checkbox" id="f-best"> Best only
  </label>
  <label style="color:var(--muted);font-size:11px;display:flex;align-items:center;gap:5px;">
    <input type="checkbox" id="f-has-community"> Has community
  </label>

  <button class="btn-reset" onclick="resetFilters()">Reset</button>
  <span class="row-count" id="row-count"></span>
</div>

<div class="table-wrap">
  <table id="main-table">
    <thead>
      <tr>
        <th onclick="sortTable(0)">Device</th>
        <th onclick="sortTable(1)">VRF</th>
        <th onclick="sortTable(2)">Prefix</th>
        <th onclick="sortTable(3)">Paths</th>
        <th onclick="sortTable(4)">AS Path</th>
        <th onclick="sortTable(5)">Next Hop</th>
        <th onclick="sortTable(6)">Origin</th>
        <th onclick="sortTable(7)">LP</th>
        <th onclick="sortTable(8)">Weight</th>
        <th onclick="sortTable(9)">Age</th>
        <th onclick="sortTable(10)">Best</th>
        <th onclick="sortTable(11)">Valid</th>
        <th onclick="sortTable(12)">Communities</th>
      </tr>
    </thead>
    <tbody id="table-body">
    </tbody>
  </table>
</div>

<script>
const RAW = __JSON_DATA__;

function vrfClass(vrf) {{
  if (vrf === 'default') return 'vrf-default';
  if (vrf === 'PROD')    return 'vrf-PROD';
  if (vrf === 'MGMT')    return 'vrf-MGMT';
  return 'vrf-other';
}}

function communityHTML(commStr, highlightRegex) {{
  if (!commStr) return '<span class="no-community">—</span>';
  const tags = commStr.trim().split(/\s+/);
  return '<div class="communities">' + tags.map(t => {{
    const cls = (highlightRegex && highlightRegex.test(t)) ? 'community-tag highlight' : 'community-tag';
    return `<span class="${{cls}}">${{t}}</span>`;
  }}).join('') + '</div>';
}}

function buildOptions(id, values) {{
  const sel = document.getElementById(id);
  const cur = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  values.forEach(v => {{
    const o = document.createElement('option');
    o.value = o.textContent = v;
    sel.appendChild(o);
  }});
  sel.value = cur;
}}

function applyFilters() {{
  const fDevice    = document.getElementById('f-device').value;
  const fVrf       = document.getElementById('f-vrf').value;
  const fPrefix    = document.getElementById('f-prefix').value.trim().toLowerCase();
  const fAspath    = document.getElementById('f-aspath').value.trim().toLowerCase();
  const fCommStr   = document.getElementById('f-community').value.trim();
  const fBest      = document.getElementById('f-best').checked;
  const fHasComm   = document.getElementById('f-has-community').checked;

  let commRegex = null;
  try {{ if (fCommStr) commRegex = new RegExp(fCommStr, 'i'); }} catch(e) {{}}

  const rows = document.querySelectorAll('#table-body tr');
  let visible = 0;

  rows.forEach(row => {{
    const d = row.dataset;
    let show = true;
    if (fDevice && d.device !== fDevice) show = false;
    if (fVrf    && d.vrf    !== fVrf)    show = false;
    if (fPrefix && !d.prefix.includes(fPrefix)) show = false;
    if (fAspath && !d.aspath.toLowerCase().includes(fAspath)) show = false;
    if (fBest   && d.best !== '1') show = false;
    if (fHasComm && !d.communities) show = false;
    if (commRegex && !commRegex.test(d.communities)) show = false;

    row.classList.toggle('hidden', !show);
    if (show) {{
      // Re-render communities with highlight
      const commCell = row.querySelector('.comm-cell');
      if (commCell) commCell.innerHTML = communityHTML(d.communities, commRegex);
      visible++;
    }}
  }});

  document.getElementById('row-count').textContent = `Showing ${{visible}} of ${{rows.length}} paths`;
}}

function resetFilters() {{
  ['f-device','f-vrf'].forEach(id => document.getElementById(id).value = '');
  ['f-prefix','f-aspath','f-community'].forEach(id => document.getElementById(id).value = '');
  ['f-best','f-has-community'].forEach(id => document.getElementById(id).checked = false);
  applyFilters();
}}

let sortCol = -1, sortAsc = true;
function sortTable(col) {{
  if (sortCol === col) sortAsc = !sortAsc; else {{ sortCol = col; sortAsc = true; }}
  document.querySelectorAll('thead th').forEach((th,i) => th.classList.toggle('sorted', i===col));
  const tbody = document.getElementById('table-body');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a,b) => {{
    const av = a.cells[col]?.textContent.trim() || '';
    const bv = b.cells[col]?.textContent.trim() || '';
    return sortAsc ? av.localeCompare(bv, undefined, {{numeric:true}}) : bv.localeCompare(av, undefined, {{numeric:true}});
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Init ──────────────────────────────────────────────────────────────────────
(function() {{
  const devices = [...new Set(RAW.map(r => r.host))].sort();
  const vrfs    = [...new Set(RAW.map(r => r.vrf))].sort();
  buildOptions('f-device', devices);
  buildOptions('f-vrf',    vrfs);

  const tbody = document.getElementById('table-body');
  RAW.forEach(r => {{
    const tr = document.createElement('tr');
    if (r.best === '✓') tr.classList.add('best-path');
    tr.dataset.device      = r.host;
    tr.dataset.vrf         = r.vrf;
    tr.dataset.prefix      = r.prefix.toLowerCase();
    tr.dataset.aspath      = r.as_path;
    tr.dataset.best        = r.best === '✓' ? '1' : '';
    tr.dataset.communities = r.communities || '';

    tr.innerHTML = `
      <td>${{r.host}}</td>
      <td><span class="badge-vrf ${{vrfClass(r.vrf)}}">${{r.vrf}}</span></td>
      <td class="prefix">${{r.prefix}}</td>
      <td style="color:var(--muted)">${{r.paths_available}}</td>
      <td class="as-path">${{r.as_path}}</td>
      <td class="nexthop">${{r.next_hop}}</td>
      <td>${{r.origin}}</td>
      <td>${{r.local_pref}}</td>
      <td>${{r.weight}}</td>
      <td style="color:var(--muted)">${{r.age}}</td>
      <td><span class="check">${{r.best}}</span></td>
      <td><span class="check">${{r.valid}}</span></td>
      <td class="comm-cell">${{communityHTML(r.communities, null)}}</td>
    `;
    tbody.appendChild(tr);
  }});

  ['f-device','f-vrf'].forEach(id => document.getElementById(id).addEventListener('change', applyFilters));
  ['f-prefix','f-aspath','f-community'].forEach(id => document.getElementById(id).addEventListener('input', applyFilters));
  ['f-best','f-has-community'].forEach(id => document.getElementById(id).addEventListener('change', applyFilters));

  applyFilters();
}})();
</script>
</body>
</html>
"""

def render_html(records, output_file):
    # Stats
    total_paths            = len(records)
    total_prefixes         = len(set((r["host"], r["vrf"], r["prefix"]) for r in records))
    paths_with_communities = sum(1 for r in records if r.get("communities"))
    all_communities        = []
    for r in records:
        if r.get("communities"):
            all_communities.extend(r["communities"].split())
    unique_communities = len(set(all_communities))
    best_paths         = sum(1 for r in records if r.get("best") == "✓")
    device_count       = len(set(r["host"] for r in records))
    vrf_count          = len(set(r["vrf"] for r in records))
    generated          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = HTML_TEMPLATE
    html = html.replace("__GENERATED__",              generated)
    html = html.replace("__DEVICE_COUNT__",           str(device_count))
    html = html.replace("__VRF_COUNT__",              str(vrf_count))
    html = html.replace("__TOTAL_PATHS__",            str(total_paths))
    html = html.replace("__TOTAL_PREFIXES__",         str(total_prefixes))
    html = html.replace("__PATHS_WITH_COMMUNITIES__", str(paths_with_communities))
    html = html.replace("__UNIQUE_COMMUNITIES__",     str(unique_communities))
    html = html.replace("__BEST_PATHS__",             str(best_paths))
    html = html.replace("__JSON_DATA__",              json.dumps(records, ensure_ascii=False))

    Path(output_file).write_text(html, encoding="utf-8")
    print(f"Report: {output_file}")
    print(f"Paths:  {total_paths} ({best_paths} best) across {vrf_count} VRF(s)")
    print(f"Communities: {paths_with_communities} paths tagged, {unique_communities} unique")


def main():
    parser = argparse.ArgumentParser(description="BGP Detail Report Generator")
    parser.add_argument("-i", "--input",  default=OUTPUT_DIR,    help="Input directory")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="Output HTML file")
    args = parser.parse_args()

    print(f"\nBGP Detail Parser")
    print("=" * 40)
    print(f"Input:  {args.input}/")
    print(f"Output: {args.output}")
    print()

    records = load_files(args.input)
    if not records:
        print("No BGP path records parsed.")
        sys.exit(1)

    render_html(records, args.output)


if __name__ == "__main__":
    main()
