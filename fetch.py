#!/usr/bin/env python3
"""
Gather everything the morning brief needs in one go, so the model reads one
digest instead of making a dozen network calls.

    python3 fetch.py OUTDIR                 # weather, stocks, indices, every feed
    python3 fetch.py OUTDIR --only feeds    # or weather, stocks
    python3 fetch.py article OUTDIR URL...  # plain text of article pages, one file each

Writes OUTDIR/fetch.json (everything, machine-readable) and OUTDIR/digest.txt
(what to read: weather, prices, then feed items per section with date, title,
link and a short description, newest first, within each section's window).
Failures are listed at the top of the digest, never hidden. Python 3 standard
library only; sources come from sources.json next to this file.
"""
import concurrent.futures as cf
import email.utils
import html
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
SGT = ZoneInfo("Asia/Singapore")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 25

# Section key in sources.json -> (hours of freshness, max items to show in the digest)
WINDOWS = {
    "apple_official": (72, 15),
    "apple_9to5mac": (48, 25),
    "apple_macrumors": (48, 25),
    "singapore": (48, 40),
    "india": (48, 40),
    "world": (48, 40),
    "ai_singapore": (48, 30),
    "ai_startups_sea": (168, 40),
    "ai_worldwide": (48, 60),
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def get(url: str, ua: str = UA, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def try_get(url: str, **kw):
    """Return (bytes, None) or (None, 'reason')."""
    try:
        return get(url, **kw), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # URLError, timeout, TLS
        return None, type(e).__name__ + (f": {e}" if str(e) else "")


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

def icon_from_wmo(code: int, icon_map: dict) -> str:
    for rng, icon in icon_map.items():
        lo, _, hi = rng.partition("-")
        if int(lo) <= code <= int(hi or lo):
            return icon
    return "cloudy"


def icon_from_metno(symbol: str, icon_map: dict) -> str:
    base = symbol.split("_")[0]  # strip _day / _night / _polartwilight
    if "thunder" in base:
        return "thunder"
    if base in icon_map:
        return icon_map[base]
    if "rain" in base or "sleet" in base:
        return "rain" if "heavy" in base else "showers"
    if "snow" in base:
        return "rain"
    return "cloudy"


def weather_metno(city: dict, w: dict) -> dict:
    url = w["fallback_api"].format(lat=city["lat"], lon=city["lon"])
    raw = get(url, ua="morning-brief/1.0 github.com/rizwankhanmk/morning-brief")
    return parse_metno(json.loads(raw), city, w)


def parse_metno(data: dict, city: dict, w: dict) -> dict:
    tz = ZoneInfo(city["tz"])
    today = datetime.now(tz).date()
    temps, symbols = [], []
    for ts in data["properties"]["timeseries"]:
        t = datetime.fromisoformat(ts["time"].replace("Z", "+00:00")).astimezone(tz)
        if t.date() != today:
            continue
        d = ts["data"]
        temps.append(d["instant"]["details"]["air_temperature"])
        sym = (d.get("next_6_hours") or d.get("next_1_hours") or {}).get("summary", {}).get("symbol_code")
        if sym and 7 <= t.hour <= 19:
            symbols.append(sym)
    if not temps:
        raise ValueError("met.no returned no hours for today")
    icon = "cloudy"
    if symbols:
        ranked = {s: symbols.count(s) for s in symbols}
        icon = icon_from_metno(max(ranked, key=ranked.get), w["metno_icon_map"])
    return {"city": city["city"], "icon": icon, "high": round(max(temps)), "low": round(min(temps)), "source": "met.no"}


def weather_openmeteo(city: dict, w: dict) -> dict:
    url = w["api"].format(lat=city["lat"], lon=city["lon"], tz=city["tz"])
    return parse_openmeteo(json.loads(get(url)), city, w)


def parse_openmeteo(data: dict, city: dict, w: dict) -> dict:
    if "daily" not in data:
        raise ValueError(data.get("reason") or "no daily block")
    d = data["daily"]
    return {"city": city["city"], "icon": icon_from_wmo(int(d["weather_code"][0]), w["icon_map"]),
            "high": round(float(d["temperature_2m_max"][0])), "low": round(float(d["temperature_2m_min"][0])),
            "source": "Open-Meteo"}


def fetch_weather(failures: list) -> list:
    w = SOURCES["weather"]
    out = []
    for city in w["cities"]:
        for fn in (weather_metno, weather_openmeteo):
            try:
                out.append(fn(city, w))
                break
            except Exception as e:
                failures.append(f"weather {city['city']} via {fn.__name__}: {type(e).__name__}: {str(e)[:80]}")
    return out


# ---------------------------------------------------------------------------
# Stocks and indices
# ---------------------------------------------------------------------------

def parse_yahoo(data: dict) -> dict:
    res = data["chart"]["result"][0]
    tz = ZoneInfo(res["meta"].get("exchangeTimezoneName", "UTC"))
    closes = res["indicators"]["quote"][0]["close"]
    stamps = res["timestamp"]
    rows = [(s, c) for s, c in zip(stamps, closes) if c is not None]
    # Drop a bar for a session still in progress: its timestamp is today and the
    # market has not closed, so prefer the previous complete bar.
    now = datetime.now(tz)
    if len(rows) >= 2 and datetime.fromtimestamp(rows[-1][0], tz).date() == now.date() and res["meta"].get("currentTradingPeriod"):
        close_at = res["meta"]["currentTradingPeriod"]["regular"]["end"]
        if now.timestamp() < close_at:
            rows = rows[:-1]
    if len(rows) < 2:
        raise ValueError("fewer than two closes")
    (t0, prev), (t1, last) = rows[-2], rows[-1]
    return {"price": round(last, 2), "prev": round(prev, 2), "change": round(last - prev, 2),
            "change_pct": round((last - prev) / prev * 100, 2),
            "close_date": datetime.fromtimestamp(t1, tz).strftime("%A %-d %B"),
            "prev_date": datetime.fromtimestamp(t0, tz).strftime("%A %-d %B")}


def fetch_quotes(entries: list, failures: list, kind: str) -> list:
    out = []
    for t in entries:
        url = SOURCES["stocks"]["yahoo_chart"].format(yahoo=t["yahoo"])
        raw, err = try_get(url)
        if err:
            failures.append(f"{kind} {t['display']}: {err}")
            continue
        try:
            q = parse_yahoo(json.loads(raw))
        except Exception as e:
            failures.append(f"{kind} {t['display']}: {type(e).__name__}: {str(e)[:80]}")
            continue
        out.append({"ticker": t["display"], "name": t["name"], "currency": t.get("currency", ""), **q})
    return out


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def clean(text: str, limit: int = 220) -> str:
    text = html.unescape(TAG.sub(" ", text or ""))
    text = WS.sub(" ", text).strip()
    return text[:limit].rsplit(" ", 1)[0] + "…" if len(text) > limit else text


def parse_date(value: str):
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        v = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None


def local(el, *names):
    """First child whose local tag name is one of names, ignoring namespaces.
    (Elements without children are falsy, so never chain these with `or`.)"""
    for name in names:
        for child in el:
            if child.tag.split("}")[-1] == name:
                return child
    return None


def text_of(el) -> str:
    return (el.text or "") if el is not None else ""


def parse_feed(raw: bytes) -> list:
    root = ET.fromstring(raw)
    items = []
    channel = local(root, "channel")
    if channel is not None:  # RSS 2.0
        for it in channel:
            if it.tag.split("}")[-1] != "item":
                continue
            items.append({"title": clean(text_of(local(it, "title")), 200),
                          "link": text_of(local(it, "link")).strip(),
                          "date": parse_date(text_of(local(it, "pubDate", "date"))),
                          "desc": clean(text_of(local(it, "description")))})
    else:  # Atom
        for it in root:
            if it.tag.split("}")[-1] != "entry":
                continue
            href = ""
            for l in it:
                if l.tag.split("}")[-1] == "link" and l.get("rel", "alternate") == "alternate":
                    href = l.get("href", ""); break
            items.append({"title": clean(text_of(local(it, "title")), 200), "link": href,
                          "date": parse_date(text_of(local(it, "published", "updated"))),
                          "desc": clean(text_of(local(it, "summary", "content")))})
    return items


def fetch_feed(key: str, url: str):
    raw, err = try_get(url)
    if err:
        return key, url, None, err
    try:
        items = parse_feed(raw)
    except ET.ParseError as e:
        return key, url, None, f"not a feed ({e})"
    return key, url, items, None


def fetch_feeds(failures: list) -> dict:
    jobs = [(k, u) for k in WINDOWS for u in SOURCES.get(k, []) if u.startswith("http")]
    now = datetime.now(timezone.utc)
    out = {k: [] for k in WINDOWS}
    with cf.ThreadPoolExecutor(8) as ex:
        for key, url, items, err in ex.map(lambda j: fetch_feed(*j), jobs):
            if err:
                failures.append(f"feed {key} {url}: {err}")
                continue
            hours, _ = WINDOWS[key]
            host = re.sub(r"^www\.", "", url.split("/")[2])
            fresh = [dict(i, feed=host) for i in items if i["date"] and now - i["date"] <= timedelta(hours=hours)]
            if not fresh:
                failures.append(f"feed {key} {url}: reachable but nothing in the last {hours}h")
            out[key].extend(fresh)
    for k in out:
        seen = set(); dedup = []
        for i in sorted(out[k], key=lambda i: i["date"], reverse=True):
            if i["link"] in seen:
                continue
            seen.add(i["link"]); dedup.append(i)
        out[k] = dedup
    return out


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

def article_text(raw: bytes, limit: int = 6000) -> str:
    t = raw.decode("utf-8", errors="ignore")
    t = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav|aside)[^>]*>.*?</\1>", " ", t)
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", t)
    body = m.group(1) if m else t
    paras = [clean(p, 10_000) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", body)]
    paras = [p for p in paras if len(p) > 40]
    text = "\n".join(paras) if paras else clean(body, limit)
    return text[:limit]


def fetch_articles(outdir: pathlib.Path, urls: list):
    outdir.mkdir(parents=True, exist_ok=True)
    for n, url in enumerate(urls, 1):
        raw, err = try_get(url)
        path = outdir / f"article-{n}.txt"
        if err:
            path.write_text(f"FAILED {url}\n{err}\n", encoding="utf-8")
            print(f"{path}: FAILED {err} {url}")
            continue
        text = article_text(raw)
        path.write_text(f"{url}\n\n{text}\n", encoding="utf-8")
        print(f"{path}: {len(text)} chars {url}")


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

def digest(data: dict) -> str:
    out = [f"MORNING BRIEF FETCH, {datetime.now(SGT).strftime('%A %-d %B %Y %H:%M')} Singapore time", ""]
    if data["failures"]:
        out += ["FAILURES (use web search for anything listed here):"] + [f"  - {f}" for f in data["failures"]] + [""]
    out.append("WEATHER")
    for w in data["weather"]:
        out.append(f"  {w['city']}: {w['icon']} {w['high']}/{w['low']} ({w['source']})")
    out += ["", "STOCKS (most recent completed close, previous close)"]
    for s in data["stocks"] + data["indices"]:
        out.append(f"  {s['ticker']:8} {s['currency']}{s['price']:,.2f}  {s['change']:+.2f} ({s['change_pct']:+.2f}%)  close {s['close_date']}, previous {s['prev_date']}")
    for key, items in data["feeds"].items():
        hours, limit = WINDOWS[key]
        out += ["", f"== {key.upper()}  ({len(items)} fresh items in the last {hours}h; showing {min(len(items), limit)})"]
        for i in items[:limit]:
            when = i["date"].astimezone(SGT).strftime("%a %d %b %H:%M")
            out.append(f"  [{when}] {i['title']}  <{i['feed']}>")
            out.append(f"      {i['link']}")
            if i["desc"]:
                out.append(f"      {i['desc']}")
    return "\n".join(out) + "\n"


def main(argv):
    if argv and argv[0] == "article":
        if len(argv) < 3:
            sys.exit("usage: python3 fetch.py article OUTDIR URL...")
        fetch_articles(pathlib.Path(argv[1]), argv[2:])
        return
    if not argv:
        sys.exit("usage: python3 fetch.py OUTDIR [--only weather|stocks|feeds]")
    outdir = pathlib.Path(argv[0]); outdir.mkdir(parents=True, exist_ok=True)
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    failures = []
    data = {"generated": datetime.now(SGT).isoformat(timespec="minutes"), "weather": [], "stocks": [], "indices": [], "feeds": {}, "failures": failures}
    if only in (None, "weather"):
        data["weather"] = fetch_weather(failures)
    if only in (None, "stocks"):
        data["stocks"] = fetch_quotes(SOURCES["stocks"]["tickers"], failures, "stock")
        data["indices"] = fetch_quotes(SOURCES["stocks"].get("indices", []), failures, "index")
    if only in (None, "feeds"):
        data["feeds"] = fetch_feeds(failures)
    text = digest(data)
    (outdir / "digest.txt").write_text(text, encoding="utf-8")
    (outdir / "fetch.json").write_text(json.dumps(data, default=str, indent=1, ensure_ascii=False), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
