# JARVIS ecosystem separation

- `jarvis-personal`: private owner system. Supabase Personal only. Local ports API 8000 / UI 5173.
- `jarvis-users`: SaaS app. Supabase Users only. Local ports API 8001 / UI 5174.
- Personal never reads the Users database directly. The only bridge is Personal backend -> Users `/admin/*` using `JARVIS_ADMIN_API_KEY`.
- Never expose `JARVIS_ADMIN_API_KEY` in either frontend.
- Keep independent Git repositories. The legacy parent `.git` belongs to the old Personal monolith and should be moved into `jarvis-personal/.git` once, then initialize `jarvis-users` separately.
