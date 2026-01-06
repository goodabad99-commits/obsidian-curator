from pathlib import Path
from datetime import datetime
import re

VAULT = Path(r"C:\Users\Yousuf\Documents\vault")
REVIEW_FILE = VAULT / "97_Reviews" / "link_review_queue.md"

def append_to_review(note_path, from_title, to_title, reason):
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not REVIEW_FILE.exists():
        REVIEW_FILE.write_text("# Link Review Queue\n\n## Pending Suggestions\n", encoding="utf-8")

    entry = f"""
- [ ] **{from_title} → {to_title}**
  - File: `{note_path}`
  - Reason: {reason}
  - Suggested: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    with open(REVIEW_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

def _parse_review_entries(lines):
    entries = []
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^- \[[ xX]\] ", line):
            if start is not None:
                entries.append((start, i))
            start = i
    if start is not None:
        entries.append((start, len(lines)))
    return entries

def _extract_titles(line):
    m = re.match(r"^- \[[xX]\] \*\*(.+?)\*\*", line)
    if not m:
        return None, None
    title_pair = m.group(1)
    if " ƒ+' " not in title_pair:
        return None, None
    from_title, to_title = title_pair.split(" ƒ+' ", 1)
    return from_title.strip(), to_title.strip()

def _extract_file_path(entry_lines):
    for line in entry_lines:
        m = re.search(r"- File:\s*`([^`]+)`", line)
        if m:
            return m.group(1).strip()
    return None

def _entry_applied(entry_lines):
    return any(line.strip().startswith("- Applied:") for line in entry_lines)

def apply_approved_reviews():
    if not REVIEW_FILE.exists():
        return 0

    lines = REVIEW_FILE.read_text(encoding="utf-8").splitlines()
    entries = _parse_review_entries(lines)
    if not entries:
        return 0

    applied_count = 0
    updated_lines = list(lines)

    for start, end in reversed(entries):
        line = lines[start]
        if not line.startswith("- [x]") and not line.startswith("- [X]"):
            continue
        entry_lines = lines[start:end]
        if _entry_applied(entry_lines):
            continue

        from_title, to_title = _extract_titles(line)
        note_rel = _extract_file_path(entry_lines)
        if not to_title or not note_rel:
            continue

        note_path = VAULT / note_rel
        if not note_path.exists():
            continue

        md_text = note_path.read_text(encoding="utf-8", errors="ignore")
        new_text = apply_links_safe(md_text, [to_title], max_links=1)
        if new_text != md_text:
            note_path.write_text(new_text, encoding="utf-8")

        applied_line = f"  - Applied: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        updated_lines.insert(end, applied_line)
        applied_count += 1

    if updated_lines != REVIEW_FILE.read_text(encoding="utf-8").splitlines():
        REVIEW_FILE.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    return applied_count

def apply_links_safe(md_text, links, max_links=3):
    """
    Adds wiki links ONLY under the '## Links' heading.
    Does not modify other sections.
    """
    lines = md_text.splitlines()

    # Ensure Links section exists
    if "## Links" not in md_text:
        lines.append("")
        lines.append("## Links")
        lines.append("")

    # Find Links section insertion point
    out = []
    in_links = False
    inserted = 0

    for i, line in enumerate(lines):
        out.append(line)
        if line.strip() == "## Links":
            in_links = True
            continue

        # When we reach the first content line after Links heading, insert links once
        if in_links:
            # Insert links at the first blank line after heading or immediately
            # Only once
            if inserted == 0:
                # skip existing blank lines (we allow one)
                # We'll insert after the first blank line or immediately if content starts
                pass

    # Reconstruct by inserting links at top of Links section
    text = "\n".join(lines)
    if "## Links" not in text:
        return md_text

    # If links already exist, do not duplicate
    to_add = []
    for t in links[:max_links]:
        if f"[[{t}]]" not in text:
            to_add.append(f"- [[{t}]]")
    if not to_add:
        return md_text

    # Insert immediately after the Links heading line
    parts = text.split("## Links", 1)
    before = parts[0]
    after = parts[1]

    # Keep spacing clean
    insertion = "\n\n" + "\n".join(to_add) + "\n"
    new_text = before + "## Links" + insertion + after.lstrip("\n")

    # Ensure final newline
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text
