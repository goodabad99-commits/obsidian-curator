# Codex Resume – Obsidian Curator

## Environment (Confirmed)
- OS: Windows
- Python: 3.12 installed at:
  C:\Python312\python.exe
- Virtual environment:
  C:\Users\Yousuf\Documents\vault\Scripts\Curator\.venv312
- Curator is expected to run ONLY using:
  .\.venv312\Scripts\python.exe

## Current State (Stable)
- watcher.py exists and runs under the venv.
- curator_core.py:
  - audit_line() is FIXED
  - Writes ONLY to:
    C:\Users\Yousuf\Documents\vault\99_Logs\curator_audit.md
  - Deletes extensionless sibling (curator_audit) before writing.
- apply_links.py:
  - Review queue path fixed to:
    C:\Users\Yousuf\Documents\vault\97_Reviews\link_review_queue.md
  - [x] approvals apply links ONLY under ## Links and mark them applied.
- rules.yaml:
  - watcher_kill_scan_seconds configurable (default 5s).

## Guards in Place
- watcher.py has an interpreter guard:
  - Exits immediately (with audit log entry) if NOT run from:
    C:\Users\Yousuf\Documents\vault\Scripts\Curator\.venv312\Scripts\python.exe
- watcher.py includes a periodic killer:
  - Terminates any system-Python watcher.py process (e.g. from C:\Program Files\Python312\python.exe).
  - Logs ONLY when a kill actually occurs (PID + command line).

## Verified Behavior
- Extensionless curator_audit does NOT persist.
- curator_audit.md receives:
  - "Curator watcher started"
  - Watching paths
- Review queue and audit paths are correct.

## Current Issue (Unresolved)
- watcher.py STARTS successfully (audit confirms).
- watcher.py EXITS within ~60 seconds.
- WMIC shows no watcher.py process after ~60s.
- No session / heartbeat / exit lines observed yet in the last log tail.

## What Was Added to Diagnose
- Session ID logging (timestamp + PID) on startup.
- Heartbeat logging every ~30s.
- Exit logging in finally block (exception / normal / keyboardinterrupt).

## Immediate Task for Codex
1. Inspect curator_audit.md and locate the MOST RECENT session block.
2. Extract:
   - session id
   - pid
   - heartbeat lines
   - exit line (or absence of heartbeat)
3. Identify WHY watcher exits before 60s:
   - guard misfire
   - mutex/lock logic
   - self-termination from kill loop
   - unhandled exception
   - thread exit / observer shutdown
4. Propose the MINIMAL fix to keep watcher alive indefinitely.

## Constraints
- Do NOT remove safety guards.
- Do NOT disable review queue.
- Do NOT reintroduce extensionless files.
- Prefer smallest possible change.
