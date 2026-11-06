#Requires -Version 5.1
<#
.SYNOPSIS
    Full verification gate for the FPSO EPC backend + frontend.

.DESCRIPTION
    Runs the offline backend suite, then starts the SQLite dev backend,
    runs the live connectivity suite, and stops it. Finally runs the
    frontend tests, type check, and production build.

    Usage:
        .\scripts\verify.ps1
        .\scripts\verify.ps1 -SkipFrontend
        .\scripts\verify.ps1 -SkipConnectivity
#>
param(
    [switch]$SkipConnectivity,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python. Create it first (see CLAUDE.md)."
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "PASSED: $Name" -ForegroundColor Green
}

Invoke-Step "Backend unit tests (offline)" {
    Push-Location $backend
    try { & $python -m pytest tests/ -q -m "not live" }
    finally { Pop-Location }
}

if (-not $SkipConnectivity) {
    Invoke-Step "Backend connectivity tests (live dev_main :8080)" {
        $log = Join-Path $env:TEMP "fpso-dev-main-verify.log"
        $server = Start-Process -FilePath $python `
            -ArgumentList "-m", "uvicorn", "dev_main:app", "--host", "127.0.0.1", "--port", "8080" `
            -WorkingDirectory $backend -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $log -RedirectStandardError "$log.err"

        try {
            $ready = $false
            for ($i = 0; $i -lt 40; $i++) {
                Start-Sleep -Milliseconds 500
                try {
                    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -UseBasicParsing -TimeoutSec 2
                    if ($resp.StatusCode -eq 200) { $ready = $true; break }
                } catch {
                    if ($server.HasExited) { break }
                }
            }
            if (-not $ready) {
                Write-Host "dev_main did not become ready. Output:" -ForegroundColor Red
                if (Test-Path $log) { Get-Content $log -Tail 40 }
                if (Test-Path "$log.err") { Get-Content "$log.err" -Tail 40 }
                exit 1
            }

            Push-Location $backend
            try { & $python -m pytest tests/test_endpoint_connectivity.py -q -m live }
            finally { Pop-Location }

            Push-Location $root
            try { & $python scripts/security_smoke.py --base-url http://127.0.0.1:8080 }
            finally { Pop-Location }
        }
        finally {
            if ($server -and -not $server.HasExited) {
                Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
                $server.WaitForExit(5000) | Out-Null
            }
        }
    }
}

if (-not $SkipFrontend) {
    # npm/tsc write warnings (e.g. the Browserslist notice) to stderr. In
    # PowerShell 5.1 a native command's stderr becomes a NativeCommandError,
    # which is terminating while $ErrorActionPreference is "Stop". Relax it for
    # these calls and rely on $LASTEXITCODE instead.
    $nativePreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        Invoke-Step "Frontend unit tests" {
            Push-Location $frontend
            try { & npm run test }
            finally { Pop-Location }
        }

        Invoke-Step "Frontend type check" {
            Push-Location $frontend
            try { & npx tsc --noEmit }
            finally { Pop-Location }
        }

        Invoke-Step "Frontend production build" {
            Push-Location $frontend
            try { & npm run build }
            finally { Pop-Location }
        }
    }
    finally {
        $ErrorActionPreference = $nativePreference
    }
}

Write-Host ""
Write-Host "All verification gates passed." -ForegroundColor Green
