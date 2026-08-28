# JARVIS Users

Clean multi-user SaaS baseline. This repository is independent from JARVIS Personal and uses its own Supabase project/database.

## Local backend

Create `backend/.env` from `backend/.env.example`, then:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## Local frontend

Create `frontend/.env` from `frontend/.env.example`, then:

```bash
cd frontend
npm install
npm run dev
```

Do not commit either `.env` file.
