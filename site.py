#!/usr/bin/env python3
"""
Build the archive page: docs/index.html, a single self-contained file with
every issue on the branch, full-text search, the running threads and a
price chart. No external assets, no JavaScript libraries.

    python3 site.py              # reads briefs/*.json and briefs/threads.json
    python3 site.py --out PATH

Open the file locally, or turn on GitHub Pages for the `briefs` branch with
the /docs folder as the source. Python 3 standard library only.
"""
import html
import json
import pathlib
import re
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
BRIEFS = ROOT / "briefs"
NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def load_issues():
    issues = []
    for p in sorted(BRIEFS.glob("*.json")):
        if not NAME.match(p.name):
            continue
        try:
            issues.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(issues, key=lambda d: d["date"], reverse=True)


def all_items(section):
    items = list(section.get("items", []))
    for g in section.get("groups", []):
        items.extend(g.get("items", []))
    return items


def sparkline(points, width=560, height=120, pad=8) -> str:
    """Inline SVG line for one series. points: [(date, price)] oldest first."""
    if len(points) < 2:
        return ""
    ys = [p for _, p in points]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    n = len(points)
    coords = []
    for i, (_, y) in enumerate(points):
        x = pad + i * (width - 2 * pad) / (n - 1)
        yy = pad + (hi - y) * (height - 2 * pad) / span
        coords.append(f"{x:.1f},{yy:.1f}")
    first, last = points[0], points[-1]
    colour = "#1F8A4C" if last[1] >= first[1] else "#C8372D"
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="price chart">'
            f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="{" ".join(coords)}"/>'
            f'<text x="{pad}" y="{height-2}" font-size="11" fill="#6E6E73">{esc(first[0])}  {first[1]:,.2f}</text>'
            f'<text x="{width-pad}" y="{height-2}" font-size="11" fill="#6E6E73" text-anchor="end">{esc(last[0])}  {last[1]:,.2f}</text></svg>')


def build(out: pathlib.Path):
    issues = load_issues()
    threads_path = BRIEFS / "threads.json"
    threads = json.loads(threads_path.read_text(encoding="utf-8")) if threads_path.exists() else {"threads": []}

    # search index: one record per item
    index = []
    for d in issues:
        for s in d.get("sections", []):
            for i in all_items(s):
                index.append({"d": d["date"], "s": s["title"], "h": i["headline"], "t": i["summary"], "src": i.get("source", ""), "u": i.get("url", "")})
            b = s.get("brief") or s.get("official")
            if b:
                index.append({"d": d["date"], "s": s["title"], "h": b.get("label") or s["title"], "t": b["summary"], "src": "", "u": ""})

    # price series
    series = {}
    for d in sorted(issues, key=lambda x: x["date"]):
        for s in d.get("stocks", []) + d.get("indices", []):
            series.setdefault(s["ticker"], []).append((d["date"][5:], float(s["price"])))

    parts = []
    parts.append(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning brief archive</title>
<style>
:root{{--ink:#1D1D1F;--soft:#6E6E73;--hair:#E5E5EA;--bg:#F3F3F1;--card:#fff;--link:#0071E3}}
@media(prefers-color-scheme:dark){{:root{{--ink:#F2F2F7;--soft:#A1A1A6;--hair:#3A3A3C;--bg:#1C1C1E;--card:#2C2C2E;--link:#5AA9FF}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.5}}
main{{max-width:760px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 10px}} h3{{font-size:15px;margin:0 0 4px}}
.card{{background:var(--card);border:1px solid var(--hair);border-radius:10px;padding:14px 16px;margin:0 0 10px}}
.soft{{color:var(--soft);font-size:13px}} a{{color:var(--link);text-decoration:none}}
input{{width:100%;box-sizing:border-box;font-size:16px;padding:10px 12px;border:1px solid var(--hair);border-radius:8px;background:var(--card);color:var(--ink)}}
details summary{{cursor:pointer;font-weight:600}} .hit{{border-top:1px solid var(--hair);padding:8px 0}} .hit:first-child{{border-top:0}}
.tabs span{{display:inline-block;margin:0 10px 8px 0;padding:4px 10px;border:1px solid var(--hair);border-radius:999px;font-size:13px;cursor:pointer}} .tabs span.on{{background:var(--link);color:#fff;border-color:var(--link)}}
</style></head><body><main>
<h1>Morning brief archive</h1><p class="soft">{len(issues)} issues on this branch, newest first. Older issues live in git history.</p>
<h2>Search</h2><input id="q" placeholder="Search every headline and summary" autofocus><div id="hits"></div>
""")
    # threads
    live = [t for t in threads.get("threads", []) if t.get("status")]
    if live:
        parts.append("<h2>Running threads</h2>")
        for t in live:
            hist = "".join(f'<div class="hit soft"><b>{esc(h.get("date",""))}</b> {esc(h.get("note",""))}</div>' for h in t.get("history", [])[-10:])
            parts.append(f'<div class="card"><h3>{esc(t["title"])} <span class="soft">since {esc(t.get("started",""))}, day {esc(t.get("day",""))}</span></h3><p>{esc(t["status"])}</p><details><summary class="soft">History</summary>{hist}</details></div>')
    # prices
    if series:
        parts.append('<h2>Prices across the archive</h2><div class="tabs" id="tabs">' + "".join(f'<span data-k="{esc(k)}">{esc(k)}</span>' for k in series) + "</div>")
        for k, pts in series.items():
            parts.append(f'<div class="card chart" data-k="{esc(k)}" style="display:none">{sparkline(pts)}</div>')
    # issues
    parts.append("<h2>Issues</h2>")
    for d in issues:
        nice = date.fromisoformat(d["date"]).strftime("%A %-d %B %Y")
        body = []
        for s in d.get("sections", []):
            b = s.get("brief") or s.get("official")
            lines = []
            if b:
                lines.append(f'<p><b>{esc(b.get("label",""))}</b> {esc(b["summary"][:300])}{"…" if len(b["summary"])>300 else ""}</p>')
            for i in all_items(s):
                link = f'<a href="{esc(i["u"] if "u" in i else i.get("url",""))}">{esc(i.get("source",""))}</a>' if i.get("url") else esc(i.get("source", ""))
                lines.append(f'<div class="hit"><b>{esc(i["headline"])}</b><br><span class="soft">{esc(i["summary"])}</span><br>{link}</div>')
            body.append(f'<details><summary>{esc(s["title"])}</summary>{"".join(lines)}</details>')
        today = f'<p><b>Today</b> {esc(d["today"])}</p>' if d.get("today") else ""
        parts.append(f'<div class="card"><h3>{nice}</h3><p>{esc(d.get("lede",""))}</p>{today}{"".join(body)}</div>')
    parts.append(f"""
<script>
const INDEX={json.dumps(index, ensure_ascii=False)};
const q=document.getElementById('q'),hits=document.getElementById('hits');
function esc(s){{return String(s).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();if(v.length<2){{hits.innerHTML='';return}}
 const r=INDEX.filter(i=>(i.h+' '+i.t+' '+i.src).toLowerCase().includes(v)).slice(0,60);
 hits.innerHTML='<div class="card">'+(r.length?r.map(i=>`<div class="hit"><span class="soft">${{esc(i.d)}} · ${{esc(i.s)}}</span><br><b>${{esc(i.h)}}</b><br><span class="soft">${{esc(i.t)}}</span>${{i.u?`<br><a href="${{esc(i.u)}}">${{esc(i.src)}}</a>`:''}}</div>`).join(''):'<span class="soft">Nothing found.</span>')+'</div>';}});
const tabs=document.querySelectorAll('#tabs span'),charts=document.querySelectorAll('.chart');
function show(k){{tabs.forEach(t=>t.classList.toggle('on',t.dataset.k===k));charts.forEach(c=>c.style.display=c.dataset.k===k?'':'none')}}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.k)));if(tabs.length)show(tabs[0].dataset.k);
</script></main></body></html>""")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes, {len(issues)} issues, {len(index)} searchable items)")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = ROOT / "docs" / "index.html"
    if "--out" in args:
        out = pathlib.Path(args[args.index("--out") + 1])
    build(out)
