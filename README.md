# morning-brief

A Claude scheduled task that emails me a morning brief every day and archives each issue in this repo.

Each issue has: today's weather for Singapore and Navi Mumbai, AAPL, GOOGL and DBS closing prices, nine Apple stories (official, wider coverage, 9to5Mac), five Singapore stories, five from India, five from the rest of the world, and five each on AI in Singapore, the US, and China/worldwide. Every story is a 3 to 5 line summary with the source name as a link.

The design never changes between issues: it lives in `template.html`, and `build.py` only fills in the content.

## Set-up (about 15 minutes, once)

### 1. Put these files on GitHub

Create a new repository called `morning-brief` (private is fine), then from this folder:

```
git init
git add .
git commit -m "morning brief: template, builder, prompt"
git branch -M main
git remote add origin https://github.com/rizwankhanmk/morning-brief.git
git push -u origin main
```

### 2. Create the scheduled task

1. Go to https://claude.ai/code/routines and click **New task**, then **Set up manually**.
2. Name it `Morning brief`.
3. Open `PROMPT.md`, replace the two `<<...>>` placeholders, and paste everything below the line into the prompt box. Pick a strong model.
4. Trigger: **Schedule**, daily, **6:37 am** Singapore time (a few minutes past the hour so it starts on time).
5. **Advanced settings > General > Repository**: select `rizwankhanmk/morning-brief`.
6. **Cloud environment**: click the environment name, open its settings, set **Network access** to **Full** for now. (The default only allows package registries, so the news sites would be blocked. You can tighten this to a custom list later; the hosts are in `sources.json` plus `query1.finance.yahoo.com`.)
7. **Connectors** tab: keep **Gmail**, remove everything else.
8. Click **Create**, then **Run now** on the task page.

### 3. Check the first run

Open the run from the task page and read the transcript. A green tick only means the session finished; the transcript shows whether the email went out and the push succeeded. If a feed was blocked you will see it there.

Then check your inbox, and look for the `briefs` branch on GitHub.

## Weather

The top line shows today's high and low for Singapore and Navi Mumbai with a weather emoji, fetched from Open-Meteo (free, no key). If you use a custom network allowlist instead of Full access, add `api.open-meteo.com`.

## Changing the design

Edit `template.html` (and the few colour tokens at the top of `build.py` if you change colours), run `python3 build.py briefs/2026-10-21.json`, open the HTML, and commit to `main`. The next run picks it up.

## Where things land

- `briefs/YYYY-MM-DD.json` — the day's content
- `briefs/YYYY-MM-DD.html` — the email as sent
- `briefs/YYYY-MM-DD.txt` — plain-text version

Daily runs push to the `briefs` branch, so `main` only ever contains changes I made myself.
