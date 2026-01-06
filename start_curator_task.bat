@echo off
rem Launcher used by Windows Scheduled Task to start the Curator watcher
cd /d C:\Users\Yousuf\Documents\vault\Scripts\Curator
"C:\Users\Yousuf\Documents\vault\Scripts\Curator\.venv312\Scripts\pythonw.exe" watcher.py
