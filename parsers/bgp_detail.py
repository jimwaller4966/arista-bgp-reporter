"""
parsers/bgp_detail.py — Parser for Arista 'show ip bgp vrf all detail' output.

Handles both:
  - 'show ip bgp vrf all detail'  (VRF headers embedded in output)
  - 'show ip bgp detail'          (default VRF only, no VRF headers)

VRF context is tracked as the parser walks through the output so each
neighbor record carries the correct VRF name.

To add a new parser:
  1. Create parsers/<name>.py with parse(host, raw_text) -> list[dict]
  2. Define COLUMNS, TITLE, COMMAND at module level
  3. Create a matching parse_<name>.py renderer (clone parse_bgp.py)
"""

import re


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract(pattern, text, group=1, default="—"):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else default


def _int(val, default=0):
    try:
        return int(str(val).replace(",", ""))
    except (ValueError, AttributeError):
        return default


# ── VRF-aware splitter ────────────────────────────────────────────────────────

def _split_vrf_blocks(raw_text):
    """
    Split raw output into (vrf_name, block_text) tuples.

    Handles two formats:

    Format A — 'show ip bgp vrf all detail' (EOS inserts VRF header lines):
        VRF: default
           BGP neighbor is 10.0.0.1 ...
           ...
        VRF: MGMT
           BGP neighbor is 192.168.1.1 ...

    Format B — 'show ip bgp detail' (no VRF headers, implicit default):
        BGP neighbor is 10.0.0.1 ...
        ...

    Returns list of (vrf, neighbor_block_text).
    """
    results = []

    # Check if output contains VRF section headers
    vrf_header_re = re.compile(r"^VRF:\s+(\S+)", re.MULTILINE)
    vrf_matches = list(vrf_header_re.finditer(raw_text))

    if not vrf_matches:
        # Format B — no VRF headers, treat everything as default VRF
        neighbor_blocks = re.split(r"(?=^BGP neighbor is )", raw_text, flags=re.MULTILINE)
        for block in neighbor_blocks:
            block = block.strip()
            if block.startswith("BGP neighbor is "):
                results.append(("default", block))
        return results

    # Format A — walk VRF sections
    for i, match in enumerate(vrf_matches):
        vrf_name = match.group(1)
        section_start = match.end()
        section_end = vrf_matches[i + 1].start() if i + 1 < len(vrf_matches) else len(raw_text)
        section_text = raw_text[section_start:section_end]

        neighbor_blocks = re.split(r"(?=^BGP neighbor is )", section_text, flags=re.MULTILINE)
        for block in neighbor_blocks:
            block = block.strip()
            if block.startswith("BGP neighbor is "):
                results.append((vrf_name, block))

    return results


# ── Per-neighbor block parser ─────────────────────────────────────────────────

def _parse_neighbor_block(host, vrf, block):
    neighbor = _extract(r"^BGP neighbor is (\S+)", block)
    remote_as = _extract(r"remote AS (\d+)", block)
    local_as = _extract(r"local AS (\d+)", block)
    description = _extract(r"Description: (.+)", block)

    # State
    state = _extract(r"BGP state is (\w+)", block)

    # Uptime — present when Established
    uptime = _extract(r"up for (.+?)(?:,|\n)", block)

    # Address families active on this session
    afs = re.findall(r"Address family (\S+ \S+) is", block)
    address_families = ", ".join(afs) if afs else "—"

    # Prefix counts
    prefixes_received = _int(_extract(r"(\d[\d,]*) accepted prefixes", block))
    prefixes_advertised = _int(_extract(r"(\d[\d,]*) advertised prefixes", block))

    # Message counters
    msgs_in = _int(_extract(r"(\d[\d,]*) messages? received", block))
    msgs_out = _int(_extract(r"(\d[\d,]*) messages? sent", block))

    # Hold / keepalive
    hold_time = _extract(r"Hold time is (\d+)", block)
    keepalive = _extract(r"Configured hold time is \d+, keepalive interval is (\d+)", block)

    # Neighbor router-ID
    router_id = _extract(r"Neighbor(?:'s)? BGP router.id (?:is )?(\d+\.\d+\.\d+\.\d+)", block)

    # Session resets and notifications
    resets = _int(_extract(r"(\d+) times? connection reset", block))
    notifications_in = _int(_extract(r"(\d[\d,]*) notifications? received", block))
    notifications_out = _int(_extract(r"(\d[\d,]*) notifications? sent", block))

    return {
        "host":                 host,
        "vrf":                  vrf,
        "neighbor":             neighbor,
        "description":          description,
        "remote_as":            remote_as,
        "local_as":             local_as,
        "state":                state,
        "uptime":               uptime,
        "address_families":     address_families,
        "prefixes_received":    prefixes_received,
        "prefixes_advertised":  prefixes_advertised,
        "msgs_in":              msgs_in,
        "msgs_out":             msgs_out,
        "hold_time":            hold_time,
        "keepalive":            keepalive,
        "router_id":            router_id,
        "resets":               resets,
        "notifications_in":     notifications_in,
        "notifications_out":    notifications_out,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def parse(host, raw_text):
    """
    Parse 'show ip bgp [vrf all] detail' output for one device.

    Args:
        host (str): Device hostname or IP
        raw_text (str): Raw CLI output (vrf all or default-only)

    Returns:
        list[dict]: One dict per BGP neighbor, each with a 'vrf' field
    """
    neighbors = []
    blocks = _split_vrf_blocks(raw_text)

    for vrf, block in blocks:
        try:
            n = _parse_neighbor_block(host, vrf, block)
            neighbors.append(n)
        except Exception as e:
            neighbors.append({
                "host":     host,
                "vrf":      vrf,
                "neighbor": "parse error",
                "state":    "error",
                "_error":   str(e),
            })

    return neighbors


# ── Column definitions (order = HTML table column order) ─────────────────────

COLUMNS = [
    {"key": "host",                "label": "Device",           "filterable": True},
    {"key": "vrf",                 "label": "VRF",              "filterable": True,  "badge": False},
    {"key": "neighbor",            "label": "Neighbor",         "filterable": False},
    {"key": "description",         "label": "Description",      "filterable": False},
    {"key": "remote_as",           "label": "Remote AS",        "filterable": True},
    {"key": "state",               "label": "State",            "filterable": True,  "badge": True},
    {"key": "uptime",              "label": "Uptime",           "filterable": False},
    {"key": "address_families",    "label": "Address Families", "filterable": True},
    {"key": "prefixes_received",   "label": "Pfx Rcvd",        "filterable": False, "numeric": True},
    {"key": "prefixes_advertised", "label": "Pfx Advd",        "filterable": False, "numeric": True},
    {"key": "msgs_in",             "label": "Msgs In",          "filterable": False, "numeric": True},
    {"key": "msgs_out",            "label": "Msgs Out",         "filterable": False, "numeric": True},
    {"key": "resets",              "label": "Resets",           "filterable": False, "numeric": True},
    {"key": "router_id",           "label": "Neighbor RID",     "filterable": False},
    {"key": "hold_time",           "label": "Hold",             "filterable": False},
    {"key": "keepalive",           "label": "KA Interval",      "filterable": False},
]

TITLE = "BGP Neighbor Detail"
COMMAND = "show ip bgp vrf all detail"

# Slug must match sanitize(COMMAND) from collect.py
# sanitize("show ip bgp vrf all detail") → "show_ip_bgp_vrf_all_detail"
# sanitize("show ip bgp detail")         → "show_ip_bgp_detail"
# parse_bgp.py looks for both automatically
COMMAND_SLUGS = [
    "show_ip_bgp_vrf_all_detail",
    "show_ip_bgp_detail",
]
