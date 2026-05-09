# deploy.ps1
# Run from anywhere on Windows
# Downloads files from Downloads folder, puts them in the right place, commits, pushes

$repo     = "C:\Users\Jim\source\arista-bgp-reporter"
$dl       = "$env:USERPROFILE\Downloads"

Write-Host "Moving files into repo..." -ForegroundColor Cyan

# ── Python scripts ────────────────────────────────────────────────────────────
$pyFiles = @("collect.py", "parse_bgp.py")
foreach ($f in $pyFiles) {
    if (Test-Path "$dl\$f") {
        Copy-Item -Force "$dl\$f" "$repo\$f"
        Write-Host "  $f -> $repo\" -ForegroundColor Gray
    } else {
        Write-Host "  MISSING: $dl\$f" -ForegroundColor Yellow
    }
}

# ── Parser module ─────────────────────────────────────────────────────────────
if (Test-Path "$dl\bgp_detail.py") {
    Copy-Item -Force "$dl\bgp_detail.py" "$repo\parsers\bgp_detail.py"
    Write-Host "  bgp_detail.py -> $repo\parsers\" -ForegroundColor Gray
} else {
    Write-Host "  MISSING: $dl\bgp_detail.py" -ForegroundColor Yellow
}

# ── Leaf configs ──────────────────────────────────────────────────────────────
for ($i = 1; $i -le 6; $i++) {
    $f = "leaf$i.cfg"
    if (Test-Path "$dl\$f") {
        Copy-Item -Force "$dl\$f" "$repo\bgp-lab\configs\$f"
        Write-Host "  $f -> $repo\bgp-lab\configs\" -ForegroundColor Gray
    } else {
        Write-Host "  MISSING: $dl\$f" -ForegroundColor Yellow
    }
}

# ── Commit and push ───────────────────────────────────────────────────────────
Set-Location $repo
git add .
$status = git status --short
if ($status) {
    git commit -m "Update configs: subinterfaces for PROD/MGMT VRFs, fix command slug"
    git push
    Write-Host ""
    Write-Host "Pushed to GitHub." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Nothing to commit - files may not have changed." -ForegroundColor Yellow
}
