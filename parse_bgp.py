#!/usr/bin/env python3
"""
parse_bgp.py — Parse collected 'show ip bgp [vrf all] detail' files and render an HTML report.

Usage:
    python3 parse_bgp.py                  # scans output/ for bgp files
    python3 parse_bgp.py -i output/       # explicit input directory
    python3 parse_bgp.py -o report.html   # custom output filename

Automatically picks up files from both:
    - show ip bgp vrf all detail  → *_show_ip_bgp_vrf_all_detail.txt
    - show ip bgp detail          → *_show_ip_bgp_detail.txt
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

OUTPUT_DIR = "output"
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

    seen = set()
    for f in found:
        if f in seen:
            continue
        seen.add(f)

        # Strip slug suffix to get hostname
        host = f.name
        for slug in PARSER.COMMAND_SLUGS:
            host = host.replace(f"_{slug}.txt", "")

        raw = f.read_text(errors="replace")
        # Strip file header comment lines added by collect.py
        raw = re.sub(r"^#.*\n", "", raw, flags=re.MULTILINE)

        neighbors = PARSER.parse(host, raw)
        records.extend(neighbors)
        vrfs = sorted(set(n.get("vrf", "?") for n in neighbors))
        print(f"  Parsed {host}: {len(neighbors)} neighbors across VRFs: {vrfs}")

    return records


# ── State badge colors ────────────────────────────────────────────────────────

STATE_COLORS = {
    "Established":  ("#1a7a4a", "#d4f5e2"),
    "Active":       ("#b45309", "#fef3c7"),
    "Idle":         ("#6b7280", "#f3f4f6"),
    "Connect":      ("#1d4ed8", "#dbeafe"),
    "OpenSent":     ("#6d28d9", "#ede9fe"),
    "OpenConfirm":  ("#0e7490", "#cffafe"),
    "error":        ("#991b1b", "#fee2e2"),
}


# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(records, generated_at):
    columns = PARSER.COLUMNS
    title = PARSER.TITLE
    command = PARSER.COMMAND

    filter_cols = [c for c in columns if c.get("filterable")]
    filters = {}
    for col in filter_cols:
        vals = sorted(set(str(r.get(col["key"], "—")) for r in records))
        filters[col["key"]] = vals

    records_json = json.dumps(records, default=str)
    columns_json = json.dumps(columns)
    state_colors_json = json.dumps(STATE_COLORS)

    filter_dropdowns = ""
    for col in filter_cols:
        options = "".join(f'<option value="{v}">{v}</option>' for v in filters[col["key"]])
        filter_dropdowns += (
            f'<label>{col["label"]}</label>'
            f'<select id="filter-{col["key"]}" data-key="{col["key"]}">'
            f'<option value="">All</option>{options}</select>'
        )

    col_headers = ""
    for i, col in enumerate(columns):
        col_headers += f'<th onclick="sortTable({i})" data-col="{i}">{col["label"]} <span class="sort-icon">↕</span></th>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:      #0d1117;
    --surface: #161b22;
    --border:  #30363d;
    --text:    #e6edf3;
    --muted:   #8b949e;
    --accent:  #58a6ff;
    --green:   #3fb950;
    --red:     #f85149;
    --mono:    'JetBrains Mono', monospace;
    --sans:    'Inter', sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; line-height: 1.5; }}

  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 18px 28px 14px;
    display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  }}
  .header h1 {{ font-family: var(--mono); font-size: 17px; font-weight: 600; color: var(--accent); }}
  .header .cmd {{
    font-family: var(--mono); font-size: 11px; color: var(--muted);
    background: var(--bg); border: 1px solid var(--border); padding: 2px 8px; border-radius: 4px;
  }}
  .header .meta {{ margin-left: auto; font-size: 11px; color: var(--muted); font-family: var(--mono); }}

  .stats {{ display: flex; border-bottom: 1px solid var(--border); background: var(--surface); }}
  .stat {{ padding: 10px 22px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; }}
  .stat-val {{ font-family: var(--mono); font-size: 22px; font-weight: 600; }}
  .stat-val.blue  {{ color: var(--accent); }}
  .stat-val.green {{ color: var(--green); }}
  .stat-val.red   {{ color: var(--red); }}
  .stat-val.plain {{ color: var(--text); }}
  .stat-lbl {{ font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.6px; }}

  .filters {{
    display: flex; gap: 10px; padding: 10px 28px;
    background: var(--surface); border-bottom: 1px solid var(--border);
    flex-wrap: wrap; align-items: center;
  }}
  .filters label {{ font-size: 11px; color: var(--muted); margin-right: -4px; }}
  .filters select, .filters input {{
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 5px; padding: 5px 10px; font-family: var(--sans); font-size: 12px; outline: none;
  }}
  .filters select:hover, .filters input:hover {{ border-color: var(--accent); }}
  .filters input {{ width: 200px; }}
  .filters input::placeholder {{ color: var(--muted); }}
  .btn-reset {{
    margin-left: auto; background: transparent; border: 1px solid var(--border);
    color: var(--muted); border-radius: 5px; padding: 5px 12px;
    font-size: 12px; cursor: pointer; font-family: var(--sans); transition: all 0.15s;
  }}
  .btn-reset:hover {{ border-color: var(--accent); color: var(--accent); }}

  .row-count {{ font-size: 11px; color: var(--muted); padding: 6px 28px 2px; font-family: var(--mono); }}

  .table-wrap {{ overflow-x: auto; padding: 8px 28px 40px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 1000px; font-size: 12px; }}
  thead th {{
    background: var(--surface); color: var(--muted); font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600;
    padding: 8px 12px; text-align: left; border-bottom: 2px solid var(--border);
    white-space: nowrap; cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 1;
  }}
  thead th:hover {{ color: var(--accent); }}
  thead th.sorted .sort-icon {{ color: var(--accent); opacity: 1; }}
  .sort-icon {{ margin-left: 3px; opacity: 0.35; }}

  tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.1s; }}
  tbody tr:hover {{ background: #ffffff07; }}
  tbody td {{ padding: 7px 12px; font-family: var(--mono); font-size: 11.5px; white-space: nowrap; }}
  tbody td.dim {{ color: var(--muted); }}
  tbody td.num {{ text-align: right; }}

  .badge {{
    display: inline-block; padding: 2px 9px; border-radius: 12px;
    font-size: 10.5px; font-weight: 600; font-family: var(--sans); letter-spacing: 0.2px;
  }}
  .vrf-tag {{
    display: inline-block; padding: 1px 7px; border-radius: 4px;
    font-size: 10.5px; font-family: var(--mono);
    background: #58a6ff18; color: var(--accent); border: 1px solid #58a6ff33;
  }}

  .no-results {{ text-align: center; padding: 48px; color: var(--muted); font-family: var(--mono); }}
</style>
</head>
<body>

<div class="header">
  <h1>{title}</h1>
  <span class="cmd">{command}</span>
  <span class="meta">Generated {generated_at}</span>
</div>

<div class="stats" id="stats-bar"></div>

<div class="filters">
  <input type="text" id="search-box" placeholder="Search any field…">
  {filter_dropdowns}
  <button class="btn-reset" onclick="resetFilters()">Reset</button>
</div>

<div class="row-count" id="row-count"></div>

<div class="table-wrap">
  <table id="main-table">
    <thead><tr>{col_headers}</tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="no-results" id="no-results" style="display:none">No matching neighbors found.</div>
</div>

<script>
const RECORDS = {records_json};
const COLUMNS = {columns_json};
const STATE_COLORS = {state_colors_json};

let sortCol = -1, sortAsc = true;

function stateBadge(state) {{
  const pair = STATE_COLORS[state] || ["#374151", "#f9fafb"];
  const [fg, bg] = pair;
  return `<span class="badge" style="background:${{bg}};color:${{fg}};border:1px solid ${{fg}}33">${{state}}</span>`;
}}

function vrfTag(vrf) {{
  if (!vrf || vrf === "—") return '<span class="dim">—</span>';
  return `<span class="vrf-tag">${{vrf}}</span>`;
}}

function renderStats(visible) {{
  const total    = visible.length;
  const estab    = visible.filter(r => r.state === "Established").length;
  const notEstab = total - estab;
  const devices  = new Set(visible.map(r => r.host)).size;
  const vrfs     = new Set(visible.map(r => r.vrf).filter(Boolean)).size;
  const totalPfx = visible.reduce((a, r) => a + (parseInt(r.prefixes_received) || 0), 0);

  document.getElementById("stats-bar").innerHTML = `
    <div class="stat"><span class="stat-val blue">${{devices}}</span><span class="stat-lbl">Devices</span></div>
    <div class="stat"><span class="stat-val blue">${{vrfs}}</span><span class="stat-lbl">VRFs</span></div>
    <div class="stat"><span class="stat-val plain">${{total}}</span><span class="stat-lbl">Neighbors</span></div>
    <div class="stat"><span class="stat-val green">${{estab}}</span><span class="stat-lbl">Established</span></div>
    <div class="stat"><span class="stat-val ${{notEstab > 0 ? 'red' : 'plain'}}">${{notEstab}}</span><span class="stat-lbl">Not Established</span></div>
    <div class="stat"><span class="stat-val plain">${{totalPfx.toLocaleString()}}</span><span class="stat-lbl">Total Pfx Rcvd</span></div>
  `;
}}

function getFiltered() {{
  const search = document.getElementById("search-box").value.toLowerCase();
  const drops  = document.querySelectorAll("[id^='filter-']");
  const active = {{}};
  drops.forEach(s => {{ if (s.value) active[s.dataset.key] = s.value; }});

  return RECORDS.filter(r => {{
    for (const [k, v] of Object.entries(active)) {{
      if (String(r[k] ?? "—") !== v) return false;
    }}
    if (search) {{
      if (!Object.values(r).join(" ").toLowerCase().includes(search)) return false;
    }}
    return true;
  }});
}}

function getSorted(records) {{
  if (sortCol < 0) return records;
  const col = COLUMNS[sortCol];
  return [...records].sort((a, b) => {{
    let av = a[col.key] ?? "", bv = b[col.key] ?? "";
    if (col.numeric) {{ av = Number(av) || 0; bv = Number(bv) || 0; }}
    else {{ av = String(av).toLowerCase(); bv = String(bv).toLowerCase(); }}
    return sortAsc ? (av > bv ? 1 : av < bv ? -1 : 0)
                   : (av < bv ? 1 : av > bv ? -1 : 0);
  }});
}}

function renderTable() {{
  const filtered = getFiltered();
  const sorted   = getSorted(filtered);
  const tbody    = document.getElementById("tbody");

  document.getElementById("row-count").textContent =
    `Showing ${{sorted.length}} of ${{RECORDS.length}} neighbors`;
  renderStats(filtered);

  if (!sorted.length) {{
    tbody.innerHTML = "";
    document.getElementById("no-results").style.display = "block";
    return;
  }}
  document.getElementById("no-results").style.display = "none";

  tbody.innerHTML = sorted.map(r => {{
    const cells = COLUMNS.map(col => {{
      let val = r[col.key] ?? "—";
      let cls = "";
      if (col.badge) {{
        val = stateBadge(String(val));
      }} else if (col.key === "vrf") {{
        val = vrfTag(String(val));
      }} else {{
        val = String(val);
        if (val === "—" || val === "0") cls = "dim";
      }}
      if (col.numeric) cls += " num";
      return `<td class="${{cls.trim()}}">${{val}}</td>`;
    }}).join("");
    return `<tr>${{cells}}</tr>`;
  }}).join("");
}}

function sortTable(idx) {{
  document.querySelectorAll("thead th").forEach((th, i) => {{
    th.classList.toggle("sorted", i === idx);
    const icon = th.querySelector(".sort-icon");
    if (icon) icon.textContent = i === idx ? (sortAsc && sortCol === idx ? "↓" : "↑") : "↕";
  }});
  if (sortCol === idx) sortAsc = !sortAsc; else {{ sortCol = idx; sortAsc = true; }}
  renderTable();
}}

function resetFilters() {{
  document.getElementById("search-box").value = "";
  document.querySelectorAll("[id^='filter-']").forEach(s => s.value = "");
  sortCol = -1; sortAsc = true;
  document.querySelectorAll("thead th").forEach(th => {{
    th.classList.remove("sorted");
    const icon = th.querySelector(".sort-icon");
    if (icon) icon.textContent = "↕";
  }});
  renderTable();
}}

document.getElementById("search-box").addEventListener("input", renderTable);
document.querySelectorAll("[id^='filter-']").forEach(s => s.addEventListener("change", renderTable));

renderTable();
</script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse BGP detail output and render HTML report")
    parser.add_argument("-i", "--input-dir", default=OUTPUT_DIR)
    parser.add_argument("-o", "--output",    default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    print(f"\nBGP Detail Parser")
    print(f"{'='*40}")
    print(f"Input:  {args.input_dir}/")
    print(f"Output: {args.output}\n")

    records = load_files(args.input_dir)
    if not records:
        print("No BGP neighbor records parsed.")
        sys.exit(1)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_html(records, generated_at)

    with open(args.output, "w") as f:
        f.write(html)

    total_vrfs = len(set(r.get("vrf", "") for r in records))
    print(f"\nReport: {args.output}")
    print(f"Neighbors: {len(records)} across {total_vrfs} VRF(s)")


if __name__ == "__main__":
    main()
