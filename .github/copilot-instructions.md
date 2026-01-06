# Copilot / AI agent instructions — Curator

Short, actionable guidance to help an AI agent be productive in this repo.

1. Quick start
- Ensure environment: `.env` must contain `OPENAI_API_KEY` and `VAULT_PATH`. See [README.md](README.md).
- Preferred runtime: repository contains a Windows venv at `.venv312` and `watcher.py` enforces it; use `.venv312\Scripts\python.exe` to run.
- Start the watcher from the repo root: `python watcher.py` (watcher logs to the audit file).

2. Big-picture architecture
- This tool watches an Obsidian vault and curates markdown notes:
  - File-watching & orchestration: [watcher.py](watcher.py) — observer loop, mutex checks, heartbeat, review sinks.
  - Core curation logic: [curator_core.py](curator_core.py) — ensures frontmatter, headings, suggests/applies links, updates vector DB.
  - Link review & application: [apply_links.py](apply_links.py) — queue format, applying approved reviews, and safe link insertion.
  - Config and conventions: [rules.yaml](rules.yaml) — watched folders, schema headings, indexing and linking limits.

3. Important workflows & commands
- Run the watcher (Windows, using repo venv):
  ```powershell
  .venv312\Scripts\activate
  python watcher.py
  ```
- If watcher exits, check audit: `C:\Users\Yousuf\Documents\vault\99_Logs\curator_audit.md` (path is hardcoded in code).
- Review queue file: `97_Reviews/link_review_queue.md` inside the vault (see [apply_links.py](apply_links.py)).

4. Key project-specific patterns (do not change unless confident)
- Frontmatter & schema: `curator_core.ensure_yaml` and `ensure_headings` will add YAML fields and required headings listed in [rules.yaml](rules.yaml). Example headings: `## Core`, `## Assumptions`, `## Evidence`, `## Links`, `## Next Actions`.
- Links: the system only inserts wiki links under the `## Links` heading via `apply_links.apply_links_safe`. Avoid inserting links elsewhere.
- Link classification: `curator_core.classify_link_reason` treats a suggested target as `safe` only if the target title string is present (case-insensitive) in the note body; otherwise it's queued for review.
- Embeddings & indexing: vector DB location and chunk sizes are driven by [rules.yaml](rules.yaml) (`indexing.db_dir_relative`, `chunk_tokens`, `overlap_tokens`); `curator_core.chroma_collection` uses a persistent Chroma DB under the vault.

5. Notable implementation quirks (documented, reproducible)
- Two VAULT sources: `curator_core.py` reads `VAULT_PATH` from `.env`, but `apply_links.py` hardcodes `VAULT = C:\\Users\\Yousuf\\Documents\\vault`. Be careful when changing vault handling.
- Interpreter enforcement: `watcher.py` exits if the active interpreter is not the `.venv312` scripts interpreter — tests or quick runs should use that venv.
- Review entry parsing: `apply_links._extract_titles` expects a specific title delimiter (literal string present in code). When producing approved-review entries, include the `File:` line and mark the checkbox `[x]` to trigger `apply_approved_reviews`.

6. Dependencies
- Main Python packages referenced in code: `watchdog`, `openai`, `chromadb`, `tiktoken`, `python-dotenv`, `pyyaml`. Install into `.venv312`.

7. How to change behavior safely
- Schema, watch folders, indexing, and linking limits are configured in [rules.yaml](rules.yaml). Prefer edits there over code changes for tuning.
- If changing how links are parsed/applied, update both `curator_core` (suggest/apply flow) and `apply_links.py` (safe insertion & review application) and test end-to-end with a small test vault.

8. Quick code pointers for agents
- To suggest links: call `curator_core.suggest_links_for_note(note_text, existing_titles, max_links=...)` which uses the chat model configured by `CHAT_MODEL` env var.
- To apply links programmatically: `apply_links.apply_links_safe(md_text, links, max_links=...)` — it only touches the `## Links` section.
- To re-index a note: call `curator_core.update_embeddings_for_file(rel_path, md_text)` (uses `EMBED_MODEL` env var).

If anything above is unclear or you'd like more examples (sample review entry, sample note before/after), tell me which section to expand. I'll iterate.
