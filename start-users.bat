@echo off
start "JARVIS Users API" cmd /k "cd /d %~dp0jarvis-users && python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001"
start "JARVIS Users Frontend" cmd /k "cd /d %~dp0jarvis-users\frontend && npm run dev"
