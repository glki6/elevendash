# Run one scroll test in a private headless Firefox (its own empty profile), then close that instance only.
# -Work is the folder server.py writes out.jsonl to; the throwaway profile is made there too. Never the person's own Firefox profile.
param([string]$Url, [string]$Work, [int]$Width = 1145, [int]$Height = 563, [int]$Wait = 60)
$prof = Join-Path $Work 'prof'
$out = Join-Path $Work 'out.jsonl'
function Stop-Test {
  Get-CimInstance Win32_Process -Filter "Name='firefox.exe'" | Where-Object { $_.CommandLine -like "*$prof*" } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
}
Stop-Test
Start-Sleep -Milliseconds 800
if (Test-Path $out) { Remove-Item $out -Force -Confirm:$false }
# a fresh profile every run: after several forced stops Firefox would otherwise open its safe-mode prompt
if (Test-Path $prof) { Remove-Item $prof -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force $prof | Out-Null
Set-Content -Path (Join-Path $prof 'user.js') -Encoding ascii -Value @('user_pref("toolkit.startup.max_resumed_crashes", -1);', 'user_pref("browser.sessionstore.resume_from_crash", false);', 'user_pref("browser.shell.checkDefaultBrowser", false);', 'user_pref("datareporting.policy.dataSubmissionEnabled", false);', 'user_pref("app.update.enabled", false);')
$env:MOZ_HEADLESS_WIDTH = "$Width"
$env:MOZ_HEADLESS_HEIGHT = "$Height"
$p = Start-Process -FilePath 'C:\Program Files\Mozilla Firefox\firefox.exe' -ArgumentList @('--headless', '--no-remote', '--profile', "`"$prof`"", $Url) -PassThru
for ($i = 0; $i -lt $Wait; $i++) {
  Start-Sleep -Seconds 1
  if ((Test-Path $out) -and (Select-String -Path $out -Pattern '"step":"done"' -Quiet)) { break }
}
Stop-Test
# also by process tree: the launcher can hide the command line of the instance it starts
$kids = @($p.Id); $all = Get-CimInstance Win32_Process -Filter "Name='firefox.exe'"
for ($k = 0; $k -lt 4; $k++) { $kids += ($all | Where-Object { $kids -contains $_.ParentProcessId }).ProcessId }
$kids | Select-Object -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }
Write-Output "waited $i s"
