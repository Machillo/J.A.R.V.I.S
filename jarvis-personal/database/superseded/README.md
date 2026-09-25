# Superseded migrations

Files here were replaced by a later migration and must never be applied.
They live outside `database/migrations/` so `backend/scripts/apply_migration.py`
refuses them. Each file names its replacement in its first line.
