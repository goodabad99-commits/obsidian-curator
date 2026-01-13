#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from curator_core import curate_file

MAX_COMPANIES = int(os.environ.get("MAX_COMPANIES_PER_RUN", "50"))
NOTES_DIR = Path("/opt/obsidian-vault") / "20_Companies" / "AE"

def main():
    notes = sorted(NOTES_DIR.glob("*.md"))
    processed = 0
    for note in notes:
        if processed >= MAX_COMPANIES:
            break
        curate_file(note)
        processed += 1
    print(f"link_complete count={processed}")

if __name__ == "__main__":
    main()
