"""The adversarial battery every Labs guard must pass (shared by the tests and the mutation tests).

Each case is an environment an attacker, or a tired developer, could run Labs
with. All must be refused. Hostnames are the public shapes of hosted services;
no real credential or project id appears here.
"""
from __future__ import annotations

LOCAL_DSN = "postgresql://postgres:@127.0.0.1:5432/dincr_labs"

REFUSED_DSNS = {
    "production Supabase pooler": "postgresql://postgres.abcdefgh:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    "production Supabase direct": "postgresql://postgres:pw@db.abcdefghijkl.supabase.co:5432/dincr_labs",
    "Render database": "postgresql://u:pw@dpg-example.oregon-postgres.render.com/dincr_labs",
    "remote IP": "postgresql://u:pw@203.0.113.10:5432/dincr_labs",
    "remote hostname": "postgresql://u:pw@db.internal.example:5432/dincr_labs",
    "remote host in query": "postgresql:///dincr_labs?host=db.abcdefghijkl.supabase.co",
    "remote hostaddr in query": "postgresql://127.0.0.1/dincr_labs?hostaddr=203.0.113.10",
    "multi-host with a remote one": "postgresql://127.0.0.1,203.0.113.10/dincr_labs",
    "service file redirect": "postgresql://127.0.0.1/dincr_labs?service=prod",
    "product domain": "postgresql://u:pw@db.dincr.com/dincr_labs",
    "tunnel to the Supabase pooler": "postgresql://postgres.abcdefghijklmnopqrst:pw@127.0.0.1:6543/dincr_labs",
    "loopback DSN naming hosted infrastructure": "postgresql://127.0.0.1:5432/dincr_labs?application_name=db.abcdefghijkl.supabase.co",
    "non-Labs database name": "postgresql://postgres:@127.0.0.1:5432/postgres",
    "not postgres": "mysql://root@127.0.0.1/dincr_labs",
    "empty": "",
}

ACCEPTED_DSNS = {
    "loopback v4": LOCAL_DSN,
    "localhost": "postgresql://postgres@localhost:5432/dincr_labs_test",
    "loopback v6": "postgresql://postgres@[::1]:5432/dincr_labs",
    "unix socket": "postgresql://postgres@/dincr_labs?host=/tmp/pgserver",
}


def labs_env(**extra: str) -> dict[str, str]:
    return {"DINCR_ENV": "labs", "DINCR_LABS_DATABASE_URL": LOCAL_DSN, "PATH": "/usr/bin", **extra}


REFUSED_ENVIRONMENTS = {
    "DINCR_ENV missing": {k: v for k, v in labs_env().items() if k != "DINCR_ENV"},
    "DINCR_ENV production": labs_env(DINCR_ENV="production"),
    "DINCR_ENV development": labs_env(DINCR_ENV="development"),
    "DINCR_ENV LABS (case)": labs_env(DINCR_ENV="LABS"),
    "production Supabase URL": labs_env(SUPABASE_URL="https://abcdefghijkl.supabase.co"),
    "Supabase service key": labs_env(SUPABASE_SERVICE_ROLE_KEY="x"),
    "production backend (Render)": labs_env(RENDER="true"),
    "production backend URL": labs_env(RENDER_EXTERNAL_URL="https://example.onrender.com"),
    "production Gmail OAuth": labs_env(FINVA_GMAIL_CLIENT_SECRET="x"),
    "production OAuth redirect": labs_env(FINVA_GMAIL_REDIRECT_URI="https://api.dincr.com/user-product/vip/gmail/callback"),
    "Owner Gmail OAuth": labs_env(GMAIL_CLIENT_SECRET="x"),
    "production billing (Google)": labs_env(DINCR_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON="{}"),
    "production billing (sandbox switch)": labs_env(DINCR_STORE_ACCEPT_SANDBOX="1"),
    "SMTP password": labs_env(SUPPORT_SMTP_APP_PASSWORD="x"),
    "Owner private configuration": labs_env(JARVIS_OWN_ACCOUNT_IBANS="x"),
    "Microsoft OAuth client": labs_env(MICROSOFT_CLIENT_ID="x"),
    "Discord webhook": labs_env(SUPPORT_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/x"),
    "push keys": labs_env(VAPID_PRIVATE_KEY="x"),
    "analytics": labs_env(POSTHOG_API_KEY="x"),
    "AI provider key": labs_env(OPENAI_API_KEY="x"),
    "unknown future secret": labs_env(SOME_NEW_PROVIDER_API_KEY="x"),
    "unknown future token": labs_env(NEW_SERVICE_TOKEN="x"),
    "empty string still counts": labs_env(SUPABASE_URL=""),
    "DATABASE_URL to production": labs_env(DATABASE_URL="postgresql://u:pw@db.abcdefghijkl.supabase.co/postgres"),
    "DATABASE_URL differs": labs_env(DATABASE_URL="postgresql://postgres:@127.0.0.1:5432/dincr_labs_other"),
    "libpq PGHOST": labs_env(PGHOST="db.abcdefghijkl.supabase.co"),
    "libpq PGSERVICE": labs_env(PGSERVICE="prod"),
    "Labs DSN to production": labs_env(DINCR_LABS_DATABASE_URL="postgresql://u:pw@db.abcdefghijkl.supabase.co/dincr_labs"),
}
