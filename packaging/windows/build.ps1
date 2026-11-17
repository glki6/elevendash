# Builds "Eleven Dashboard" for Windows: a folder with Eleven Dashboard.exe in it, zipped.
# Run from the repository with a Python that has elevendash and PyInstaller installed (a venv; see release.yml):
#   powershell -File packaging\windows\build.ps1
# Then it checks the build: the demo builds a dashboard, and the app answers on this computer.
# Everything it writes stays in packaging\windows\out (ignored by git).
$ErrorActionPreference = 'Stop'
$name = 'Eleven Dashboard'
$out = Join-Path $PSScriptRoot 'out'
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --windowed --name $name `
    --collect-submodules elevendash --collect-data elevendash `
    --workpath "$out\work" --specpath "$out\work" --distpath "$out\dist" `
    (Join-Path $PSScriptRoot 'entry.py')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
$exe = Join-Path "$out\dist\$name" "$name.exe"

# 1. The command line inside the exe: the demo writes a whole dashboard (every module and the page files are in).
$t = Join-Path $out 'check'
$p = Start-Process $exe -ArgumentList 'demo', "`"$t\demo`"" -PassThru -Wait
if ($p.ExitCode -or -not (Test-Path "$t\demo\site\index.html")) { throw "the demo did not build (exit $($p.ExitCode))" }

# 2. The app: it starts, answers on this computer only, and serves the dashboard with its bar.
$p = Start-Process $exe -ArgumentList '--dir', "`"$t\demo`"", 'app', '--no-browser', '--port', '8799' -PassThru
try {
    $ok = $false
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8799/ -TimeoutSec 5
            $ok = $r.Content.Contains('id="ed-app"')
            break
        } catch { }
    }
    if (-not $ok) { throw 'the app did not answer' }
} finally {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

$zip = Join-Path $out 'Eleven-Dashboard-windows.zip'
Compress-Archive -Path "$out\dist\$name" -DestinationPath $zip -Force
Write-Output "Built and checked: $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
