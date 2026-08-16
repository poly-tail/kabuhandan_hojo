param(
    [string]$InputDir = "docs/graphs/src",
    [string]$OutputDir = "docs/graphs/generated"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts/render_docs_graphs.py"

& python $scriptPath --input-dir (Join-Path $repoRoot $InputDir) --output-dir (Join-Path $repoRoot $OutputDir)
exit $LASTEXITCODE
