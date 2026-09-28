# Security audit 2026-09 (pre-launch)

**Scope:** backend, mobile/web client, landing, database and migrations, CI/CD. **Method:** the cloudflare/security-audit-skill methodology, source-first:
- reconnaissance;
- five domain hunters: identity; authorization and tenancy; OAuth, webhooks and inputs; client and mobile; infrastructure and supply chain;
- an independent verifier that also re-audited the fixes;
- machine-readable findings (`findings.json`, following the skill's `report-schema.json`).

Agents did not execute target code (no OS sandbox). Behavior was proven with the repository's own tests. Private run artifacts live outside the repository.

## Result
- **CRITICAL: 0. HIGH: 0.**
- **Confirmed:** 2 medium, 7 low.
- **Needs validation:** 7 (deployment or console facts).
- **Rejected:** 6.

| Finding | Severity | Fix |
|---|---|---|
| The Gmail sync accepted a CCSS payroll order from any sender and overwrote the salary history (aguinaldo) with no review | medium | CCSS parsing only for `ccss.sa.cr` senders; the search no longer lists mail by subject alone |
| Authentication ran blocking I/O on the event loop (any Bearer string could stall the API) | medium | The middleware's I/O runs in the thread pool (separate PR) |
| `/auth/me` and the export exposed the granting Owner's account id and internal courtesy note | low | Stripped from User responses and the export |
| Kill switches missed Outlook/OAuth completion and several write routes | low | Every applicable flag is evaluated per request |
| Concurrent debt payments lost a balance reduction | low | Row lock (`FOR UPDATE`) |
| Discord webhook secret could reach the logs | low | Log the exception type only |
| IBKR writer resolved the Owner across two legacy identity spaces (latent; the ids match today) | low | Resolve through `allowed_users → accounts`; fail closed |
| VIP debt advisory uses the Owner-calibrated cycle engine | low | Backlog (shared finance engines review) |
| Owner IBKR bridge installs an unpinned `ibapi` | low | Pin with hashes or install from IB's distribution |

**Needs validation.** Each item names the fact to check:
- the Supabase "Confirm email" / "Secure email change" settings (this item would be critical only if both were off and an Owner email were unbound; production has 0 unbound rows);
- DMARC of the CCSS and bank domains;
- body-size limits at the edge;
- Render access-log query strings;
- Postgres error-log settings;
- the production database role attributes;
- the CPU cost of parsing mail before the sender check.

**Application-name residual (#245).** The audit confirmed that `application_name` is not used as a boundary anywhere except the documented delete-guard exemption. The dedicated login below replaces that exemption with a real one.

## Dedicated database login for the backend (follow-up of #245): still needed, and the design

**Is it still needed? Yes.** Today the backend connects as `postgres` through Supavisor. So:
- The only barrier between tenants is the application's `WHERE workspace_id = …`. RLS is bypassed.
- Every Vault secret (all mailbox refresh tokens) is readable by any backend code path.
- The backend can run DDL, and could disable the #245 triggers.
- The #245 delete guard exempts the application by `application_name`, which is **not** a boundary. Supavisor rewrites it to `Supavisor`, and any client can set it.

None of this is exploitable without another bug; no injection was found in the audit (every f-string SQL site was checked). But a dedicated login turns an app bug into a limited one, and makes the guard exemption real.

**Design (phased, each phase a reviewed migration plus a Render secret change, never applied automatically):**

1. **Phase 1: same behavior, least privilege.**
   - **Role:** `CREATE ROLE dincr_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS`. It keeps today's semantics, because app tables have RLS on and no policies.
   - **Grants:**
     - `GRANT USAGE ON SCHEMA public`;
     - `SELECT, INSERT, UPDATE, DELETE` on an explicit table list;
     - `USAGE, SELECT` on their sequences;
     - no `TRUNCATE`, `TRIGGER` or `REFERENCES`, and it owns nothing.
   - **Denied:** `auth`, `storage` and `vault` schemas.
   - **Vault:** only through `SECURITY DEFINER` functions owned by `postgres` in a private schema, each with `SET search_path = pg_catalog, pg_temp`, `REVOKE ALL FROM PUBLIC` and `GRANT EXECUTE TO dincr_app`:
     - `mail_secret_create(account uuid, token text)`;
     - `mail_secret_read(connection_id bigint, account uuid)`, which checks connection ownership;
     - `mail_secret_delete(secret uuid, account uuid)`.
   - **#245 delete guard:** the exemption becomes `session_user = 'dincr_app'`. Supavisor authenticates as the real role (`dincr_app.<project_ref>`), so this is a real boundary. The SQL editor and scripts running as `postgres` must then declare their workspace, which is the intent.
   - **PRE-MERGE GATE:**
     - remove the remaining runtime DDL (email_monitor, strategy_dashboard, advisor, deployment_monitor, intelligence, memory_service, ibkr_readonly), since it fails without table ownership;
     - create the role and grants by migration;
     - set the new `DATABASE_URL` in Render;
     - then merge.
   - **Test first:** run the whole backend suite against a database where the app role is `dincr_app` (the PostgreSQL tests can do this).
2. **Phase 2: RLS as a second wall.**
   - Drop `BYPASSRLS`.
   - Add per-table policies `TO dincr_app USING (workspace_id = current_setting('dincr.workspace_id')::uuid)`.
   - Set `dincr.workspace_id` with `set_config(..., true)` in each transaction from the session context. It is transaction-local, so it is safe in Supavisor transaction mode.
