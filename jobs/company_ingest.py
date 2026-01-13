#!/usr/bin/env python3
import json, hashlib, time, os
from pathlib import Path

MAX_COMPANIES = int(os.environ.get("MAX_COMPANIES_PER_RUN", "50"))
VAULT = Path("/opt/obsidian-vault")
COMPANY_LIST = VAULT / "20_Companies" / "company_list.json"
RAW_ROOT = VAULT / "21_Company_Data" / "_raw"

def slugify(name: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in name).split()) or "company"

def load_entries():
    if not COMPANY_LIST.exists():
        return []
    text = COMPANY_LIST.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        return data.get("companies") or data.get("items") or []
    if isinstance(data, list):
        return data
    return []

def main():
    entries = load_entries()
    processed = 0
    for entry in entries:
        if processed >= MAX_COMPANIES:
            break
        name = entry.get("company_name") or entry.get("name") or "Unknown Company"
        slug = slugify(name)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        payload = {
            "retrieved_at": ts,
            "source_url": entry.get("source_url") or entry.get("url") or "",
            "entry": entry,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]
        target_dir = RAW_ROOT / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{ts}_{digest}.json"
        if target_file.exists():
            continue
        target_file.write_text(blob, encoding="utf-8")
        processed += 1
    print(f"ingest_complete count={processed}")

if __name__ == "__main__":
    main()
