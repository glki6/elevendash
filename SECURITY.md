# Security and privacy

Eleven's game logs hold your Eleven and Meta account tokens, your platform user id and name, the names and ids of
people you played online, your location and the headset's device id. elevendash is built so that none of that leaves
your computer: logs stay in your workspace, the dashboard file holds match data only, and the only network requests
are two read-only calls to your own Quest.

## Reporting a problem

Please report privately anything that could expose someone's data, for example:

- the dashboard file, the PDF or the build data containing something from a log beyond match data
- `elevendash redact` leaving an account, people or location value in its output
- elevendash sending anything anywhere other than your own Quest
- a way to make `elevendash fetch` write outside the workspace

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
