param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $PSScriptRoot
$Frontend = (Resolve-Path (Join-Path $Backend "..\frontend")).Path
# Google Drive / non-NTFS breaks npm install; run Vite from a local NTFS copy.
$LocalFrontend = Join-Path $env:LOCALAPPDATA "calendar-frontend-deps"

function Resolve-Uv {
    $winget = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $dirs = @()
    if (Test-Path -LiteralPath $winget) {
        $dirs += Get-ChildItem -LiteralPath $winget -Directory -Filter "astral-sh.uv_*" |
            Select-Object -ExpandProperty FullName
    }
    $dirs += @(
        $(Join-Path $env:USERPROFILE ".local\bin"),
        $(Join-Path $env:USERPROFILE ".cargo\bin"),
        $(Join-Path $env:LOCALAPPDATA "Programs\uv")
    )
    foreach ($dir in $dirs) {
        if (-not $dir) { continue }
        $uv = Join-Path $dir "uv.exe"
        if (Test-Path -LiteralPath $uv) {
            $env:Path = "$dir;$env:Path"
            return $uv
        }
    }
    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $env:Path = "$(Split-Path -Parent $cmd.Source);$env:Path"
        return $cmd.Source
    }
    throw "uv was not found. Install uv and run make up again."
}

function Wait-Api {
    param($Process)
    for ($i = 0; $i -lt 60; $i++) {
        if ($Process.HasExited) {
            throw "API exited before it was ready (code $($Process.ExitCode))."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }
    throw "API did not start on http://127.0.0.1:8000"
}

function Resolve-Npm {
    $dirs = @(
        $(if ($env:ProgramW6432) { Join-Path $env:ProgramW6432 "nodejs" }),
        $(Join-Path $env:ProgramFiles "nodejs"),
        "C:\Program Files\nodejs",
        $(Join-Path $env:LOCALAPPDATA "Programs\nodejs")
    )
    foreach ($dir in $dirs) {
        if (-not $dir) { continue }
        $npm = Join-Path $dir "npm.cmd"
        $node = Join-Path $dir "node.exe"
        if ((Test-Path -LiteralPath $npm) -and (Test-Path -LiteralPath $node)) {
            # 32-bit make shells often miss the real Program Files Node install.
            $env:Path = "$dir;$env:Path"
            return $npm
        }
    }
    throw "npm was not found. Install Node.js and run make up again."
}

function Sync-FrontendToLocal {
    New-Item -ItemType Directory -Force -Path $LocalFrontend | Out-Null
    Copy-Item (Join-Path $Frontend "package.json") $LocalFrontend -Force
    Copy-Item (Join-Path $Frontend "vite.config.ts") $LocalFrontend -Force
    Copy-Item (Join-Path $Frontend "index.html") $LocalFrontend -Force
    Get-ChildItem (Join-Path $Frontend "tsconfig*.json") | ForEach-Object {
        Copy-Item $_.FullName $LocalFrontend -Force
    }
    $localSrc = Join-Path $LocalFrontend "src"
    if (Test-Path $localSrc) {
        Remove-Item $localSrc -Recurse -Force
    }
    Copy-Item (Join-Path $Frontend "src") $localSrc -Recurse -Force
}

function Stop-DevServers {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match "uvicorn app.main:app" -or
            ($_.CommandLine -match "vite" -and (
                $_.CommandLine -match [regex]::Escape($Frontend) -or
                $_.CommandLine -match [regex]::Escape($LocalFrontend) -or
                $_.CommandLine -match "calendar-frontend-deps"
            ))
        )
    }
    foreach ($proc in $procs) {
        & taskkill /PID $proc.ProcessId /T /F 2>$null | Out-Null
    }
}

$Uv = Resolve-Uv
$Npm = Resolve-Npm

if ($Action -eq "down") {
    Stop-DevServers
    Write-Host "Stopped API and frontend"
    exit 0
}

Write-Host "API  http://127.0.0.1:8000"
Write-Host "UI   http://127.0.0.1:5173"
Write-Host "Syncing frontend to $LocalFrontend"
Sync-FrontendToLocal

Write-Host "Using $Uv"
# Start uv.exe directly (not cmd /k): /k stays alive after uv fails, so Wait-Api
# never sees HasExited and Vite can come up against a dead API.
$api = Start-Process -PassThru -FilePath $Uv -WorkingDirectory $Backend -WindowStyle Minimized -ArgumentList @(
    "run",
    "uvicorn",
    "app.main:app",
    "--reload",
    "--host",
    "127.0.0.1",
    "--port",
    "8000"
)
Wait-Api $api
Write-Host "API ready"
try {
    if (-not (Test-Path (Join-Path $LocalFrontend "node_modules"))) {
        Write-Host "Installing frontend dependencies..."
        & $Npm install --prefix $LocalFrontend
    }
    & $Npm run dev --prefix $LocalFrontend
    $code = $LASTEXITCODE
}
finally {
    if ($api -and -not $api.HasExited) {
        & taskkill /PID $api.Id /T /F 2>$null | Out-Null
    }
    Stop-DevServers
}
if ($null -eq $code) {
    exit 0
}
exit $code
