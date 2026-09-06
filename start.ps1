# start-dev.ps1
# Launches all 4 services in separate PowerShell windows.

$ErrorActionPreference = "Stop"

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV = Join-Path $PROJECT_ROOT ".venv"
$PYTHON = Join-Path $VENV "Scripts\python.exe"

function Run-In-NewWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    $fullCommand = @"
Set-Location -LiteralPath '$PROJECT_ROOT'
`$Host.UI.RawUI.WindowTitle = '$Title'
Write-Host '--- $Title ---' -ForegroundColor Cyan
Write-Host ''

try {
    $Command
}
catch {
    Write-Host ''
    Write-Host 'ERROR:' -ForegroundColor Red
    Write-Host `$_ -ForegroundColor Red
}

Write-Host ''
Write-Host 'Process finished. Press Enter to close this window...' -ForegroundColor Yellow
Read-Host
"@

    Start-Process powershell.exe `
        -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $fullCommand
}

# Client UI
Run-In-NewWindow "client_ui" @"
Set-Location '$PROJECT_ROOT\client_ui'
npm run dev
"@

# Orchestrator
Run-In-NewWindow "orchestrator" @"
& '$PYTHON' -m uvicorn orchestrator.main:app --port 8001 --reload
"@

# RAG service
Run-In-NewWindow "RAG service" @"
Set-Location '$PROJECT_ROOT\RAG'
& '$PYTHON' -m uvicorn rag_server:app --port 8000
"@

# Router
Run-In-NewWindow "router" @"
ollama-agent-router serve --config '$PROJECT_ROOT\ollama-agent-router.yaml'
"@

Write-Host "Launched 4 PowerShell windows." -ForegroundColor Green
