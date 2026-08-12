#!/usr/bin/env python3
"""
fix_links.py
------------
Scans all output_*.html snapshot files in a directory and:
  - Replaces the href on any <a> tag whose text is "View in previous days browser"
  - Adds the link before </body> if it is missing entirely

Target URL: https://mktpulse.online/
Link text:  View in previous days browser

Usage:
    python fix_links.py                     # current directory
    python fix_links.py /path/to/snapshots  # specified directory
"""

import re
import sys
from pathlib import Path

TARGET_URL  = "https://mktpulse.online/"
LINK_TEXT   = "View in previous days browser"
FILE_PATTERN = re.compile(r"^output_\d{8}_\d{6}\.html$")

# Matches <a ...>View in previous days browser</a> regardless of href or other attrs
ANCHOR_RE = re.compile(
    r'<a\b[^>]*>\s*View in previous days browser\s*</a>',
    re.IGNORECASE
)

REPLACEMENT_ANCHOR = f'<a href="{TARGET_URL}">{LINK_TEXT}</a>'
FALLBACK_INJECT    = f'\n<p>{REPLACEMENT_ANCHOR}</p>\n</body>'


def fix_file(path: Path) -> str:
    """Fix a single file. Returns 'replaced', 'added', or 'skipped'."""
    original = path.read_text(encoding="utf-8", errors="replace")

    if ANCHOR_RE.search(original):
        updated = ANCHOR_RE.sub(REPLACEMENT_ANCHOR, original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            return "replaced"
        return "skipped"  # href was already correct
    else:
        # Link is missing — inject it before </body>
        if "</body>" in original.lower():
            # Case-insensitive replace for </body>
            updated = re.sub(
                r'</body>',
                FALLBACK_INJECT,
                original,
                count=1,
                flags=re.IGNORECASE
            )
        else:
            # No </body> tag — append to end of file
            updated = original + f'\n<p>{REPLACEMENT_ANCHOR}</p>\n'

        path.write_text(updated, encoding="utf-8")
        return "added"


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()

    if not target.is_dir():
        print(f"Error: '{target}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    files = sorted(f for f in target.iterdir()
                   if f.is_file() and FILE_PATTERN.match(f.name))

    if not files:
        print("No matching snapshot files found.")
        sys.exit(0)

    counts = {"replaced": 0, "added": 0, "skipped": 0}

    for f in files:
        result = fix_file(f)
        counts[result] += 1
        symbol = {"replaced": "✎", "added": "+", "skipped": "·"}[result]
        print(f"  {symbol}  {f.name}  [{result}]")

    print(f"\nDone.  {counts['replaced']} replaced · "
          f"{counts['added']} added · {counts['skipped']} already correct")


if __name__ == "__main__":
    main()
