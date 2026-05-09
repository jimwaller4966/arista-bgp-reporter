# setup-repo.ps1
# Run from C:\Users\Jim\source\arista-bgp-reporter

$repoRoot = "C:\Users\Jim\source\arista-bgp-reporter"
Set-Location $repoRoot

# ── Create directory structure ────────────────────────────────────────────────
Write-Host "Creating directory structure..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "$repoRoot\parsers"         | Out-Null
New-Item -ItemType Directory -Force -Path "$repoRoot\bgp-lab\configs" | Out-Null
New-Item -ItemType Directory -Force -Path "$repoRoot\output"          | Out-Null

# ── Move lab files into bgp-lab\ ─────────────────────────────────────────────
Write-Host "Organizing lab files..." -ForegroundColor Cyan
$cfgFiles = @("leaf1.cfg","leaf2.cfg","leaf3.cfg","leaf4.cfg","leaf5.cfg","leaf6.cfg")
foreach ($f in $cfgFiles) {
    if (Test-Path "$repoRoot\$f") {
        Move-Item -Force "$repoRoot\$f" "$repoRoot\bgp-lab\configs\$f"
        Write-Host "  Moved $f -> bgp-lab\configs\" -ForegroundColor Gray
    }
}
if (Test-Path "$repoRoot\bgp-fullmesh.yaml") {
    Move-Item -Force "$repoRoot\bgp-fullmesh.yaml" "$repoRoot\bgp-lab\bgp-fullmesh.yaml"
    Write-Host "  Moved bgp-fullmesh.yaml -> bgp-lab\" -ForegroundColor Gray
}
if (Test-Path "$repoRoot\devices.txt") {
    Move-Item -Force "$repoRoot\devices.txt" "$repoRoot\devices.txt.example"
    Write-Host "  Renamed devices.txt -> devices.txt.example" -ForegroundColor Gray
}

# ── .gitignore ────────────────────────────────────────────────────────────────
Write-Host "Writing .gitignore..." -ForegroundColor Cyan
$gitignore = @(
    "# Device lists - never commit real hostnames/IPs",
    "devices.txt",
    "",
    "# Collected CLI output",
    "output/",
    "",
    "# Python",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".venv/",
    "venv/",
    "",
    "# OS",
    ".DS_Store",
    "Thumbs.db"
)
$gitignore | Set-Content "$repoRoot\.gitignore" -Encoding UTF8

# ── README.md ─────────────────────────────────────────────────────────────────
Write-Host "Writing README.md..." -ForegroundColor Cyan
$readme = @(
    "# arista-bgp-reporter",
    "",
    "Collect show ip bgp vrf all detail from Arista EOS devices via SSH and render",
    "an interactive HTML report with filterable, sortable tables per VRF and neighbor.",
    "",
    "## Requirements",
    "",
    "    pip install netmiko",
    "",
    "## Usage",
    "",
    "### 1. Configure devices",
    "",
    "    cp devices.txt.example devices.txt",
    "    # Edit devices.txt - one hostname or IP per line",
    "",
    "### 2. Collect",
    "",
    "    python3 collect.py",
    "    # Prompts for credentials, saves output/<host>_show_ip_bgp_vrf_all_detail.txt",
    "",
    "### 3. Parse and render",
    "",
    "    python3 parse_bgp.py",
    "    # Generates bgp_report.html",
    "",
    "Open bgp_report.html in any browser.",
    "",
    "## Report features",
    "",
    "- Live search across all fields",
    "- Filter by Device, VRF, Remote AS, State, Address Family",
    "- Sortable columns",
    "- State badges (Established / Active / Idle / etc.)",
    "- Stats bar: devices, VRFs, neighbors, established count, total prefixes",
    "",
    "## Lab (cEOS / Containerlab)",
    "",
    "A 6-node full-mesh cEOS lab with eBGP across default, PROD, and MGMT VRFs",
    "is included under bgp-lab/ for testing.",
    "",
    "    cd bgp-lab",
    "    sudo containerlab deploy -t bgp-fullmesh.yaml",
    "",
    "Requires Containerlab (https://containerlab.dev) and a local ceosimage:4.36.0.1F Docker image.",
    "",
    "## Adding parsers",
    "",
    "To add support for a new command:",
    "1. Create parsers/<name>.py with parse(host, raw), COLUMNS, TITLE, COMMAND, COMMAND_SLUGS",
    "2. Clone parse_bgp.py to parse_<name>.py pointing to the new parser",
    "3. Add the command to DEFAULT_COMMANDS in collect.py or pass it with -c"
)
$readme | Set-Content "$repoRoot\README.md" -Encoding UTF8

# ── parsers/__init__.py ───────────────────────────────────────────────────────
Write-Host "Writing parsers/__init__.py..." -ForegroundColor Cyan
"# parsers package" | Set-Content "$repoRoot\parsers\__init__.py" -Encoding UTF8

# ── Check for Python files ────────────────────────────────────────────────────
Write-Host ""
$missing = @()
foreach ($f in @("collect.py", "parse_bgp.py", "parsers\bgp_detail.py")) {
    if (-not (Test-Path "$repoRoot\$f")) { $missing += $f }
}

if ($missing.Count -gt 0) {
    Write-Host "Missing files - copy these in before committing:" -ForegroundColor Yellow
    foreach ($f in $missing) { Write-Host "  $repoRoot\$f" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Then run:" -ForegroundColor Cyan
    Write-Host '  git add .' -ForegroundColor White
    Write-Host '  git commit -m "Initial commit - BGP collector, parser, and cEOS lab"' -ForegroundColor White
    Write-Host '  gh repo create arista-bgp-reporter --private --push --source=.' -ForegroundColor White
    exit 0
}

# ── Commit and push ───────────────────────────────────────────────────────────
Write-Host "Committing and pushing..." -ForegroundColor Cyan
git add .
git commit -m "Initial commit - BGP collector, parser, and cEOS lab"
gh repo create arista-bgp-reporter --private --push --source=.
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
