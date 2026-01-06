Obsidian Curator

Run
1) Ensure `.env` has `OPENAI_API_KEY` and `VAULT_PATH` set.
2) From this folder, run: `python watcher.py`

What it does
- Watches the folders in `rules.yaml` and curates changed notes.
- Writes audit logs to `C:\Users\Yousuf\Documents\vault\99_Logs\curator_audit.md`.
- Queues review suggestions in `C:\Users\Yousuf\Documents\vault\97_Reviews\link_review_queue.md`.
- Applies checked review items and marks them as applied.

Troubleshooting
- If the watcher exits immediately, verify Python and dependencies are installed (`watchdog`, `openai`, `chromadb`, `tiktoken`, `python-dotenv`, `pyyaml`).
- If no files are being processed, confirm `VAULT_PATH` points to your Obsidian vault and the `watch_folders` in `rules.yaml` exist.
- If review approvals are not applying, ensure the queue item is checked `[x]` and includes a `File:` line with a valid vault-relative path.
