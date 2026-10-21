#!/usr/bin/env python3
"""
Render a morning brief from JSON into the fixed HTML email template.

    python build.py briefs/2026-10-21.json

Writes briefs/2026-10-21.html (send as htmlBody) and briefs/2026-10-21.txt
(send as the plain-text body). Python 3 standard library only.

The look lives in template.html; this file only lays out the content.
Do not restyle here. Change template.html if the design needs to change.
"""
import html
import json
import os
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")

# Tokens (keep in step with template.html)
INK = "#1D1D1F"
SOFT = "#6E6E73"
LINK = "#0071E3"
UP = "#1F8A4C"
DOWN = "#C8372D"
HAIR = "#E5E5EA"
FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Where the animated weather GIFs are served from. The repo must be public for
# the GitHub raw URL to work; override with MB_ICON_BASE or "icon_base" in the JSON.
ICON_BASE = "https://raw.githubusercontent.com/rizwankhanmk/morning-brief/main/assets/weather"
ICON_ALT = {"sun": "\u2600\ufe0f", "partly-cloudy": "\u26c5", "cloudy": "\u2601\ufe0f",
            "rain": "\U0001f327\ufe0f", "thunder": "\u26c8\ufe0f", "haze": "\U0001f32b\ufe0f"}

# Expected item counts, checked after rendering (warnings only — never blocks sending).
EXPECTED = {
    "Apple": {"9to5Mac": 2, "MacRumors": 2},
    "Singapore": 5,
    "India": 5,
    "World": 5,
    "AI in Singapore": {"_brief": True},
    "Singapore AI startups": {"_total": 5},
    "AI in the United States": 5,
    "AI in China and worldwide": 5,
}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%A, %-d %B %Y")


def render_weather(weather, icon_base) -> str:
    if not weather:
        return ""
    cells = []
    for w in weather:
        icon = w.get("icon", "cloudy")
        src = f"{icon_base.rstrip('/')}/{icon}.gif"
        alt = ICON_ALT.get(icon, "")
        cells.append(
            f"""
                    <td class="wx" valign="middle" style="padding:0 0 0 22px;">
                      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                          <td class="wxc" valign="middle" style="padding:0 8px 0 0;"><img class="wxi" src="{esc(src)}" width="44" height="44" alt="{alt}" style="display:block;width:44px;height:44px;border:0;"></td>
                          <td valign="middle">
                            <p style="margin:0 0 2px 0;font-family:{FONT};font-size:12px;line-height:1.3;font-weight:500;color:{SOFT};">{esc(w['city'])}</p>
                            <p style="margin:0;font-family:{FONT};font-size:16px;line-height:1.3;font-weight:600;color:{INK};">{int(round(float(w['high'])))}&deg; <span style="font-weight:400;color:{SOFT};">/ {int(round(float(w['low'])))}&deg;</span></p>
                          </td>
                        </tr>
                      </table>
                    </td>"""
        )
    return f"""
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="right">
                    <tr>{''.join(cells)}
                    </tr>
                  </table>"""


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
            <td width="{width}" valign="top" style="padding:0 10px 0 0;">
              <p style="margin:0 0 4px 0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:500;color:{SOFT};">{esc(s['ticker'])}<span class="nm"> &nbsp;{esc(s.get('name',''))}</span></p>
              <p class="price" style="margin:0 0 4px 0;font-family:{FONT};font-size:28px;line-height:1.15;font-weight:600;letter-spacing:-0.01em;color:{INK};"><span style="font-size:15px;font-weight:500;color:{SOFT};">{esc(cur)}</span>{float(s['price']):,.2f}</p>
              <p class="chg" style="margin:0;font-family:{FONT};font-size:14px;line-height:1.4;font-weight:500;white-space:nowrap;color:{colour};">{arrow} {change} &nbsp;({pct:+.2f}%)</p>
            </td>"""
        )
    return f"""
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:0 0 6px 0;">
              <tr>{''.join(cells)}
              </tr>
            </table>
            <p style="margin:0 0 30px 0;font-family:{FONT};font-size:12px;line-height:1.5;color:#8E8E93;">{esc(note)}</p>"""


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
    out = [
        f"""
              <tr>
                <td style="padding:24px 0 16px 0;border-top:1px solid {HAIR};">
                  <p style="margin:0;font-family:{FONT};font-size:20px;line-height:1.3;font-weight:600;letter-spacing:-0.01em;color:{INK};">{esc(section['title'])}</p>"""
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
                  <p style="margin:0 0 6px 0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:600;color:{SOFT};">{esc(label)}</p>""" if label else "")
            + f"""
                  <p style="margin:0 0 7px 0;font-family:{FONT};font-size:15px;line-height:1.55;color:{INK};">{esc(brief['summary'])}</p>
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.5;font-weight:500;color:{SOFT};">{prefix}{links}</p>
                </td>
              </tr>"""
        )
    if "groups" in section:
        for group in section["groups"]:
            out.append(
                f"""
              <tr>
                <td style="padding:2px 0 12px 0;">
                  <p style="margin:0;font-family:{FONT};font-size:13px;line-height:1.4;font-weight:600;color:{SOFT};">{esc(group['label'])}</p>
                </td>
              </tr>"""
            )
            out.extend(render_item(i) for i in group["items"])
    else:
        out.extend(render_item(i) for i in section.get("items", []))
    return "".join(out)


def render_text(data) -> str:
    lines = [f"MORNING BRIEF — {nice_date(data['date'])}", ""]
    for w in data.get("weather", []):
        lines.append(f"{w['city']}: {int(round(float(w['high'])))}° / {int(round(float(w['low'])))}°, {w.get('icon','')}")
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
            if g["label"]:
                lines += [g["label"], ""]
            for i in g["items"]:
                lines += [i["headline"], i["summary"], f"Source: {i['source']} — {i.get('url','')}", ""]
    lines += [data.get("footer", "")]
    return "\n".join(lines).strip() + "\n"


def check_counts(data):
    for section in data["sections"]:
        want = EXPECTED.get(section["title"])
        if want is None:
            print(f"warning: unexpected section '{section['title']}'")
            continue
        if isinstance(want, dict) and want.get("_brief"):
            if not section.get("brief"):
                print(f"warning: {section['title']}: expected a 'brief' paragraph")
            continue
        if isinstance(want, dict) and "_total" in want:
            n = sum(len(g["items"]) for g in section.get("groups", [])) + len(section.get("items", []))
            if n != want["_total"]:
                print(f"warning: {section['title']}: {n} items, expected {want['_total']} across groups")
            continue
        if isinstance(want, dict):
            for g in section.get("groups", []):
                n, w = len(g["items"]), want.get(g["label"])
                if w is not None and n != w:
                    print(f"warning: {section['title']} / {g['label']}: {n} items, expected {w}")
        else:
            n = len(section.get("items", []))
            if n != want:
                print(f"warning: {section['title']}: {n} items, expected {want}")


def main(path: str):
    src = pathlib.Path(path)
    data = json.loads(src.read_text(encoding="utf-8"))

    html_out = (
        TEMPLATE.replace("{{TITLE}}", esc(f"Morning brief, {nice_date(data['date'])}"))
        .replace("{{DATE_LINE}}", esc(nice_date(data["date"])))
        .replace("{{WEATHER}}", render_weather(data.get("weather", []), os.environ.get("MB_ICON_BASE") or data.get("icon_base") or ICON_BASE))
        .replace("{{LEDE}}", esc(data.get("lede", "")))
        .replace("{{STOCKS}}", render_stocks(data["stocks"], data.get("stocks_note", "")))
        .replace("{{SECTIONS}}", "".join(render_section(s) for s in data["sections"]))
        .replace("{{FOOTER}}", esc(data.get("footer", "")))
    )
    html_path = src.with_suffix(".html")
    txt_path = src.with_suffix(".txt")
    html_path.write_text(html_out, encoding="utf-8")
    txt_path.write_text(render_text(data), encoding="utf-8")
    check_counts(data)
    print(f"wrote {html_path} ({len(html_out):,} bytes) and {txt_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python build.py briefs/YYYY-MM-DD.json")
    main(sys.argv[1])
