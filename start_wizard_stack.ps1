# start_wizard_stack.ps1 — RE-Wizard-Flow komplett hochfahren.
#
# Startet beide Prozesse des Wizard-Flows:
#   1. Evaluation-Backend :8087  (external/arch_team, python -m backend.main)
#   2. RE-Dashboard       :8080  (start_dashboard.py, Wizard-UI unter /wizard)
#
# Raeumt vorher verwaiste Uvicorn-Worker weg (Windows: multiprocessing.spawn-
# Kinder ueberleben den Parent-Kill und halten den Port mit ALTER Env — siehe
# EVALUATION_TODO.md, Falle 2).
#
# Aufruf:  powershell -File start_wizard_stack.ps1 [-SkipDashboard] [-SkipBackend]

param(
    [switch]$SkipDashboard,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$ArchTeam = Join-Path $Root "external\arch_team"

function Stop-PortOwners([int]$Port) {
    # Listener + verwaiste multiprocessing.spawn-Worker toeten (mehrere Runden,
    # weil geerbte Sockets den Port an tote PIDs binden koennen).
    for ($i = 0; $i -lt 5; $i++) {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $conns) { break }
        foreach ($p in ($conns.OwningProcess | Sort-Object -Unique)) {
            Stop-Process -Id $p -Force -Confirm:$false -ErrorAction SilentlyContinue
        }
        Start-Sleep 1
    }
    # Orphan-Worker: python -c "from multiprocessing.spawn ..." mit toter PPID
    $alive = @{}
    Get-CimInstance Win32_Process | ForEach-Object { $alive[$_.ProcessId] = $true }
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -match 'multiprocessing\.spawn' -and -not $alive.ContainsKey($_.ParentProcessId) } |
        ForEach-Object {
            Write-Host "  Orphan-Worker PID $($_.ProcessId) (tote PPID $($_.ParentProcessId)) -> kill"
            Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
        }
    $rest = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($rest) { throw "Port $Port weiterhin belegt (PIDs: $($rest.OwningProcess -join ','))" }
}

function Wait-Http([string]$Url, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep 1 }
    }
    return $false
}

if (-not $SkipBackend) {
    Write-Host "[1/2] Evaluation-Backend :8087 ..."
    Stop-PortOwners 8087
    if (-not (Test-Path (Join-Path $ArchTeam ".env"))) {
        Write-Warning "external/arch_team/.env fehlt — Backend faellt ohne LLM-Zugang STILL auf Mock-Scores zurueck (erkennbar an mock=true im Response)."
    }
    Start-Process -WorkingDirectory $ArchTeam -WindowStyle Hidden python -ArgumentList "-m", "backend.main"
    if (-not (Wait-Http "http://localhost:8087/health" 30)) { throw "Backend :8087 kam nicht hoch" }
    $cfg = (Invoke-RestMethod "http://localhost:8087/api/runtime-config").llm
    Write-Host "  OK — model=$($cfg.model), key=$($cfg.openrouter_api_key_present)"
    if (-not $cfg.openrouter_api_key_present) { Write-Warning "Kein API-Key im Backend — Bewertungen werden Mock sein!" }
}

if (-not $SkipDashboard) {
    Write-Host "[2/2] RE-Dashboard :8080 ..."
    Stop-PortOwners 8080
    Start-Process -WorkingDirectory $Root -WindowStyle Hidden python -ArgumentList "start_dashboard.py", "--no-browser"
    if (-not (Wait-Http "http://localhost:8080/wizard" 45)) { throw "Dashboard :8080 kam nicht hoch" }
    Write-Host "  OK — Wizard-UI: http://localhost:8080/wizard"
}

Write-Host ""
Write-Host "Wizard-Stack laeuft. Flow: extract -> validate-batch -> decide -> improve/split"
