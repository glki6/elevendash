## What's new in 1.1.2

- The gear's menu works from the keyboard: Tab moves into it when it opens and on through it, and Shift+Tab goes back.
- The welcome screen has its own light or dark and 中 or Eng switches, and the app opens in what you pick there.
- The page and browser tab are called Eleven Dashboard, with the app's icon.
- The match list shows the date with each match's time.
- See it on a best serve opens Your serves at that serve's row and marks it.
- Clearer wording in a few places: what "best" serves means, where the journal points you, and the Import and phone settings named as the app names them. The Overview mentions your last day only when it holds more than your last session.
- The headset address box reads full-width digits, colons and stops, turns away anything that isn't a real address, and says so plainly when the port number is out of range. Started again right after Stop, the app waits a moment for its usual port instead of failing.
- At phone width the Older and Newer buttons stay together, and Jump to moves out of the way as you scroll down.
- Screen readers hear an import's stage once instead of every log line, and the gear says when it has something new to read.
- The demo's shots are met at realistic times after the bounce, so Time from the bounce and Still rising have something to show. The README and website screenshots match the updated demo.
- For contributors: the pre-push leak check no longer flags screenshots by chance.

## What's new in 1.1.1

- The welcome screen follows your language and theme, says when it is checking the connection, and shows import progress and results under its own buttons. If an import fails, you can try again from there.
- Logs with no finished match keep you on the welcome screen and say why, instead of opening an empty dashboard.
- Rolling results, Your floor and Recent form work from 10 matches when you don't have 20 yet, and Patterns shows something sooner.
- Errors read as plain sentences that say what went wrong, without technical wording.
- Reading the settings no longer fails when it catches the file halfway through being saved.

## Eleven Dashboard for Windows

1. Download **Eleven-Dashboard-windows.zip** below and unzip it anywhere (Documents, for example).
2. Open the folder and double-click **Eleven Dashboard.exe**. The app isn't code-signed, so Windows may show "Windows protected your PC" the first time: choose **More info**, then **Run anyway**.
3. The app opens in your browser on a welcome screen. On the headset, start File Sharing in Eleven (**Settings › Network Settings › File Sharing**). Type the address it shows into the welcome screen, press **Check the connection**, then **Import the logs**.
4. Your dashboard opens. After every session, press **Import new logs** (behind the gear button at the top). Under the gear's **Settings**, **Add to Start menu and desktop** lets you open the app from there next time.

Your logs and results are kept in `Documents\elevendash` on your computer. Nothing is uploaded anywhere.

**Updating:** stop the old app (**Settings › Stop the app**), then unzip this one over it. Your data is not in the app's folder, so it stays as it is.

**Checking the download:** `Eleven-Dashboard-windows.zip.sha256` below holds the zip's SHA-256; compare it with `Get-FileHash Eleven-Dashboard-windows.zip` in PowerShell. The zip also has a build attestation: `gh attestation verify Eleven-Dashboard-windows.zip --repo glki6/elevendash`.

On macOS or Linux, or on Windows with Python 3.10 or newer: `pipx install git+https://github.com/glki6/elevendash`, then `elevendash app`. See the README.
