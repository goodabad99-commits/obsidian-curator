#!/usr/bin/env python3
import json, time, os
from pathlib import Path

VAULT = Path("/opt/obsidian-vault")
NOTES_DIR = VAULT / "20_Companies" / "AE"
RAW_ROOT = VAULT / "21_Company_Data" / "_raw"
DASH = VAULT / "98_Dashboards" / "company_ingestion_status.md"
REVIEW = VAULT / "97_Reviews" / "link_review_queue.md"

def confidence_counts():
    counts = {"high":0,"medium":0,"low":0,"unknown":0}
    for path in NOTES_DIR.glob("*.md"):
        conf = "unknown"
        with path.open(encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == "---":
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                if line.lower().startswith("confidence:"):
                    conf = line.split(":",1)[1].strip().lower()
                    break
        if conf not in counts:
            conf = "unknown"
        counts[conf] += 1
    return counts

def main():
    last_run = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    notes = list(NOTES_DIR.glob("*.md"))
    raw_bundles = list(RAW_ROOT.rglob("*.json"))
    counts = confidence_counts()
    review_tail = ""
    if REVIEW.exists():
        review_tail = "\n".join(REVIEW.read_text(encoding="utf-8").splitlines()[-10:])
    review_tail = review_tail or "empty"
    content = [
        "# Company Ingestion Status",
        f"- last_run: {last_run}",
        f"- notes: {len(notes)}",
        f"- raw_bundles: {len(raw_bundles)}",
        f"- confidence: {json.dumps(counts, ensure_ascii=False)}",
        f"- review_tail:\n{review_tail}",
    ]
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text("\n".join(content) + "\n", encoding="utf-8")
    print("refresh_complete")

if __name__ == "__main__":
    main()
