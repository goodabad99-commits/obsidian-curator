import os, re, json, time
from datetime import datetime
from pathlib import Path
import yaml
try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None  # type: ignore
try:
    import chromadb  # type: ignore
except Exception:
    chromadb = None  # type: ignore
from dotenv import load_dotenv
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore
from apply_links import append_to_review, apply_links_safe


HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

API_KEY = os.getenv("OPENAI_API_KEY")

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")


VAULT_PATH = os.getenv("VAULT_PATH", "/opt/obsidian-vault")
VAULT = Path(VAULT_PATH).resolve()
AUDIT_LOG = VAULT / "99_Logs" / "curator_audit.md"

enc = tiktoken.get_encoding("cl100k_base")
_CLIENT = None

def get_client():
    global _CLIENT
    if _CLIENT is None:
        if not API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _CLIENT = OpenAI(api_key=API_KEY)
    return _CLIENT

def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_rules():
    rules_path = HERE / "rules.yaml"
    with open(rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def audit_line(text: str):
    # Ensure audit folder exists
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Always delete extensionless sibling if it exists
    try:
        extless = AUDIT_LOG.with_suffix("")
        if extless.exists() and extless.is_file():
            extless.unlink()
    except Exception:
        pass

    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"- [{now_ts()}] {text}\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def split_yaml(md: str):
    if md.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md, flags=re.DOTALL)
        if m:
            return m.group(1), m.group(2)
    return None, md

def ensure_yaml(md: str, title_guess: str):
    yaml_block, body = split_yaml(md)
    if yaml_block is None:
        fm = {
            "title": title_guess,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "type": "",
            "tags": [],
            "links": [],
        }
        new_yaml = yaml.safe_dump(fm, sort_keys=False).strip()
        return f"---\n{new_yaml}\n---\n\n{body.strip()}\n"
    else:
        # ensure required fields exist
        fm = yaml.safe_load(yaml_block) or {}
        changed = False
        for k, v in {
            "title": fm.get("title", title_guess),
            "created": fm.get("created", datetime.now().strftime("%Y-%m-%d")),
            "type": fm.get("type", ""),
            "tags": fm.get("tags", []),
            "links": fm.get("links", []),
        }.items():
            if k not in fm:
                fm[k] = v
                changed = True
        if changed:
            new_yaml = yaml.safe_dump(fm, sort_keys=False).strip()
            return f"---\n{new_yaml}\n---\n\n{body.strip()}\n"
        return md

def ensure_headings(md: str, required_headings):
    yaml_block, body = split_yaml(md)
    if yaml_block is not None:
        content = body
    else:
        content = md

    # Ensure each heading exists (append missing)
    for h in required_headings:
        if h not in content:
            content = content.rstrip() + "\n\n" + h + "\n\n"
    if yaml_block is not None:
        return f"---\n{yaml_block.strip()}\n---\n\n{content.strip()}\n"
    else:
        return content.strip() + "\n"

def list_note_titles():
    """Map title -> relative path for existing notes (for safe linking)."""
    rules = load_rules()
    exclude = set(rules.get("exclude_folders", []))
    titles = {}
    for p in VAULT.rglob("*.md"):
        rel = p.relative_to(VAULT)
        parts = set(rel.parts)
        if any(x in parts for x in exclude):
            continue
        txt = read_text(p)
        yaml_block, body = split_yaml(txt)
        title = None
        if yaml_block:
            fm = yaml.safe_load(yaml_block) or {}
            if isinstance(fm, dict):
                title = fm.get("title")
        if not title:
            # fallback: first H1
            m = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
            title = m.group(1).strip() if m else p.stem
        titles[title] = str(rel)
    return titles

def extract_links_section(md: str, links_heading="## Links"):
    yaml_block, body = split_yaml(md)
    content = body if yaml_block else md

    # Find Links section boundaries
    pattern = re.escape(links_heading) + r"\s*\n"
    m = re.search(pattern, content)
    if not m:
        return None, None, None, md

    start = m.end()
    # section ends at next "## " heading or EOF
    m2 = re.search(r"\n##\s+", content[start:])
    end = start + (m2.start() if m2 else len(content[start:]))
    before = content[:start]
    links_body = content[start:end]
    after = content[end:]
    return before, links_body, after, (yaml_block, body, content)

def set_links_section(md: str, new_links_text: str, links_heading="## Links"):
    yaml_block, body = split_yaml(md)
    content = body if yaml_block else md

    # Replace Links section content
    m = re.search(re.escape(links_heading) + r"\s*\n", content)
    if not m:
        # if missing, append
        content = content.rstrip() + f"\n\n{links_heading}\n\n{new_links_text.strip()}\n"
    else:
        start = m.end()
        m2 = re.search(r"\n##\s+", content[start:])
        end = start + (m2.start() if m2 else len(content[start:]))
        content = content[:start] + new_links_text.strip() + "\n" + content[end:]

    if yaml_block is not None:
        return f"---\n{yaml_block.strip()}\n---\n\n{content.strip()}\n"
    return content.strip() + "\n"

def suggest_links_for_note(note_text: str, existing_titles: list, max_links=5):
 # Use model to suggest existing note titles to link to
    titles_str = "\n".join(existing_titles[:600])  # safety cap
    prompt = f"""
You are suggesting Obsidian wiki links.
Only choose from the EXISTING TITLES list.

Return ONLY a JSON array of up to {max_links} titles.
No explanations.

EXISTING TITLES:
{titles_str}

NOTE CONTENT:
{note_text[:4000]}
"""
    try:
        resp = get_client().chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
    except Exception as exc:
        audit_line(f"link_suggest_error: {exc}")
        return []
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [x for x in arr if isinstance(x, str)][:max_links]
    except Exception:
        pass
    return []

def chunk_text(text: str, chunk_tokens=450, overlap=80):
    toks = enc.encode(text)
    chunks = []
    i = 0
    while i < len(toks):
        j = min(i + chunk_tokens, len(toks))
        chunks.append(enc.decode(toks[i:j]))
        if j == len(toks):
            break
        i = max(0, j - overlap)
    return chunks

def chroma_collection():
    rules = load_rules()
    db_dir = rules["indexing"]["db_dir_relative"]
    col_name = rules["indexing"]["collection"]
    db_path = VAULT / db_dir
    db_path.mkdir(parents=True, exist_ok=True)
    chroma = chromadb.PersistentClient(path=str(db_path), settings=Settings(anonymized_telemetry=False))
    return chroma.get_or_create_collection(name=col_name, metadata={"hnsw:space": "cosine"})

def update_embeddings_for_file(rel_path: str, md_text: str):
    rules = load_rules()
    chunk_tokens = rules["indexing"]["chunk_tokens"]
    overlap = rules["indexing"]["overlap_tokens"]

    # Remove YAML for embeddings (keeps semantic content clean)
    _, body = split_yaml(md_text)
    body = body.strip()

    chunks = chunk_text(body, chunk_tokens, overlap)
    col = chroma_collection()

    ids = [f"{rel_path}::chunk::{i}" for i in range(len(chunks))]

    # Remove old chunks for this file (simple approach)
    # Chroma doesn't have prefix delete; we do best-effort by deleting known ids range:
    # We'll delete first 500 possible chunk ids to avoid stale chunks.
    old_ids = [f"{rel_path}::chunk::{i}" for i in range(500)]
    try:
        col.delete(ids=old_ids)
    except Exception:
        pass

    # Embed and upsert
    if chunks:
        try:
            emb = get_client().embeddings.create(model=EMBED_MODEL, input=chunks)
            vectors = [d.embedding for d in emb.data]
            metas = [{"path": rel_path, "chunk": i} for i in range(len(chunks))]
            col.upsert(ids=ids, documents=chunks, metadatas=metas, embeddings=vectors)
        except Exception as exc:
            audit_line(f"embedding_error {rel_path}: {exc}")

def classify_link_reason(note_text: str, target_title: str) -> str:
    """
    Returns 'safe' if the target title is explicitly mentioned in the note text.
    Otherwise returns 'review'.
    Conservative by design.
    """
    if target_title and target_title.lower() in note_text.lower():
        return "safe"
    return "review"

def curate_file(path: Path):
    rules = load_rules()
    rel = str(path.relative_to(VAULT)).replace("\\", "/")

    # Only process markdown
    if path.suffix.lower() != ".md":
        return

    # Exclude folders
    parts = set(path.relative_to(VAULT).parts)
    if any(x in parts for x in rules.get("exclude_folders", [])):
        return

    md = read_text(path)
    title_guess = path.stem.replace("_", " ").replace("-", " ").strip()

    # 1) Ensure YAML frontmatter
    md2 = ensure_yaml(md, title_guess)

    # 2) Ensure required headings
    md3 = ensure_headings(md2, rules["schema"]["required_headings"])

    # 3) Suggest links
    titles_map = list_note_titles()
    existing_titles = list(titles_map.keys())

    suggested = suggest_links_for_note(
        md3,
        existing_titles,
        max_links=rules["linking"]["max_links_per_note"]
    )

    audit_line(f"Suggested links count for {rel}: {len(suggested)}")

    safe_links = []
    review_links = []

    for t in suggested:
        verdict = classify_link_reason(md3, t)
        if verdict == "safe":
            safe_links.append(t)
        else:
            review_links.append(t)

    # 4) Apply safe links (Links section only)
    if safe_links:
        md3 = apply_links_safe(
            md3,
            safe_links,
            max_links=min(len(safe_links), rules["linking"]["max_links_per_note"])
        )

    # 5) Queue review-required links
    if review_links:
        yaml_block, body = split_yaml(md3)
        from_title = title_guess

        if yaml_block:
            try:
                fm = yaml.safe_load(yaml_block) or {}
                if isinstance(fm, dict) and fm.get("title"):
                    from_title = str(fm.get("title"))
            except Exception:
                pass

        note_rel = str(path.relative_to(VAULT)).replace("\\", "/")
        for t in review_links:
            append_to_review(
                note_path=note_rel,
                from_title=from_title,
                to_title=t,
                reason="Not explicitly mentioned in note text; requires approval."
            )

    # 6) Write back if changed
    if md3 != md:
        write_text(path, md3)
        audit_line(f"Curated: {rel} (schema+links)")
    else:
        audit_line(f"Seen (no change): {rel}")

    # 7) Update embeddings
    update_embeddings_for_file(rel, md3)
    audit_line(f"Indexed: {rel}")

