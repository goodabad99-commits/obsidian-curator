import os
import sys
import ctypes
import csv
import io
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

def _audit_startup_signature():
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        session = datetime.now().strftime('%Y%m%d%H%M%S')
        line = f"- [{ts}] Watcher start session={session} pid={os.getpid()} exe={sys.executable} cwd={os.getcwd()}\n"
        with open(AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass

HERE = Path(__file__).parent.resolve()

ALLOWED_EXES = {
    str((HERE / ".venv312" / "Scripts" / "python.exe").resolve()).casefold(),
    str((HERE / ".venv312" / "Scripts" / "pythonw.exe").resolve()).casefold(),
}

AUDIT_LOG_PATH = Path(r"C:\Users\Yousuf\Documents\vault\99_Logs\curator_audit.md")
MUTEX_NAME = "Global\\CuratorWatcherMutex"
WMIC_PATH = r"C:\Windows\System32\Wbem\WMIC.exe"
_audit_startup_signature()

def _wrong_interpreter():
    try:
        exe = Path(sys.executable).resolve()
        exe_str = str(exe).casefold()
        exe_name = exe.name.casefold()
        expected_scripts_dir = (Path(__file__).parent / ".venv312" / "Scripts").resolve()

        # Allow if the interpreter is the venv's Scripts python executable
        if exe.parent.resolve() == expected_scripts_dir:
            return False

        # Allow if the exact interpreter path is whitelisted in ALLOWED_EXES
        try:
            if exe_str in ALLOWED_EXES:
                return False
        except Exception:
            pass

        # Otherwise, require the interpreter to be a python executable from the venv
        if exe_name not in ("python.exe", "pythonw.exe"):
            return True

        return True
    except Exception:
        return True


def _audit_wrong_interpreter():
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        extless = AUDIT_LOG_PATH.with_suffix("")
        if extless.exists() and extless.is_file():
            extless.unlink()
    except Exception:
        pass
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"- [{ts}] Watcher exited due to wrong interpreter: {sys.executable}\n")
        try:
            tb_lines = traceback.format_stack(limit=30)
            for line in tb_lines:
                f.write(f"- [{ts}] {line.rstrip()}\n")
        except Exception:
            pass

def _audit_lock_denied():
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        extless = AUDIT_LOG_PATH.with_suffix("")
        if extless.exists() and extless.is_file():
            extless.unlink()
    except Exception:
        pass
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"- [{ts}] Watcher exited because another instance is running.\n")

def _acquire_mutex():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None, False
    already_exists = ctypes.windll.kernel32.GetLastError() == 183
    return handle, already_exists

if _wrong_interpreter():
    _audit_wrong_interpreter()
    os._exit(1)

_MUTEX_HANDLE, _MUTEX_EXISTS = _acquire_mutex()
if _MUTEX_HANDLE is None or _MUTEX_EXISTS:
    _audit_lock_denied()
    os._exit(1)

import time
import traceback
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from curator_core import VAULT, curate_file, audit_line, load_rules, AUDIT_LOG
from apply_links import apply_approved_reviews, REVIEW_FILE

# Debounce to avoid multiple rapid triggers on a single save
PENDING = {}
LAST_PROCESSED = {}
DEBOUNCE_SECONDS = 2.0
REVIEW_SCAN_SECONDS = 1.0
HEARTBEAT_SECONDS = 12.0

def _list_non_venv_watchers():
    try:
        proc = subprocess.run(
            [
                WMIC_PATH,
                "process",
                "where",
                "ExecutablePath='C:\\\\Program Files\\\\Python312\\\\python.exe' and CommandLine like '%%watcher.py%%'",
                "get",
                "CommandLine,ProcessId",
                "/FORMAT:CSV",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if not proc.stdout:
            return []
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            return []
        rows = []
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        for row in reader:
            pid = (row.get("ProcessId") or "").strip()
            cmd = (row.get("CommandLine") or "").strip()
            if pid:
                rows.append((pid, cmd))
        return rows
    except Exception:
        return []

def _kill_non_venv_watchers():
    killed = []
    for pid, cmd in _list_non_venv_watchers():
        try:
            proc = subprocess.run(
                [
                    WMIC_PATH,
                    "process",
                    "where",
                    f"ProcessId={pid}",
                    "call",
                    "terminate",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if "ReturnValue = 0" in (proc.stdout or ""):
                killed.append((pid, cmd))
        except Exception:
            pass
    return killed

def cleanup_extensionless_files():
    targets = [AUDIT_LOG, REVIEW_FILE]
    for md_path in targets:
        if md_path.suffix.lower() != ".md":
            continue
        extless_path = md_path.with_suffix("")
        if md_path.exists() and extless_path.exists() and extless_path.is_file():
            try:
                extless_path.unlink()
            except Exception:
                pass

class Handler(FileSystemEventHandler):
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
        PENDING[str(p)] = time.time()

def main():
    rules = load_rules()
    cleanup_extensionless_files()
    watch_folders = rules.get("watch_folders", [])
    pid = os.getpid()
    session_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{pid}"
    audit_line(f"Curator watcher started. session={session_id}")
    kill_scan_seconds = float(rules.get("watcher_kill_scan_seconds", 5.0))

    obs = Observer()
    handler = Handler()

    for folder in watch_folders:
        watch_path = VAULT / folder
        watch_path.mkdir(parents=True, exist_ok=True)
        obs.schedule(handler, str(watch_path), recursive=True)
        audit_line(f"Watching: {watch_path}")

    obs.start()

    exit_reason = "normal"
    try:
        while True:
            now = time.time()
            if (now - LAST_PROCESSED.get("_kill_scan", 0)) >= kill_scan_seconds:
                killed = _kill_non_venv_watchers()
                for pid, cmd in killed:
                    msg = f"Killed non-venv watcher PID {pid}"
                    if cmd:
                        msg += f": {cmd}"
                    audit_line(msg)
                LAST_PROCESSED["_kill_scan"] = now
            if (now - LAST_PROCESSED.get("_heartbeat", 0)) >= HEARTBEAT_SECONDS:
                audit_line(f"Watcher heartbeat session={session_id} pid={pid}")
                LAST_PROCESSED["_heartbeat"] = now
            if (now - LAST_PROCESSED.get("_review_scan", 0)) >= REVIEW_SCAN_SECONDS:
                try:
                    applied = apply_approved_reviews()
                    if applied:
                        audit_line(f"Applied approved review links: {applied}")
                except Exception as e:
                    audit_line(f"ERROR applying approved reviews: {e}")
                LAST_PROCESSED["_review_scan"] = now

            ready = [p for p, t in list(PENDING.items()) if (now - t) >= DEBOUNCE_SECONDS]
            for p in ready:
                PENDING.pop(p, None)
                if (now - LAST_PROCESSED.get(p, 0)) < DEBOUNCE_SECONDS:
                    continue
                LAST_PROCESSED[p] = now
                try:
                    curate_file(Path(p))
                except Exception as e:
                    audit_line(f"ERROR curating {p}: {e}")
            time.sleep(0.25)
    except KeyboardInterrupt:
        exit_reason = "keyboardinterrupt"
        audit_line(f"Watcher exiting session={session_id} pid={pid} reason=keyboardinterrupt")
    except Exception as e:
        exit_reason = "exception"
        audit_line(
            f"Watcher exception session={session_id} pid={pid} type={type(e).__name__} message={e}"
        )
        tb_lines = traceback.format_exc().splitlines()[:30]
        for line in tb_lines:
            audit_line(line)
    finally:
        if exit_reason == "normal":
            audit_line(f"Watcher exiting session={session_id} pid={pid} reason=normal")
        elif exit_reason == "exception":
            audit_line(f"Watcher exiting session={session_id} pid={pid} reason=exception")
        obs.stop()
        obs.join()
        audit_line("Curator watcher stopped.")

if __name__ == "__main__":
    main()
