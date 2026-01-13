#!/usr/bin/env python3
import json, time, os
from pathlib import Path

MAX_COMPANIES = int(os.environ.get("MAX_COMPANIES_PER_RUN", "50"))
RAW_ROOT = Path("/opt/obsidian-vault") / "21_Company_Data" / "_raw"
DEST_DIR = Path("/opt/obsidian-vault") / "20_Companies" / "AE"
DASH = Path("/opt/obsidian-vault") / "98_Dashboards" / "company_ingestion_status.md"
HEADINGS = ["## Core", "## Operations", "## Relationships", "## Evidence", "## Links", "## Next Actions"]

def slugify(name: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in name).split()) or "company"

def yaml_frontmatter(data: dict) -> str:
    lines = ["---"]
    for k, v in data.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)

def build_note(entry, retrieved_at):
    title = entry.get("company_name") or entry.get("name") or "Unknown Company"
    slug = slugify(title)
    confidence = (entry.get("confidence") or "medium").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    frontmatter = {
        "title": title,
        "country": "UAE",
        "slug": slug,
        "confidence": confidence,
        "retrieved_at": retrieved_at,
        "source_url": entry.get("source_url") or entry.get("url") or "",
        "last_normalized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for opt in ("aliases", "registry_id", "sector", "tags", "owners", "subsidiaries", "partners", "customers", "government_ties", "description"):
        val = entry.get(opt)
        if val:
            frontmatter[opt] = val
    owners = entry.get("owners")
    subs = entry.get("subsidiaries")
    partners = entry.get("partners")
    customers = entry.get("customers")
    gov_ties = entry.get("government_ties")
    body_sections = {
        "## Core": entry.get("description") or "",
        "## Operations": entry.get("operations") or "",
        "## Relationships": "\n".join(filter(None, [
            f"- Owners: {owners}" if owners else "",
            f"- Subsidiaries: {subs}" if subs else "",
            f"- Partners: {partners}" if partners else "",
            f"- Customers: {customers}" if customers else "",
            f"- Government ties: {gov_ties}" if gov_ties else "",
        ])).strip(),
        "## Evidence": entry.get("evidence") or "",
        "## Links": "",
        "## Next Actions": entry.get("next_actions") or "",
    }
    parts = [yaml_frontmatter(frontmatter)]
    for h in HEADINGS:
        parts.append(h)
        parts.append(body_sections.get(h, ""))
    return slug, "\n".join(parts).rstrip() + "\n"

def iter_raw_files():
    for sub in sorted(RAW_ROOT.glob("*")):
        if sub.is_dir():
            for jf in sorted(sub.glob("*.json")):
                yield jf

def main():
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    processed = 0
    for jf in iter_raw_files():
        if processed >= MAX_COMPANIES:
            break
        bundle = json.loads(jf.read_text(encoding="utf-8"))
        entry = bundle.get("entry") or {}
        retrieved_at = bundle.get("retrieved_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        slug, note = build_note(entry, retrieved_at)
        (DEST_DIR / f"{slug}.md").write_text(note, encoding="utf-8")
        processed += 1

    total_notes = len(list(DEST_DIR.glob("*.md")))
    total_raw = len(list(RAW_ROOT.rglob("*.json")))
    dash = [
        "# Company Ingestion Status",
        f"- last_run: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"- notes: {total_notes}",
        f"- raw_bundles: {total_raw}",
    ]
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text("\n".join(dash) + "\n", encoding="utf-8")
    print(f"normalize_complete count={processed}")

if __name__ == "__main__":
    main()
