# Security and privacy

Eleven's game logs hold your Eleven and Meta account tokens, your platform user id and name, the names and ids of
people you played online, your location and the headset's device id. elevendash is built so that none of that leaves
your computer: logs stay in your workspace, the dashboard file holds match data only, and the only network requests
are two read-only calls to your own Quest.

The app (`elevendash app`) runs a small web server for your browser. It listens on 127.0.0.1 only, refuses requests
whose Host is not its own address, and answers its import, settings and notes calls only when they carry a key that
is new each time it starts and is known only to the pages it served.

The phone link (**Settings › Phone**) is off until you turn it on. Then a second server listens on this computer's
Tailscale address only (100.64.0.0/10), so only devices signed in to your tailnet can reach it, over Tailscale's
encrypted connection; it is never on your Wi-Fi or the internet. Every request to it must also carry the phone key,
from the link or QR code or from the cookie the first visit leaves (HttpOnly, SameSite=Strict). **New link** makes a
new key and the old link stops working. From the phone you can import and change settings, but not back up, restore,
export or share, open folders, make shortcuts or change the phone link, and the phone is never told where your files
are.

## Reporting a problem

Please report privately anything that could expose someone's data, for example:

- the dashboard file, the PDF or the build data containing something from a log beyond match data
- `elevendash redact` leaving an account, people or location value in its output
- elevendash sending anything anywhere other than your own Quest
- a way to make `elevendash fetch`, or an import in the app, write outside the workspace
- a way for another computer, or a website open in your browser, to use the app's server

Use GitHub's private vulnerability reporting (the **Security** tab, then **Report a vulnerability**). Don't open a
public issue for these.

## Never attach a raw log

Not to an issue, a pull request, a discussion or a message. If a log is needed to show a problem, make a redacted
copy first and read it before you share it:

```
elevendash redact logs/ALL-01.05.2026.6.30.00.PM.log redacted.log
```

If your account token was ever in something you shared, sign out of Eleven on the headset and sign in again so the
old token stops working.
