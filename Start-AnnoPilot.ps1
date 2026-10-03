param([switch]$Install)
$ErrorActionPreference = 'Stop'
$annoRoot = $PSScriptRoot
$annoPython = Join-Path $annoRoot 'backend\.venv\Scripts\python.exe'
if ($Install -or !(Test-Path -LiteralPath $annoPython)) {
    python -m venv (Join-Path $annoRoot 'backend\.venv')
    & $annoPython -m pip install --upgrade pip
    & $annoPython -m pip install -r (Join-Path $annoRoot 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
}
if ($Install -or !(Test-Path -LiteralPath (Join-Path $annoRoot 'frontend\node_modules'))) {
    Push-Location (Join-Path $annoRoot 'frontend')
    try { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' } }
    finally { Pop-Location }
}
foreach ($annoPort in 8000,3000) {
    if (Get-NetTCPConnection -LocalPort $annoPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $annoPort is already in use. Stop the previous server or open http://localhost:3000 if AnnoPilot is already running."
    }
}
$annoBackend = Start-Process -FilePath $annoPython -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $annoRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $annoRoot 'backend\server.log') -RedirectStandardError (Join-Path $annoRoot 'backend\server-error.log') -PassThru
$annoNode = (Get-Command node.exe).Source
$annoFrontend = Start-Process -FilePath $annoNode -ArgumentList 'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','3000' -WorkingDirectory (Join-Path $annoRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $annoRoot 'frontend\server.log') -RedirectStandardError (Join-Path $annoRoot 'frontend\server-error.log') -PassThru
Write-Host "AnnoPilot starting. Frontend: http://localhost:3000 · API: http://localhost:8000/docs"
Write-Host "Started process IDs: backend $($annoBackend.Id), frontend $($annoFrontend.Id). Logs are in backend/ and frontend/."
