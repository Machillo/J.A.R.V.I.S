# The Owner role

DINCR Owner (JARVIS) is internal and never purchasable. The role is **explicit**: nothing infers it, and no configuration change can promote or demote anyone.

| Key | Where | Who changes it |
|---|---|---|
| Stored role `owner` | `allowed_users.role` and `accounts.role` (always equal) | Only `backend/scripts/set_owner_role.py`, a reviewed command run behind BACKUP_VERIFIED |
| `OWNER_EMAILS` | Render environment | A human, per deployment |

A session is Owner only when **both** keys agree (`backend/auth/owner_role.py`). The same rule applies to the Owner bridge.

| Situation | Result |
|---|---|
| Stored `owner` and email listed | Owner |
| Stored `owner` and email not listed (removed, empty or misconfigured variable) | Login refused (403) with no downgraded User session, and nothing written. Owner access comes back when the configuration does. |
| Stored `user` and email listed | User. Being listed never promotes. |
| Login | Never writes the role. |

**Grant:**
1. Add the email to `OWNER_EMAILS`.
2. The person signs in once, which creates the account.
3. Run `python3.11 -m backend.scripts.set_owner_role --email-from-env VAR --grant` as a dry run, then again with `--apply`.

**Revoke:**
1. Run `--revoke --apply`.
2. Remove the email from `OWNER_EMAILS`. Removing it alone already ends access immediately.

The script reads the email from an environment variable and prints only counts.
