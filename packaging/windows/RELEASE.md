## Eleven Dashboard for Windows

1. Download **Eleven-Dashboard-windows.zip** below and unzip it anywhere (Documents, for example).
2. Open the folder and double-click **Eleven Dashboard.exe**. The app isn't code-signed, so Windows may show "Windows protected your PC" the first time: choose **More info**, then **Run anyway**.
3. The app opens in your browser on a welcome screen. On the headset, start File Sharing in Eleven (**Settings › Network Settings › File Sharing**). Type the address it shows into the welcome screen, press **Check the connection**, then **Import the logs**.
4. Your dashboard opens. After every session, press **Import new logs** (behind the gear button at the top). Under the gear's **Settings**, **Add to Start menu and desktop** lets you open the app from there next time.

Your logs and results are kept in `Documents\elevendash` on your computer. Nothing is uploaded anywhere.

**Updating:** stop the old app (**Settings › Stop the app**), then unzip this one over it. Your data is not in the app's folder, so it stays as it is.

**Checking the download:** `Eleven-Dashboard-windows.zip.sha256` below holds the zip's SHA-256; compare it with `Get-FileHash Eleven-Dashboard-windows.zip` in PowerShell. The zip also has a build attestation: `gh attestation verify Eleven-Dashboard-windows.zip --repo glki6/elevendash`.

On macOS or Linux, or on Windows with Python 3.10 or newer: `pipx install git+https://github.com/glki6/elevendash`, then `elevendash app`. See the README.
