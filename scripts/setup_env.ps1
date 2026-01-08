Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envExample = Join-Path $repoRoot ".env.example"
$envFile = Join-Path $repoRoot ".env"

if (!(Test-Path $envExample)) {
  Write-Host "ERROR: Missing .env.example at $envExample"
  exit 1
}

if (Test-Path $envFile) {
  Write-Host ".env already exists at: $envFile"
  Write-Host "Edit it if you need to update your LLM settings (do NOT commit it)."
  exit 0
}

Copy-Item -Path $envExample -Destination $envFile -Force

Write-Host "Created .env from .env.example:"
Write-Host "  $envFile"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1) Open the file and paste your real API key into LLM_API_KEY"
Write-Host "   notepad .env"
Write-Host "2) Start API:"
Write-Host "   python api_main.py"
Write-Host "3) Verify (LLM mode):"
Write-Host "   python scripts/test_ai_pipeline.py --mode=llm"
Write-Host ""
Write-Host "Security: .env contains secrets and must NOT be committed."

