#!/usr/bin/env python3
"""
Render a morning brief from JSON into the fixed HTML email template.

    python3 build.py briefs/2026-10-21.json
    python3 build.py briefs/2026-10-22.json --previous /tmp/previous.json

Writes briefs/2026-10-21.html (send as htmlBody, unmodified) and
briefs/2026-10-21.txt (send as the plain-text body). Python 3 standard
library only.

The look lives in template.html; this file only lays out the content.
Do not restyle here. Change template.html if the design needs to change.

After rendering it prints warnings (counts, summary lengths, links, outlet
names, repeats from the previous brief). Warnings never block the build;
the scheduled prompt says which ones to fix.
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
    "Apple": "#0071E3",
    "Singapore": "#D23B2F",
    "India": "#E0861B",
    "World": "#1E8E5A",
    "AI in Singapore": "#7B4FD9",
    "AI startups in Singapore and Southeast Asia": "#C2367F",
    "AI worldwide": "#0E8C9E",
}

# Expected shape, checked after rendering (warnings only, never blocks the build).
#   int            -> exactly that many items
#   {"_brief": True} -> a 'brief' paragraph, no items
#   {"_total": n}    -> exactly n items across the groups
#   {"_max": n}      -> between 1 and n items across the groups
#   {label: n, ...}  -> exactly n items in each named group
EXPECTED = {
    "Apple": {"9to5Mac": 2, "MacRumors": 2},
    "Singapore": 5,
    "India": 5,
    "World": 5,
    "AI in Singapore": {"_brief": True},
    "AI startups in Singapore and Southeast Asia": {"_max": 3},
    "AI worldwide": {"_total": 8},
}
GROUP_LABELS = {
    "AI startups in Singapore and Southeast Asia": ["Funding", "Hiring", "What they're building"],
    "AI worldwide": ["Models and products", "Money", "Policy and chips"],
}

# Writing rules (words). Items are 3 to 5 lines on a phone; paragraphs a little more.
ITEM_WORDS = (35, 60)
PARA_WORDS = (45, 65)

FOOTER = ("Built by your morning-brief agent at {time} Singapore time. "
          "Prices from Yahoo Finance; summaries written from the linked sources.")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%A, %-d %B %Y")


def singapore_time() -> str:
    now = datetime.now(ZoneInfo("Asia/Singapore"))
    return now.strftime("%-I:%M%p").lower()


def footer_text(data) -> str:
    # The builder stamps the real time. A 'footer' key in the JSON is ignored
    # unless it carries a {time} placeholder.
    custom = data.get("footer", "")
    text = custom if "{time}" in custom else FOOTER
    return text.replace("{time}", singapore_time())


def all_items(section):
    items = list(section.get("items", []))
    for g in section.get("groups", []):
        items.extend(g.get("items", []))
    return items


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


def render_stocks(stocks, note) -> str:
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
            </table>
            <p style="margin:0 0 26px 0;font-family:{FONT};font-size:12px;line-height:1.5;color:#8E8E93;">{esc(note)}</p>"""


def render_item(item) -> str:
    source = esc(item["source"])
    url = item.get("url", "").strip()
    link = f'<a href="{esc(url)}" style="color:{LINK};text-decoration:none;">{source}</a>' if url else source
    return f"""
              <tr>
                <td style="padding:0 0 22px 0;">
                  <p style="margin:0 0 6px 0;font-family:{FONT};font-size:16px;line-height:1.35;font-weight:600;color:{INK};">{esc(item['headline'])}</p>
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:15px;line-height:1.55;color:{SOFT};">{esc(item['summary'])}</p>
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:500;">{link}</p>
                </td>
              </tr>"""


def render_section(section) -> str:
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
        srcs = brief.get("sources") or [{"name": brief.get("source", ""), "url": brief.get("url", "")}]
        links = ", ".join(
            f'<a href="{esc(x.get("url",""))}" style="color:{LINK};text-decoration:none;">{esc(x["name"])}</a>' if x.get("url") else esc(x["name"])
            for x in srcs if x.get("name")
        )
        prefix = "Sources: " if len(srcs) > 1 else ""
        label = brief.get("label", "")
        out.append(
            f"""
              <tr>
                <td style="padding:0 0 26px 0;">"""
            + (f"""
                  <p style="margin:0 0 6px 0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:600;color:{colour};">{esc(label)}</p>""" if label else "")
            + f"""
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:15px;line-height:1.55;color:{INK};">{esc(brief['summary'])}</p>
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.5;font-weight:500;color:{SOFT};">{prefix}{links}</p>
                </td>
              </tr>"""
        )
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
            out.extend(render_item(i) for i in group["items"])
    else:
        out.extend(render_item(i) for i in section.get("items", []))
    return "".join(out)


def render_text(data, footer) -> str:
    lines = [f"MORNING BRIEF, {nice_date(data['date'])}", ""]
    for w in data.get("weather", []):
        lines.append(f"{WEATHER_EMOJI.get(w.get('icon',''),'')} {w['city']}: {int(round(float(w['high'])))}° / {int(round(float(w['low'])))}°")
    lines += ["", data.get("lede", ""), ""]
    for s in data["stocks"]:
        lines.append(f"{s['ticker']}  {s.get('currency','')}{float(s['price']):,.2f}  {float(s['change']):+.2f} ({float(s['change_pct']):+.2f}%)")
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
                lines += [i["headline"], i["summary"], f"Source: {i['source']} — {i.get('url','')}", ""]
    lines += [footer]
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def warn(msg):
    print(f"warning: {msg}")


def check_counts(data):
    seen = []
    for section in data["sections"]:
        title = section["title"]
        seen.append(title)
        want = EXPECTED.get(title)
        if want is None:
            warn(f"unexpected section '{title}'")
            continue
        labels = GROUP_LABELS.get(title)
        if labels:
            for g in section.get("groups", []):
                if g["label"] not in labels:
                    warn(f"{title}: unknown group label '{g['label']}' (use one of {labels})")
        n = len(all_items(section))
        if isinstance(want, dict) and want.get("_brief"):
            if not section.get("brief"):
                warn(f"{title}: expected a 'brief' paragraph")
            if n:
                warn(f"{title}: has {n} items, expected none (it is a paragraph section)")
        elif isinstance(want, dict) and "_total" in want:
            if n != want["_total"]:
                warn(f"{title}: {n} items, expected {want['_total']} across groups")
        elif isinstance(want, dict) and "_max" in want:
            if n == 0:
                warn(f"{title}: no items (one to {want['_max']} expected; say so in the lede only if the whole section is empty)")
            elif n > want["_max"]:
                warn(f"{title}: {n} items, at most {want['_max']} expected")
        elif isinstance(want, dict):
            for g in section.get("groups", []):
                m, w = len(g["items"]), want.get(g["label"])
                if w is not None and m != w:
                    warn(f"{title} / {g['label']}: {m} items, expected {w}")
        else:
            if n != want:
                warn(f"{title}: {n} items, expected {want}")
    missing = [t for t in EXPECTED if t not in seen]
    if missing:
        warn(f"missing sections: {missing}")
    if seen != [t for t in EXPECTED if t in seen]:
        warn(f"sections are out of order; expected {list(EXPECTED)}")


def check_writing(data):
    lo, hi = ITEM_WORDS
    for section in data["sections"]:
        title = section["title"]
        brief = section.get("official") or section.get("brief")
        if brief:
            n = len(brief["summary"].split())
            if not PARA_WORDS[0] <= n <= PARA_WORDS[1]:
                warn(f"{title}: paragraph is {n} words, want {PARA_WORDS[0]} to {PARA_WORDS[1]}")
        for item in all_items(section):
            n = len(item["summary"].split())
            if not lo <= n <= hi:
                warn(f"{title}: '{item['headline'][:50]}' summary is {n} words, want {lo} to {hi}")
            if "!" in item["headline"] or "!" in item["summary"]:
                warn(f"{title}: '{item['headline'][:50]}' uses an exclamation mark")


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
            if url in seen_urls and seen_urls[url] != headline:
                warn(f"{title}: url already used for '{seen_urls[url][:40]}': {url}")
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
        for i in all_items(section):
            old_urls[i.get("url", "").strip()] = i["headline"]
            old_heads[i["headline"].strip().lower()] = section["title"]
    for section in data["sections"]:
        for i in all_items(section):
            url = i.get("url", "").strip()
            if url and url in old_urls:
                warn(f"{section['title']}: '{i['headline'][:50]}' repeats the previous brief ({prev.get('date')}) by url")
            elif i["headline"].strip().lower() in old_heads:
                warn(f"{section['title']}: '{i['headline'][:50]}' repeats a headline from the previous brief ({prev.get('date')})")


def main(path: str, previous: str | None):
    src = pathlib.Path(path)
    data = json.loads(src.read_text(encoding="utf-8"))
    footer = footer_text(data)

    html_out = (
        TEMPLATE.replace("{{TITLE}}", esc(f"Morning brief, {nice_date(data['date'])}"))
        .replace("{{DATE_LINE}}", esc(nice_date(data["date"])))
        .replace("{{WEATHER}}", render_weather(data.get("weather", [])))
        .replace("{{LEDE}}", esc(data.get("lede", "")))
        .replace("{{STOCKS}}", render_stocks(data["stocks"], data.get("stocks_note", "")))
        .replace("{{SECTIONS}}", "".join(render_section(s) for s in data["sections"]))
        .replace("{{FOOTER}}", esc(footer))
    )
    html_path = src.with_suffix(".html")
    txt_path = src.with_suffix(".txt")
    html_path.write_text(html_out, encoding="utf-8")
    txt_path.write_text(render_text(data, footer), encoding="utf-8")

    check_counts(data)
    check_writing(data)
    check_links_and_sources(data)
    if previous:
        check_previous(data, previous)
    size = len(html_out.encode("utf-8"))
    if size > 100_000:
        warn(f"html is {size:,} bytes; Gmail clips messages above about 102 KB")
    print(f"wrote {html_path} ({size:,} bytes) and {txt_path}")


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
