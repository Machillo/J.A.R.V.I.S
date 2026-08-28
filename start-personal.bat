@echo off
start "JARVIS Personal API" cmd /k "cd /d %~dp0jarvis-personal && python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
start "JARVIS Personal Frontend" cmd /k "cd /d %~dp0jarvis-personal\frontend && npm run dev"
