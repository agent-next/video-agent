# open-video Windows installer (Ollama-style one-liner)
#
#   irm https://open-video.ai/install.ps1 | iex
#   # or from a checkout:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
#
# H3 generation is NVIDIA + ComfyUI (Linux-first). On Windows this script:
#   1. Detects OS / GPU via nvidia-smi if present
#   2. Prefers WSL2 to run scripts/install.sh (full path)
#   3. Otherwise clones the repo + sets up Python dry-run path and prints next steps
#
# Apache-2.0

$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:OPEN_VIDEO_REPO) { $env:OPEN_VIDEO_REPO } else { "https://github.com/agent-next/video-agent.git" }
$Root = if ($env:OPEN_VIDEO_HOME) { $env:OPEN_VIDEO_HOME } else { Join-Path $env:USERPROFILE "open-video" }

function Write-Step($msg) { Write-Host "`n[open-video] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  ·   $msg" -ForegroundColor Gray }
function Write-Warn($msg) { Write-Host "  !   $msg" -ForegroundColor Yellow }

Write-Host @"

  open-video Windows installer — Ollama-for-H3
  Repo: $RepoUrl

"@ -ForegroundColor Yellow

Write-Step "Detecting platform and GPU"
Write-Info "OS: Windows $($PSVersionTable.PSVersion)  PowerShell $($PSVersionTable.PSEdition)"
$haveNvidia = $false
$vram = 0
$gpuName = "none"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  try {
    $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader | Select-Object -First 1).Trim()
    $vram = [int]((nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1).Trim())
    $haveNvidia = $true
    Write-Ok "NVIDIA GPU: $gpuName ($vram MiB VRAM)"
  } catch {
    Write-Warn "nvidia-smi present but query failed"
  }
} else {
  Write-Warn "No nvidia-smi — H3 generation needs NVIDIA (+ preferably WSL2 Ubuntu)"
}

# Resource-aware hint (mirrors core/resources.py thresholds)
$quant = "int8"
$lowvram = $true
if (-not $haveNvidia) {
  Write-Info "quant recommendation: int8 (no NVIDIA — plan/dry-run only until GPU available)"
} elseif ($vram -lt (9 * 1024)) {
  $quant = "nf4"; Write-Ok "quant recommendation: nf4 (VRAM $vram MiB < 9 GiB)"
} elseif ($vram -lt (12 * 1024)) {
  $quant = "w4"; Write-Ok "quant recommendation: w4 (VRAM $vram MiB < 12 GiB)"
} elseif ($vram -lt (22 * 1024)) {
  $quant = "int8"; Write-Ok "quant recommendation: int8 + lowvram (VRAM $vram MiB < 22 GiB)"
} else {
  $quant = "int8"; $lowvram = $false
  Write-Ok "quant recommendation: int8 (VRAM $vram MiB ≥ 22 GiB)"
}

# Prefer WSL for the full Linux installer
$wsl = Get-Command wsl -ErrorAction SilentlyContinue
if ($wsl) {
  Write-Step "WSL detected — running Linux installer (full H3 path)"
  Write-Info "This is the supported Windows path for ComfyUI + H3 (same as Ollama's multi-OS split)."
  $bashArgs = @()
  if ($env:OPEN_VIDEO_SELF_TEST -eq "1") { $bashArgs += "--self-test" }
  if ($env:OPEN_VIDEO_SKIP_DOWNLOAD -eq "1") { $bashArgs += "--skip-download" }
  if ($env:OPEN_VIDEO_DRY_RUN -eq "1") { $bashArgs += "--dry-run" }
  $bashArgs += @("--quant", $quant, "-y")
  $argStr = ($bashArgs -join " ")
  # Install into ~/open-video inside default WSL distro
  $cmd = @"
set -e
if [ ! -e `$HOME/open-video/.git ]; then
  git clone --depth 1 '$RepoUrl' `$HOME/open-video
fi
cd `$HOME/open-video
for required in core/resources.py scripts/comfyui.pin models/h3_manifest.json scripts/verify_h3_manifest.py; do
  if [ ! -f "`$required" ]; then
    printf '%s\n' "Checkout is missing `$required. Preserve local changes and run git pull --ff-only on the intended branch in ~/open-video, then re-run. Product source is not updated automatically." >&2
    exit 1
  fi
done
bash scripts/install.sh $argStr
"@
  Write-Info "wsl bash -lc '... install.sh $argStr'"
  wsl bash -lc $cmd
  if ($LASTEXITCODE -ne 0) { throw "WSL install.sh failed with exit $LASTEXITCODE" }
  Write-Ok "Linux stack installed inside WSL. Generate with:"
  Write-Host "  wsl bash -lc 'cd ~/open-video && .venv/bin/open-video \"your prompt\" --dry-run'"
  exit 0
}

Write-Step "No WSL — staging Windows checkout for dry-run / docs path"
Write-Warn "Full H3 GPU generation on native Windows is not the default path."
Write-Warn "Install WSL2 Ubuntu, then re-run:  irm https://open-video.ai/install.ps1 | iex"
Write-Info "Staging git clone at $Root for orchestrator dry-run..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git not found. Install Git for Windows or enable WSL."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
  throw "python not found. Install Python 3.10+ from https://www.python.org/downloads/"
}

if (-not (Test-Path (Join-Path $Root ".git"))) {
  git clone --depth 1 $RepoUrl $Root
  if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
} else {
  Write-Ok "Reusing checkout without updating its source: $Root"
}
foreach ($required in @("cli/open_video.py", "core/resources.py", "scripts/comfyui.pin", "models/h3_manifest.json", "scripts/verify_h3_manifest.py")) {
  if (-not (Test-Path -PathType Leaf (Join-Path $Root $required))) {
    throw "Checkout is missing $required. Preserve local changes and run git pull --ff-only on the intended branch in '$Root', then re-run. Product source is not updated automatically."
  }
}

$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
Push-Location $Root
try {
  Write-Step "Resource probe (shipped core/resources.py)"
  & $py core/resources.py --vram $vram $(if (-not $haveNvidia) { "--no-nvidia" }) --quant auto
  Write-Step "Orchestrator dry-run (no ComfyUI / no GPU required for plan)"
  & $py cli/open_video.py "a golden sunrise over calm water, welcome to OpenVideo" --dry-run --duration 5
  if ($LASTEXITCODE -ne 0) { throw "dry-run failed" }
  Write-Ok "dry-run passed — plan + validator OK"
} finally {
  Pop-Location
}

Write-Host @"

==============================================================
  open-video staged on Windows
==============================================================
  Quant hint: $quant   lowvram=$lowvram
  Checkout:   $Root

  Next for real GPU generation:
    1. Install WSL2 + Ubuntu + NVIDIA CUDA on WSL
    2. Re-run:  irm https://open-video.ai/install.ps1 | iex

  Dry-run anytime:
    cd $Root
    $py cli/open_video.py "your prompt" --dry-run

  Docs: https://open-video.ai/docs

"@ -ForegroundColor Green
