# morning-brief

A Claude scheduled task that emails me a morning brief every day and archives each issue in this repo.

Each issue has: today's weather for Singapore and Navi Mumbai, AAPL, GOOGL and DBS closing prices, a paragraph on what Apple announced plus two stories each from 9to5Mac and MacRumors, five Singapore stories, five from India, five from the rest of the world, a paragraph on AI in Singapore, up to three AI startup stories from Singapore and Southeast Asia, and eight AI stories from around the world grouped into models and products, money, and policy and chips. Every story is a 3 to 5 line summary with the source name as a link.

The design never changes between issues: it lives in `template.html`, and `build.py` only fills in the content.

## Set-up (about 15 minutes, once)

### 1. Put these files on GitHub

Create a new repository called `morning-brief` (private, because `sources.json` holds the recipient address), then from this folder:

```
git init
git add .
git commit -m "morning brief: template, builder, prompt"
git branch -M main
git remote add origin https://github.com/rizwankhanmk/morning-brief.git
git push -u origin main
```

Put your address in `recipient` in `sources.json`.

### 2. Create the scheduled task

1. Go to https://claude.ai/code/routines and click **New task**, then **Set up manually**.
2. Name it `Morning brief`.
3. Prompt: the single line `Read PROMPT.md in this repository and do the job it describes.` The real instructions live in `PROMPT.md`, so later edits on `main` take effect without touching the task.
4. Model: pick the strongest model offered. The default model keeps bending the length and "send the HTML unchanged" rules.
5. Trigger: **Schedule**, daily, **7:15 am** Singapore time. Keep it on a minute no other task of yours uses; two tasks on the same minute have coincided with missed runs.
6. **Advanced settings > General > Repository**: select `rizwankhanmk/morning-brief`.
7. **Cloud environment**: click the environment name, open its settings, set **Network access** to **Full**. (The default only allows package registries, so the news sites would be blocked. You can tighten this to a custom list later; the hosts are in `sources.json` plus `query1.finance.yahoo.com`, `api.open-meteo.com` and `api.met.no`.)
8. **Connectors** tab: keep **Gmail**, remove everything else.
9. **Notifications**: turn on both push and email, so a run that could not send still reaches you.
10. Click **Create**, then **Run now** on the task page.

### 3. Check the first run

Open the run from the task page and read the transcript. A green tick only means the session finished; the last message says whether the brief was pushed and the email went out. If a feed was blocked you will see it there.

Then check your inbox, and look for the `briefs` branch on GitHub.

## How a run protects itself

- It stops before doing anything if `briefs/DATE.json` already exists on the `briefs` branch, so a manual "Run now" and the schedule cannot both send.
- It pushes the archive before it sends the email, so a missing Gmail connector costs you the email but never the issue.
- The builder prints warnings for wrong counts, short or long summaries, homepage links, misspelled outlet names and stories repeated from the previous day, and the prompt tells the run to fix them before sending.

## Weather

The top line shows today's high and low for Singapore and Navi Mumbai with a weather emoji, fetched from Open-Meteo (free, no key). Open-Meteo rate-limits the shared cloud address some days, so met.no is the fallback; both are in `sources.json`.

## Changing the design or the rules

Edit `template.html` (and the few colour tokens at the top of `build.py` if you change colours), run `python3 build.py briefs/2026-10-21.json`, open the HTML, and commit to `main`. The next run picks it up. The content rules are in `PROMPT.md` and `CLAUDE.md`; the expected counts and word ranges are near the top of `build.py`.

## Where things land

- `briefs/YYYY-MM-DD.json` — the day's content
- `briefs/YYYY-MM-DD.html` — the email as sent
- `briefs/YYYY-MM-DD.txt` — plain-text version

Daily runs push to the `briefs` branch, so `main` only ever contains changes I made myself. The `briefs` branch also carries an old copy of the builder and template; that is harmless, because each run builds on a fresh checkout of `main` before switching branches to commit.
