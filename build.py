#!/usr/bin/env python3
"""
Render a morning brief from JSON into the fixed HTML email template.

    python3 build.py briefs/2026-10-21.json
    python3 build.py briefs/2026-10-22.json --previous /tmp/previous.json

Writes, next to the JSON:
    DATE.html         the email (send as htmlBody, unmodified)
    DATE.txt          plain-text twin (send as body)
    DATE.short.txt    six-line digest for chat apps
    DATE.spoken.txt   a two-minute read-aloud script

Python 3 standard library only. The look lives in template.html; this file
only lays out the content. Do not restyle here.

After rendering it prints warnings (shape for the weekday, summary lengths,
links, outlet names, repeats from the previous brief). Warnings never block
the build; the scheduled prompt says which ones to fix.
"""
import html
import json
import pathlib
import sys
import urllib.parse
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))

# Tokens (keep in step with template.html)
INK = "#1D1D1F"
SOFT = "#6E6E73"
LINK = "#0071E3"
UP = "#1F8A4C"
DOWN = "#C8372D"
HAIR = "#E5E5EA"
FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Weather shows as a plain emoji (renders natively in every mail app, no images).
WEATHER_EMOJI = {"sun": "☀️", "partly-cloudy": "\U0001f324️", "cloudy": "☁️",
                 "showers": "\U0001f326️", "rain": "\U0001f327️", "thunder": "⛈️", "haze": "\U0001f32b️"}

# One colour per section: used for the section title and its group labels.
SECTION_COLOURS = {
    "The week in five": "#2F6FBF",
    "The week ahead": "#8A6D1F",
    "Apple": "#0071E3",
    "Singapore": "#D23B2F",
    "India": "#E0861B",
    "World": "#1E8E5A",
    "Explainer": "#5B5BD6",
    "AI in Singapore": "#7B4FD9",
    "AI startups in Singapore and Southeast Asia": "#C2367F",
    "AI worldwide": "#0E8C9E",
}

# ---------------------------------------------------------------------------
# Shape of an issue, by weekday. Checked after rendering (warnings only).
#   int                 -> exactly that many items
#   {"_brief": True}    -> a 'brief' paragraph, no items
#   {"_total": n}       -> exactly n items across the groups
#   {"_min": a, "_max": b} -> between a and b items across the groups
#   {label: n, ...}     -> exactly n items in each named group
# ---------------------------------------------------------------------------
WEEKDAY_SHAPE = {
    "Apple": {"9to5Mac": 2, "MacRumors": 2},
    "Singapore": 4,
    "India": 4,
    "World": 4,
    "Explainer": {"_brief": True},
    "AI in Singapore": {"_brief": True},
    "AI worldwide": {"_total": 8},
}
WEEKEND_SHAPE = {
    "Apple": {"9to5Mac": 1, "MacRumors": 1},
    "Singapore": 3,
    "India": 3,
    "World": 3,
    "Explainer": {"_brief": True},
    "AI in Singapore": {"_brief": True},
    "AI worldwide": {"_total": 5},
}
# Sections that appear on one weekday only (0 = Monday ... 6 = Sunday).
DAY_SECTIONS = {
    0: ("AI startups in Singapore and Southeast Asia", {"_min": 3, "_max": 5}),
    4: ("The week in five", 5),
    6: ("The week ahead", {"_min": 3, "_max": 6}),
}
ORDER = ["The week in five", "The week ahead", "Apple", "Singapore", "India", "World", "Explainer",
         "AI in Singapore", "AI startups in Singapore and Southeast Asia", "AI worldwide"]
GROUP_LABELS = {
    "AI startups in Singapore and Southeast Asia": ["Funding", "Hiring", "What they're building"],
    "AI worldwide": ["Models and products", "Money", "Policy and chips"],
}

# Writing rules (words).
ITEM_WORDS = (35, 60)
PARA_WORDS = (45, 65)
EXPLAINER_WORDS = {"weekday": (150, 250), "saturday": (250, 350)}
TODAY_WORDS = (8, 45)
WHY_WORDS = (8, 30)
MAX_WHY = 3
CONFIDENCE = {"single-source": "Single source", "unverified": "Unverified", "contested": "Contested"}

FOOTER = ("Built by your morning-brief agent at {time} Singapore time. "
          "Prices from Yahoo Finance; summaries written from the linked sources.")


def shape_for(d: date) -> dict:
    base = dict(WEEKEND_SHAPE if d.weekday() >= 5 else WEEKDAY_SHAPE)
    extra = DAY_SECTIONS.get(d.weekday())
    if extra:
        base[extra[0]] = extra[1]
    return base


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def nice_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%A, %-d %B %Y")


def short_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a %-d %b")


def singapore_time() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).strftime("%-I:%M%p").lower()


def footer_text(data) -> str:
    custom = data.get("footer", "")
    text = custom if "{time}" in custom else FOOTER
    text = text.replace("{time}", singapore_time())
    applied = [a for a in data.get("applied", []) if a]
    if applied:
        text += " From your replies: " + "; ".join(applied) + "."
    return text


def all_items(section):
    items = list(section.get("items", []))
    for g in section.get("groups", []):
        items.extend(g.get("items", []))
    return items


def thread_titles(data) -> dict:
    return {t["id"]: t["title"] for t in data.get("threads", []) if t.get("id")}


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def render_weather(weather) -> str:
    if not weather:
        return ""
    blocks = []
    for i, w in enumerate(weather):
        emoji = WEATHER_EMOJI.get(w.get("icon", "cloudy"), WEATHER_EMOJI["cloudy"])
        hi = int(round(float(w["high"])))
        lo = int(round(float(w["low"])))
        margin = "0" if i == 0 else "22px"
        blocks.append(
            f"""<span style="display:inline-block;vertical-align:middle;white-space:nowrap;margin-left:{margin};text-align:left;">"""
            f"""<span style="display:inline-block;vertical-align:middle;font-size:26px;line-height:1;margin-right:7px;">{emoji}</span>"""
            f"""<span style="display:inline-block;vertical-align:middle;line-height:1.25;">"""
            f"""<span style="font-family:{FONT};font-size:11px;font-weight:500;color:{SOFT};">{esc(w['city'])}</span><br>"""
            f"""<span style="font-family:{FONT};font-size:15px;font-weight:600;color:{INK};">{hi}&deg;<span style="font-weight:400;color:{SOFT};"> / {lo}&deg;</span></span>"""
            f"""</span></span>"""
        )
    return "            " + "".join(blocks)


def render_today(today: str) -> str:
    if not today:
        return ""
    return (f"""
            <p style="margin:-14px 0 22px 0;font-family:{FONT};font-size:14px;line-height:1.5;color:{INK};">"""
            f"""<span style="font-weight:600;">Today</span>&nbsp; {esc(today)}</p>""")


def render_threads(threads) -> str:
    live = [t for t in threads if t.get("status")]
    if not live:
        return ""
    rows = []
    for t in live:
        day = f""" <span style="font-weight:400;color:{SOFT};">day {int(t['day'])}</span>""" if t.get("day") else ""
        rows.append(f"""
              <tr><td style="padding:0 0 8px 0;font-family:{FONT};font-size:13px;line-height:1.5;color:{SOFT};">"""
                    f"""<span style="font-weight:600;color:{INK};">{esc(t['title'])}</span>{day} &nbsp;{esc(t['status'])}</td></tr>""")
    return f"""
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:0 0 20px 0;border-left:3px solid {HAIR};">
              <tr><td style="padding:0 0 6px 12px;font-family:{FONT};font-size:11px;line-height:1.4;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;color:{SOFT};">Still developing</td></tr>
              {''.join(r.replace('<td style="padding:0 0 8px 0;', '<td style="padding:0 0 8px 12px;') for r in rows)}
            </table>"""


def render_indices(indices) -> str:
    if not indices:
        return ""
    parts = []
    for s in indices:
        pct = float(s["change_pct"])
        colour = UP if pct >= 0 else DOWN
        arrow = "&#9650;" if pct >= 0 else "&#9660;"
        parts.append(f"""<span style="white-space:nowrap;"><span style="font-weight:600;color:{INK};">{esc(s['ticker'])}</span> {float(s['price']):,.2f} """
                     f"""<span style="color:{colour};">{arrow} {pct:+.2f}%</span></span>""")
    sep = """<span style="color:#C7C7CC;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>"""
    return f"""
            <p style="margin:0 0 8px 0;font-family:{FONT};font-size:12px;line-height:1.6;color:{SOFT};">{sep.join(parts)}</p>"""


def render_stocks(stocks, note, indices=None) -> str:
    cells = []
    width = f"{100 // max(len(stocks), 1)}%"
    for s in stocks:
        cur = s.get("currency", "")
        pct = float(s["change_pct"])
        colour = UP if pct >= 0 else DOWN
        arrow = "&#9650;" if pct >= 0 else "&#9660;"  # ▲ ▼
        change = f"{float(s['change']):+.2f}"
        cells.append(
            f"""
            <td width="{width}" valign="top" style="padding:0 6px 0 0;">
              <p style="margin:0 0 3px 0;font-family:{FONT};font-size:12px;line-height:1.4;font-weight:500;color:{SOFT};white-space:nowrap;">{esc(s['ticker'])}</p>
              <p style="margin:0 0 3px 0;font-family:{FONT};font-size:23px;line-height:1.15;font-weight:600;letter-spacing:-0.01em;color:{INK};white-space:nowrap;"><span style="font-size:12px;font-weight:500;color:{SOFT};">{esc(cur)}</span>{float(s['price']):,.2f}</p>
              <p style="margin:0;font-family:{FONT};font-size:12px;line-height:1.4;font-weight:500;white-space:nowrap;color:{colour};">{arrow} {change} ({pct:+.2f}%)</p>
            </td>"""
        )
    return f"""
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:0 0 6px 0;">
              <tr>{''.join(cells)}
              </tr>
            </table>{render_indices(indices)}
            <p style="margin:0 0 26px 0;font-family:{FONT};font-size:12px;line-height:1.5;color:#8E8E93;">{esc(note)}</p>"""


def render_item(item, threads: dict) -> str:
    source = esc(item["source"])
    url = item.get("url", "").strip()
    link = f'<a href="{esc(url)}" style="color:{LINK};text-decoration:none;">{source}</a>' if url else source
    tags = ""
    conf = CONFIDENCE.get(item.get("confidence", ""))
    if conf:
        tags += f"""<span style="color:{SOFT};font-weight:500;"> &middot; {conf}</span>"""
    if item.get("thread") in threads:
        tags += f"""<span style="color:{SOFT};font-weight:500;"> &middot; Part of: {esc(threads[item['thread']])}</span>"""
    extra = ""
    if item.get("why"):
        extra += f"""
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:14px;line-height:1.5;color:{INK};"><span style="font-weight:600;">For you</span>&nbsp; {esc(item['why'])}</p>"""
    if item.get("counter"):
        extra += f"""
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:14px;line-height:1.5;color:{SOFT};"><span style="font-weight:600;">Counter-view</span>&nbsp; {esc(item['counter'])}</p>"""
    return f"""
              <tr>
                <td style="padding:0 0 22px 0;">
                  <p style="margin:0 0 6px 0;font-family:{FONT};font-size:16px;line-height:1.35;font-weight:600;color:{INK};">{esc(item['headline'])}</p>
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:15px;line-height:1.55;color:{SOFT};">{esc(item['summary'])}</p>{extra}
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:500;">{link}{tags}</p>
                </td>
              </tr>"""


def render_brief(brief, colour) -> str:
    srcs = brief.get("sources") or [{"name": brief.get("source", ""), "url": brief.get("url", "")}]
    links = ", ".join(
        f'<a href="{esc(x.get("url",""))}" style="color:{LINK};text-decoration:none;">{esc(x["name"])}</a>' if x.get("url") else esc(x["name"])
        for x in srcs if x.get("name")
    )
    prefix = "Sources: " if len(srcs) > 1 else ""
    label = brief.get("label", "")
    paras = [p.strip() for p in brief["summary"].split("\n") if p.strip()]
    body = "".join(f"""
                  <p style="margin:0 0 10px 0;font-family:{FONT};font-size:15px;line-height:1.55;color:{INK};">{esc(p)}</p>""" for p in paras)
    return (f"""
              <tr>
                <td style="padding:0 0 26px 0;">"""
            + (f"""
                  <p style="margin:0 0 6px 0;font-family:{FONT};font-size:16px;line-height:1.35;font-weight:600;color:{colour};">{esc(label)}</p>""" if label else "")
            + body
            + f"""
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.5;font-weight:500;color:{SOFT};">{prefix}{links}</p>
                </td>
              </tr>""")


def render_section(section, threads: dict) -> str:
    subtitle = section.get("subtitle", "")
    colour = SECTION_COLOURS.get(section["title"], INK)
    out = [
        f"""
              <tr>
                <td style="padding:24px 0 16px 0;border-top:1px solid {HAIR};">
                  <p style="margin:0;font-family:{FONT};font-size:20px;line-height:1.3;font-weight:600;letter-spacing:-0.01em;color:{colour};">{esc(section['title'])}</p>"""
        + (f"""
                  <p style="margin:4px 0 0 0;font-family:{FONT};font-size:13px;line-height:1.4;color:{SOFT};">{esc(subtitle)}</p>""" if subtitle else "")
        + """
                </td>
              </tr>"""
    ]
    brief = section.get("official") or section.get("brief")
    if brief:
        out.append(render_brief(brief, colour))
    if "groups" in section:
        for group in section["groups"]:
            if not group.get("items"):
                continue
            out.append(
                f"""
              <tr>
                <td style="padding:2px 0 12px 0;">
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:600;color:{colour};">{esc(group['label'])}</p>
                </td>
              </tr>"""
            )
            out.extend(render_item(i, threads) for i in group["items"])
    else:
        out.extend(render_item(i, threads) for i in section.get("items", []))
    return "".join(out)


# ---------------------------------------------------------------------------
# Text twins
# ---------------------------------------------------------------------------

def render_text(data, footer) -> str:
    threads = thread_titles(data)
    lines = [f"MORNING BRIEF, {nice_date(data['date'])}", ""]
    for w in data.get("weather", []):
        lines.append(f"{WEATHER_EMOJI.get(w.get('icon',''),'')} {w['city']}: {int(round(float(w['high'])))}° / {int(round(float(w['low'])))}°")
    lines += ["", data.get("lede", "")]
    if data.get("today"):
        lines.append("Today: " + data["today"])
    live = [t for t in data.get("threads", []) if t.get("status")]
    if live:
        lines += ["", "STILL DEVELOPING"]
        for t in live:
            lines.append(f"{t['title']}" + (f" (day {int(t['day'])})" if t.get("day") else "") + f": {t['status']}")
    lines.append("")
    for s in data["stocks"]:
        lines.append(f"{s['ticker']}  {s.get('currency','')}{float(s['price']):,.2f}  {float(s['change']):+.2f} ({float(s['change_pct']):+.2f}%)")
    for s in data.get("indices", []):
        lines.append(f"{s['ticker']}  {float(s['price']):,.2f}  {float(s['change']):+.2f} ({float(s['change_pct']):+.2f}%)")
    lines += [data.get("stocks_note", ""), ""]
    for section in data["sections"]:
        lines += [section["title"].upper(), ""]
        brief = section.get("official") or section.get("brief")
        if brief:
            srcs = brief.get("sources") or [{"name": brief.get("source", ""), "url": brief.get("url", "")}]
            if brief.get("label"):
                lines.append(brief["label"])
            lines += [brief["summary"], "Sources: " + "; ".join(f"{x['name']} {x.get('url','')}".strip() for x in srcs), ""]
        groups = section.get("groups") or [{"label": "", "items": section.get("items", [])}]
        for g in groups:
            if not g.get("items"):
                continue
            if g["label"]:
                lines += [g["label"], ""]
            for i in g["items"]:
                lines += [i["headline"], i["summary"]]
                if i.get("why"):
                    lines.append("For you: " + i["why"])
                if i.get("counter"):
                    lines.append("Counter-view: " + i["counter"])
                tag = []
                if CONFIDENCE.get(i.get("confidence", "")):
                    tag.append(CONFIDENCE[i["confidence"]])
                if i.get("thread") in threads:
                    tag.append("Part of: " + threads[i["thread"]])
                lines += [f"Source: {i['source']} — {i.get('url','')}" + (f"  [{'; '.join(tag)}]" if tag else ""), ""]
    lines += [footer]
    return "\n".join(lines).strip() + "\n"


def render_short(data) -> str:
    """Six-ish lines for a chat app."""
    w = " · ".join(f"{WEATHER_EMOJI.get(x.get('icon',''),'')} {x['city']} {int(round(float(x['high'])))}/{int(round(float(x['low'])))}" for x in data.get("weather", []))
    q = " · ".join(f"{s['ticker']} {float(s['price']):,.2f} ({float(s['change_pct']):+.1f}%)" for s in data["stocks"] + data.get("indices", []))
    tops = []
    for section in data["sections"]:
        items = all_items(section)
        if items:
            tops.append(f"- {items[0]['headline']} ({section['title']})")
    lines = [f"Morning Brief, {short_date(data['date'])}", w, data.get("lede", "")]
    if data.get("today"):
        lines.append("Today: " + data["today"])
    lines += [q, "Top:"] + tops[:6]
    return "\n".join(l for l in lines if l) + "\n"


def render_spoken(data) -> str:
    """A read-aloud script of about two minutes, for text-to-speech."""
    out = [f"Good morning. This is your brief for {nice_date(data['date'])}."]
    ws = [f"{x['city']} {int(round(float(x['high'])))} and {int(round(float(x['low'])))} degrees with {x.get('icon','cloud').replace('-', ' ')}" for x in data.get("weather", [])]
    if ws:
        out.append("Weather: " + "; ".join(ws) + ".")
    out.append(data.get("lede", ""))
    if data.get("today"):
        out.append("Today, " + data["today"])
    live = [t for t in data.get("threads", []) if t.get("status")]
    for t in live[:3]:
        out.append(f"On {t['title']}: {t['status']}")
    for s in data["stocks"]:
        direction = "up" if float(s["change_pct"]) >= 0 else "down"
        out.append(f"{s['name']} closed at {float(s['price']):,.2f}, {direction} {abs(float(s['change_pct'])):.1f} percent.")
    for section in data["sections"]:
        brief = section.get("official") or section.get("brief")
        if section["title"] == "Explainer" and brief:
            out.append(f"Today's explainer, {brief.get('label','')}. {brief['summary'].replace(chr(10), ' ')}")
            continue
        heads = [i["headline"] for i in all_items(section)][:3]
        if heads:
            out.append(f"In {section['title']}: " + " ".join(h.rstrip('.') + "." for h in heads))
    out.append("That's the brief. Links are in the email.")
    return "\n\n".join(o for o in out if o) + "\n"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def warn(msg):
    print(f"warning: {msg}")


def check_shape(data):
    d = date.fromisoformat(data["date"])
    shape = shape_for(d)
    seen = [s["title"] for s in data["sections"]]
    for section in data["sections"]:
        title = section["title"]
        if title not in ORDER:
            warn(f"unexpected section '{title}'")
            continue
        want = shape.get(title)
        n = len(all_items(section))
        if want is None:
            # A day-specific section on the wrong day: allowed (the reference shows them all), but say so.
            for wd, (name, _) in DAY_SECTIONS.items():
                if name == title:
                    warn(f"{title}: usually only on {date(2026, 11, 2 + wd).strftime('%A')}s; fine in the reference, drop it in a real issue")
            continue
        labels = GROUP_LABELS.get(title)
        if labels:
            for g in section.get("groups", []):
                if g["label"] not in labels:
                    warn(f"{title}: unknown group label '{g['label']}' (use one of {labels})")
        if isinstance(want, dict) and want.get("_brief"):
            if not (section.get("brief") or section.get("official")):
                warn(f"{title}: expected a 'brief' paragraph")
            if n:
                warn(f"{title}: has {n} items, expected none (it is a paragraph section)")
        elif isinstance(want, dict) and "_total" in want:
            if n != want["_total"]:
                warn(f"{title}: {n} items, expected {want['_total']} across groups")
        elif isinstance(want, dict) and "_min" in want:
            if n < want["_min"] or n > want["_max"]:
                warn(f"{title}: {n} items, expected {want['_min']} to {want['_max']}")
        elif isinstance(want, dict):
            for g in section.get("groups", []):
                m, w = len(g["items"]), want.get(g["label"])
                if w is not None and m != w:
                    warn(f"{title} / {g['label']}: {m} items, expected {w}")
            if title == "Apple" and not section.get("official"):
                warn("Apple: expected the 'official' paragraph")
        else:
            if n != want:
                warn(f"{title}: {n} items, expected {want} on a {d.strftime('%A')}")
    missing = [t for t in shape if t not in seen]
    if missing:
        warn(f"missing sections for a {d.strftime('%A')}: {missing}")
    if seen != [t for t in ORDER if t in seen]:
        warn(f"sections are out of order; expected {[t for t in ORDER if t in seen]}")


def check_writing(data):
    d = date.fromisoformat(data["date"])
    lo, hi = ITEM_WORDS
    today = data.get("today", "")
    if today and not TODAY_WORDS[0] <= len(today.split()) <= TODAY_WORDS[1]:
        warn(f"today line is {len(today.split())} words, want one sentence of {TODAY_WORDS[0]} to {TODAY_WORDS[1]}")
    if today and "!" in today:
        warn("today line uses an exclamation mark")
    for t in data.get("threads", []):
        n = len(t.get("status", "").split())
        if t.get("status") and not 15 <= n <= 60:
            warn(f"thread '{t.get('title','?')}' status is {n} words, want 15 to 60")
    whys = 0
    for section in data["sections"]:
        title = section["title"]
        brief = section.get("official") or section.get("brief")
        if brief:
            n = len(brief["summary"].split())
            if title == "Explainer":
                lo_e, hi_e = EXPLAINER_WORDS["saturday" if d.weekday() == 5 else "weekday"]
                if not lo_e <= n <= hi_e:
                    warn(f"Explainer is {n} words, want {lo_e} to {hi_e} on a {d.strftime('%A')}")
                if not brief.get("label"):
                    warn("Explainer needs a 'label' (its heading)")
            elif not PARA_WORDS[0] <= n <= PARA_WORDS[1]:
                warn(f"{title}: paragraph is {n} words, want {PARA_WORDS[0]} to {PARA_WORDS[1]}")
        for item in all_items(section):
            n = len(item["summary"].split())
            if not lo <= n <= hi:
                warn(f"{title}: '{item['headline'][:50]}' summary is {n} words, want {lo} to {hi}")
            if "!" in item["headline"] or "!" in item["summary"]:
                warn(f"{title}: '{item['headline'][:50]}' uses an exclamation mark")
            if item.get("why"):
                whys += 1
                m = len(item["why"].split())
                if not WHY_WORDS[0] <= m <= WHY_WORDS[1]:
                    warn(f"{title}: 'For you' line on '{item['headline'][:40]}' is {m} words, want {WHY_WORDS[0]} to {WHY_WORDS[1]}")
            if item.get("confidence") and item["confidence"] not in CONFIDENCE:
                warn(f"{title}: unknown confidence '{item['confidence']}' (use {list(CONFIDENCE)})")
            if item.get("thread") and item["thread"] not in thread_titles(data):
                warn(f"{title}: '{item['headline'][:40]}' names thread '{item['thread']}' which is not in 'threads'")
    if whys > MAX_WHY:
        warn(f"{whys} 'For you' lines; at most {MAX_WHY} per issue")


def check_links_and_sources(data):
    names = set(SOURCES.get("outlet_names", []))
    aliases = {k.lower(): v for k, v in SOURCES.get("outlet_aliases", {}).items()}
    seen_urls = {}
    for section in data["sections"]:
        title = section["title"]
        refs = [(i["source"], i.get("url", ""), i["headline"]) for i in all_items(section)]
        brief = section.get("official") or section.get("brief")
        if brief:
            for x in brief.get("sources") or [{"name": brief.get("source", ""), "url": brief.get("url", "")}]:
                refs.append((x.get("name", ""), x.get("url", ""), "(paragraph source)"))
        for source, url, headline in refs:
            if source.lower() in aliases:
                warn(f"{title}: source '{source}' should be written '{aliases[source.lower()]}'")
            elif names and source not in names:
                warn(f"{title}: source '{source}' is not in sources.json outlet_names (fine if it is a new outlet; otherwise use the listed spelling)")
            if not url:
                warn(f"{title}: '{headline[:50]}' has no url")
                continue
            path = urllib.parse.urlparse(url).path.strip("/")
            if len(path) < 8:
                warn(f"{title}: '{headline[:50]}' links to a homepage or section page, not an article: {url}")
            recap = title in ("Explainer", "The week in five", "The week ahead")
            if url in seen_urls and seen_urls[url] != headline and not recap:
                warn(f"{title}: url already used for '{seen_urls[url][:40]}': {url}")
            if not recap:
                seen_urls.setdefault(url, headline)


def check_previous(data, previous_path):
    try:
        prev = json.loads(pathlib.Path(previous_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        warn(f"could not read previous brief {previous_path}: {e}")
        return
    if prev.get("date") == data.get("date"):
        warn(f"previous brief has the same date ({prev.get('date')}); skipping repeat check")
        return
    old_urls, old_heads = {}, {}
    for section in prev.get("sections", []):
        if section["title"] in ("The week in five", "The week ahead"):
            continue
        for i in all_items(section):
            old_urls[i.get("url", "").strip()] = i["headline"]
            old_heads[i["headline"].strip().lower()] = section["title"]
    for section in data["sections"]:
        if section["title"] in ("The week in five", "The week ahead"):
            continue
        for i in all_items(section):
            url = i.get("url", "").strip()
            if url and url in old_urls:
                warn(f"{section['title']}: '{i['headline'][:50]}' repeats the previous brief ({prev.get('date')}) by url")
            elif i["headline"].strip().lower() in old_heads:
                warn(f"{section['title']}: '{i['headline'][:50]}' repeats a headline from the previous brief ({prev.get('date')})")


# ---------------------------------------------------------------------------

def main(path: str, previous):
    src = pathlib.Path(path)
    data = json.loads(src.read_text(encoding="utf-8"))
    footer = footer_text(data)
    threads = thread_titles(data)

    html_out = (
        TEMPLATE.replace("{{TITLE}}", esc(f"Morning brief, {nice_date(data['date'])}"))
        .replace("{{DATE_LINE}}", esc(nice_date(data["date"])))
        .replace("{{WEATHER}}", render_weather(data.get("weather", [])))
        .replace("{{LEDE}}", esc(data.get("lede", "")) + "</p>" + render_today(data.get("today", "")).lstrip("\n")
                 + render_threads(data.get("threads", [])).lstrip("\n") + "<p style=\"display:none;\">")
        .replace("{{STOCKS}}", render_stocks(data["stocks"], data.get("stocks_note", ""), data.get("indices", [])))
        .replace("{{SECTIONS}}", "".join(render_section(s, threads) for s in data["sections"]))
        .replace("{{FOOTER}}", esc(footer))
    )
    src.with_suffix(".html").write_text(html_out, encoding="utf-8")
    src.with_suffix(".txt").write_text(render_text(data, footer), encoding="utf-8")
    src.with_suffix(".short.txt").write_text(render_short(data), encoding="utf-8")
    src.with_suffix(".spoken.txt").write_text(render_spoken(data), encoding="utf-8")

    check_shape(data)
    check_writing(data)
    check_links_and_sources(data)
    if previous:
        check_previous(data, previous)
    size = len(html_out.encode("utf-8"))
    if size > 100_000:
        warn(f"html is {size:,} bytes; Gmail clips messages above about 102 KB")
    print(f"wrote {src.with_suffix('.html')} ({size:,} bytes), .txt, .short.txt and .spoken.txt")


if __name__ == "__main__":
    args = sys.argv[1:]
    previous = None
    if "--previous" in args:
        i = args.index("--previous")
        previous = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit("usage: python3 build.py briefs/YYYY-MM-DD.json [--previous PATH.json]")
    main(args[0], previous)
