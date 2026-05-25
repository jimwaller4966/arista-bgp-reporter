"""
parsers/bgp_detail.py — Parser for Arista 'show ip bgp detail vrf all' output.

Each record represents one BGP path for a prefix, not a neighbor session.

Fields per record:
    host, vrf, prefix, paths_available,
    as_path, next_hop, peer_ip, peer_rid,
    origin, local_pref, weight, metric,
    age, valid, best, local, redistributed,
    communities
"""
import re

TITLE        = "BGP Route Detail"
COMMAND      = "show ip bgp detail vrf all"
COMMAND_SLUGS = [
    "show_ip_bgp_detail_vrf_all",
    "show_ip_bgp_detail",
]

COLUMNS = [
    {"key": "host",            "label": "Device"},
    {"key": "vrf",             "label": "VRF"},
    {"key": "prefix",          "label": "Prefix"},
    {"key": "paths_available", "label": "Paths"},
    {"key": "as_path",         "label": "AS Path"},
    {"key": "next_hop",        "label": "Next Hop"},
    {"key": "peer_ip",         "label": "Peer IP"},
    {"key": "origin",          "label": "Origin"},
    {"key": "local_pref",      "label": "Local Pref"},
    {"key": "weight",          "label": "Weight"},
    {"key": "metric",          "label": "Metric"},
    {"key": "age",             "label": "Age"},
    {"key": "best",            "label": "Best"},
    {"key": "valid",           "label": "Valid"},
    {"key": "local",           "label": "Local"},
    {"key": "communities",     "label": "Communities"},
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def _extract(pattern, text, group=1, default="—"):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else default

def _flag(pattern, text):
    return bool(re.search(pattern, text))

# ── VRF block splitter ────────────────────────────────────────────────────────
def _split_vrf_blocks(raw_text):
    """
    Split raw output into (vrf_name, block_text) tuples.
    Handles:
      Format A — 'show ip bgp detail vrf all':
        BGP routing table information for VRF default
          BGP routing table entry for 10.0.0.1/32
          ...
      Format B — 'show ip bgp detail' (default VRF only, no VRF header):
        BGP routing table entry for 10.0.0.1/32
        ...
    """
    results = []
    vrf_header_re = re.compile(
        r"^BGP routing table information for VRF (\S+)", re.MULTILINE
    )
    vrf_matches = list(vrf_header_re.finditer(raw_text))

    if not vrf_matches:
        # Format B — no VRF headers, treat as default
        prefix_blocks = re.split(r"(?=^BGP routing table entry for )", raw_text, flags=re.MULTILINE)
        for block in prefix_blocks:
            block = block.strip()
            if block.startswith("BGP routing table entry for "):
                results.append(("default", block))
        return results

    # Format A — walk VRF sections
    for i, match in enumerate(vrf_matches):
        vrf_name = match.group(1)
        section_start = match.end()
        section_end = vrf_matches[i + 1].start() if i + 1 < len(vrf_matches) else len(raw_text)
        section_text = raw_text[section_start:section_end]
        prefix_blocks = re.split(r"(?=^BGP routing table entry for )", section_text, flags=re.MULTILINE)
        for block in prefix_blocks:
            block = block.strip()
            if block.startswith("BGP routing table entry for "):
                results.append((vrf_name, block))

    return results

# ── Path splitter within a prefix block ───────────────────────────────────────
def _split_paths(block):
    """
    Given a prefix block, return a list of individual path strings.
    Paths start with a line that is either:
      - An AS path like "  65002" or "  65003 65002"
      - "  Local" for locally originated routes
    """
    # Split on lines that look like the start of a path:
    # 2 spaces + (digits/spaces forming AS path, or "Local")
    # Also handles "(aggregated by <rid> <ip>)" suffix on the AS path line
    path_re = re.compile(
        r"(?=^  (?:Local|\d[\d ]*)(?:\s*\(aggregated by[^)]*\))?\s*$)",
        re.MULTILINE
    )
    paths = path_re.split(block)
    return [p.strip() for p in paths if p.strip() and not p.strip().startswith("BGP routing table")]

# ── Per-path parser ───────────────────────────────────────────────────────────
def _parse_path(host, vrf, prefix, paths_available, path_text):
    """Parse a single path block into a record dict."""
    lines = path_text.splitlines()

    # First line is the AS path (or "Local") — strip any (aggregated by ...) suffix
    as_path_raw = lines[0].strip() if lines else "—"
    as_path = re.sub(r"\s*\(aggregated by[^)]*\)", "", as_path_raw).strip() or "—"

    # Next-hop line: "    10.1.12.2 from 10.1.12.2 (10.0.0.2)"
    # or for local:  "    - from - (10.0.0.1)"
    nexthop_line = lines[1].strip() if len(lines) > 1 else ""
    next_hop = _extract(r"^(\S+)\s+from", nexthop_line, default="—")
    peer_ip  = _extract(r"from\s+(\S+)", nexthop_line, default="—")

    # Attributes line: "Origin IGP, metric 0, localpref 100, ..."
    attr_line = " ".join(lines[2:]) if len(lines) > 2 else ""

    origin     = _extract(r"Origin\s+(\S+)",          attr_line, default="—").rstrip(",")
    metric     = _extract(r"metric\s+(\S+),",          attr_line, default="—")
    local_pref = _extract(r"localpref\s+(\S+),",       attr_line, default="—")
    weight     = _extract(r"weight\s+(\d+)",            attr_line, default="0")

    # Age / flags line: "Received 00:01:23 ago, valid, external, best"
    age  = _extract(r"Received\s+(\S+)\s+ago",         attr_line, default="—")
    best  = _flag(r"\bbest\b",                          attr_line)
    valid = _flag(r"\bvalid\b",                         attr_line)
    local = _flag(r"\blocal\b",                         attr_line)
    redistributed = _flag(r"\bredistributed\b",         attr_line)

    # Communities — may appear 0 or more times across the path text
    # EOS format: "Community: 65001:10 65001:12200"
    community_matches = re.findall(r"Community:\s+(.+)", path_text)
    if community_matches:
        # Flatten all communities, deduplicate preserving order
        all_comms = []
        seen = set()
        for cm in community_matches:
            for c in cm.strip().split():
                if c not in seen:
                    seen.add(c)
                    all_comms.append(c)
        communities = " ".join(all_comms)
    else:
        communities = ""

    return {
        "host":            host,
        "vrf":             vrf,
        "prefix":          prefix,
        "paths_available": paths_available,
        "as_path":         as_path,
        "next_hop":        next_hop,
        "peer_ip":         peer_ip,
        "origin":          origin,
        "local_pref":      local_pref,
        "weight":          weight,
        "metric":          metric,
        "age":             age,
        "best":            "✓" if best else "",
        "valid":           "✓" if valid else "",
        "local":           "✓" if local else "",
        "redistributed":   "✓" if redistributed else "",
        "communities":     communities,
    }

# ── Main entry point ──────────────────────────────────────────────────────────
def parse(host, raw_text):
    """
    Parse raw 'show ip bgp detail vrf all' output.
    Returns list of dicts, one per BGP path.
    """
    records = []
    vrf_blocks = _split_vrf_blocks(raw_text)

    for vrf, prefix_block in vrf_blocks:
        prefix = _extract(r"^BGP routing table entry for (\S+)", prefix_block)
        paths_available = _extract(r"Paths:\s+(\d+)\s+available", prefix_block, default="1")

        path_texts = _split_paths(prefix_block)
        for path_text in path_texts:
            rec = _parse_path(host, vrf, prefix, paths_available, path_text)
            records.append(rec)

    return records
