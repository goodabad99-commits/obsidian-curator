import os
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load env
load_dotenv(Path(__file__).parent / ".env")

VAULT_PATH = os.getenv("VAULT_PATH", "/opt/obsidian-vault")
VAULT = Path(VAULT_PATH).resolve()

AUDIT_LOG = VAULT / "99_Logs" / "curator_audit.md"
REVIEW_FILE = VAULT / "97_Reviews" / "link_review_queue.md"

WATCH_FOLDERS = ["00_Inbox", "01_Ideas", "02_Plans", "03_Evidence"]
EXCLUDE_SUFFIXES = {".tmp", ".swp"}

def generate_weekly_summary():
    """
    Creates/updates: /opt/obsidian-vault/02_Plans/Weekly_Summary.md

    Rules:
    - Only include notes modified in the last 7 days
    - Only include notes inside WATCH_FOLDERS
    - Exclude 97_Reviews and 99_Logs
    - Exclude the summary file itself
    - Use stable paths (relative to vault) to avoid filename collisions
    """

    vault_path = str(VAULT)
    summary_path = str(VAULT / "02_Plans" / "Weekly_Summary.md")

    # Ensure destination folder exists
    Path(summary_path).parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    one_week_ago = now - timedelta(days=7)

    # Build allowed roots from WATCH_FOLDERS
    allowed_roots = [str(VAULT / folder) for folder in WATCH_FOLDERS]

    recent_notes = []

    for root in allowed_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            # Prevent descending into excluded folders (defensive)
            dirnames[:] = [d for d in dirnames if d not in ("97_Reviews", "99_Logs")]

            for filename in filenames:
                if not filename.endswith(".md"):
                    continue

                file_path = os.path.join(dirpath, filename)

                # Exclude the summary file itself
                if os.path.abspath(file_path) == os.path.abspath(summary_path):
                    continue

                try:
                    mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                except Exception:
                    continue

                if mod_time <= one_week_ago:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue

                # Store relative path to avoid collisions
                rel_path = os.path.relpath(file_path, vault_path)
                recent_notes.append((rel_path, content))

    # Sort newest-first by file modified time
    def _mtime(rel_path):
        return os.path.getmtime(os.path.join(vault_path, rel_path))

    recent_notes.sort(key=lambda x: _mtime(x[0]), reverse=True)

    # Render summary
    lines = []
    lines.append("# Weekly Summary")
    lines.append("")
    lines.append(f"_Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}_")
    lines.append("")

    if not recent_notes:
        lines.append("No notes modified in the last 7 days within the tracked folders.")
        lines.append("")
    else:
        for rel_path, content in recent_notes:
            snippet = content.strip().replace("\r\n", "\n").replace("\r", "\n")
            snippet = snippet[:400]  # slightly larger snippet
            lines.append(f"## {rel_path}")
            lines.append("")
            lines.append(snippet + ("..." if len(content) > 400 else ""))
            lines.append("")

    with open(summary_path, "w", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(lines))


DEBOUNCE_SECONDS = 2.0
EARTBEAT_SECONDS = 30.0
REVIEW_SCAN_SECONDS = 5.0

# Import your existing core logic (these should be platform-neutral)
from curator_core import curate_file, audit_line
from apply_links import apply_approved_reviews

def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _ensure_paths():
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)

def _startup_log():
    _ensure_paths()
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"- [{now_ts()}] Linux watcher started. pid={os.getpid()} cwd={os.getcwd()}\n")

class Handler(FileSystemEventHandler):
    def __init__(self):
        self.pending = {}

    def on_created(self, event):
        self._queue(event)

    def on_modified(self, event):
        self._queue(event)

    def _queue(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() != ".md":
            return
        if p.suffix.lower() in EXCLUDE_SUFFIXES:
            return
        self.pending[str(p)] = time.time()

def main():
    _startup_log()

    # Ensure folders exist
    for folder in WATCH_FOLDERS:
        (VAULT / folder).mkdir(parents=True, exist_ok=True)
    (VAULT / "97_Reviews").mkdir(parents=True, exist_ok=True)
    (VAULT / "99_Logs").mkdir(parents=True, exist_ok=True)

    audit_line(f"Curator watcher started (Linux). pid={os.getpid()}")
    for folder in WATCH_FOLDERS:
        audit_line(f"Watching: {str((VAULT / folder).resolve())}")

    handler = Handler()
    obs = Observer()
    for folder in WATCH_FOLDERS:
        obs.schedule(handler, str(VAULT / folder), recursive=True)
    obs.start()


    last_processed = {}
    last_heartbeat = 0.0
    last_review_scan = 0.0

    try:
        while True:
            now = time.time()

            # heartbeat
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                audit_line(f"Watcher heartbeat (Linux). pid={os.getpid()}")
                last_heartbeat = now

            # apply approved review links periodically
            if now - last_review_scan >= REVIEW_SCAN_SECONDS:
                try:
                    applied = apply_approved_reviews()
                    if applied:
                        audit_line(f"Applied approved review links: {applied}")
                except Exception as e:
                    audit_line(f"ERROR applying approved reviews: {e}")
                last_review_scan = now

            # process pending file events
            ready = [p for p, t in list(handler.pending.items()) if (now - t) >= DEBOUNCE_SECONDS]
            for p in ready:
                handler.pending.pop(p, None)
                if (now - last_processed.get(p, 0)) < DEBOUNCE_SECONDS:
                    continue
                last_processed[p] = now
                try:
                    curate_file(Path(p))
                except Exception as e:
                    audit_line(f"ERROR curating {p}: {e}")

            time.sleep(0.25)

    except KeyboardInterrupt:
        audit_line("Linux watcher stopping (KeyboardInterrupt).")
    except Exception as e:
        audit_line(f"Linux watcher exception: {type(e).__name__}: {e}")
        tb = traceback.format_exc().splitlines()[:30]
        for line in tb:
            audit_line(line)
    finally:
        obs.stop()
        obs.join()
        audit_line("Linux watcher stopped.")

if __name__ == "__main__":
    main()
