#!/usr/bin/env python3
"""
Remove archived briefs older than N days from the working tree and the git index.

    python3 prune.py            # removes briefs/YYYY-MM-DD.* older than 30 days
    python3 prune.py --days 45
    python3 prune.py --dry-run  # only prints what it would remove

Run it on the `briefs` branch after adding today's files, before committing.
It never touches the reference brief named in KEEP, and it only ever removes
files whose name starts with a date. Git history still holds the old issues;
this keeps the checkout and the GitHub file listing to about a month.
Python 3 standard library only.
"""
import pathlib
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
BRIEFS = ROOT / "briefs"
KEEP = {"2026-10-21"}  # the reference brief that CLAUDE.md points at
NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(json|html|txt)$")


def main(days: int, dry_run: bool):
    today = datetime.now(ZoneInfo("Asia/Singapore")).date()
    cutoff = today - timedelta(days=days)
    old = []
    for path in sorted(BRIEFS.iterdir()):
        m = NAME.match(path.name)
        if not m or m.group(1) in KEEP:
            continue
        if date.fromisoformat(m.group(1)) < cutoff:
            old.append(path)
    if not old:
        print(f"nothing older than {cutoff} to prune")
        return
    rel = [str(p.relative_to(ROOT)) for p in old]
    if dry_run:
        print("would remove:", *rel, sep="\n  ")
        return
    subprocess.run(["git", "rm", "-q", "--", *rel], cwd=ROOT, check=True)
    print(f"removed {len(rel)} files older than {cutoff}:", *rel, sep="\n  ")


if __name__ == "__main__":
    args = sys.argv[1:]
    days = 30
    if "--days" in args:
        i = args.index("--days")
        days = int(args[i + 1])
        del args[i:i + 2]
    dry = "--dry-run" in args
    main(days, dry)
