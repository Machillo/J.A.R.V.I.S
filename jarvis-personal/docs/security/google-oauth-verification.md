# Google OAuth verification: DINCR (project `jarvis-auth-498317`)

Evidence for the "[Action Needed] Your Google APIs Verification Request" email of 2026-09-25, updated for the pre-launch architecture:
- **#232:** the private Owner generative AI is retired.
- **#233:** the Owner uses the standard per-account mailbox OAuth flow.
- **Privacy Policy v4:** the `docs(privacy)` PR.

Everything below comes from the repository. Items marked **MANUAL** must be confirmed in Google Cloud Console, Render, production or the submitted video.

**The statements in this file are true only once #232 and #233 are deployed.** Do not publish the Privacy Policy v4 or send the reply to Google before that.

## 1. Scopes

| Scope | Where requested | DINCR feature | Narrower alternative | Google class | Needed |
|---|---|---|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | `backend/user_product/gmail_service.py` (`GMAIL_SCOPE`, `begin_gmail_connection`: `access_type=offline`, PKCE S256, server-side state) | VIP and Owner "Correos financieros": reads notices from admitted financial senders only (`FINVA_QUERY` plus the CCSS payroll-order query) to propose transactions the user reviews, detect accounts, reconcile statements (PDF attachments) and compute the aguinaldo | None. `gmail.metadata` gives no bodies or attachments. The add-on scopes only work inside Gmail add-ons. | **Restricted** | Yes |
| `openid`, `email`, `profile` | Supabase "Sign in with Google" (`frontend/src/lib/nativeAuth.js`) | Sign-in | Already minimal | Non-sensitive | Yes. **MANUAL:** confirm whether Supabase uses an OAuth client of this same project. |

- **No other Google Workspace scope.** No write, send or delete scope is requested.
- **Legacy reader retired:** the Owner-only legacy reader (`email_monitor._gmail_service`, with one server-held `GMAIL_REFRESH_TOKEN`) was removed in #233. Its endpoints return 410 (sync, cron, watch) or acknowledge without reading (Pub/Sub push).
- **Outlook:** `Mail.Read` is Microsoft, not Google.

## 2. Data flow, from the Gmail API to storage

**1. Consent and OAuth.** The user (any VIP account, the Owner included) accepts the in-app consent (`gmail_consent.py`). The app then opens Google OAuth:
- PKCE S256, with the state hash and verifier stored in `mail_oauth_flows` (`mail_oauth.py`);
- the public callback `/user-product/vip/gmail/callback` exchanges the code, parks the refresh token in **Supabase Vault** and returns a one-time completion code by deep link;
- only the DINCR session that started the flow can attach the mailbox (`/vip/mail/oauth/complete`; account and workspace must match, VIP entitlement re-checked).

**2. Connection.**
- `finva_gmail_connections` holds one row per `(workspace_id, google_email)`, with its own Vault secret, sync state, watch and disconnect.
- A mailbox (Gmail or Outlook) is live in at most one DINCR account and workspace at a time (`mail_oauth.claim_mailbox`).
  - **Identity.** Google's account id (`sub`, from tokeninfo, only for DINCR's client) or Microsoft Graph's user `id` plus tenant, and always the canonical address (gmail.com/googlemail.com without dots or `+tag`). The address shown to the user is display only. Both have a unique index among live rows. Existing rows start with the address identity; `backend/scripts/backfill_mailbox_identity.py` upgrades them (dry run by default, aborts on ambiguity).
  - **Refusal.** A live mailbox of an account with VIP is refused with one generic message that reveals nothing about the other account.
  - **Stale takeover.** A connection that lost provider access (`reauthorization_required`) or whose account no longer has VIP can be taken over. Only a new, real provider consent for that same mailbox does it, never an address typed by someone. In one transaction:
    - the old connection is disconnected;
    - its token is deleted (not reused; not revoked, since revoking would also revoke the new grant);
    - the takeover is audited in `mail_connection_takeovers`, with account ids only.
    Its account keeps everything it imported. No data moves.
  - Disconnecting frees the mailbox.
- Several mailboxes per workspace are supported (tests: two Owner mailboxes, reconnect A keeps B, disconnect A keeps B).

**3. Read.**
- `users.messages.list` runs with the admitted-senders query, and `messages.get` fetches full content.
- The From address is verified (`bank_sender_allowed`).
- PDF attachments are read in memory (`email_monitor/gmail_content.py`).

**4. Parse.** Deterministic templates:
- `email_monitor/parser.py`, `popular_pdf.py` and `payroll_statement.py`, which are pure functions;
- `statement_candidate.py` and `financial_candidate.py`.
No AI is involved.

**5. Stored.**
- `finva_email_messages`: message id, sender, subject, date, bank and status. Sender and subject are cleared after 90 days.
- `finva_email_candidates`: the extracted fields. `raw_payload` is cleared 30 days after review.
- `finva_statement_documents`: hash and attachment names.
- `payroll_salary_reports`: CCSS orders.
- Full bodies and PDFs are **not** stored (`gmail_service._ingest_message`, `gmail_retention.py`, run by the `/vip/gmail/maintenance` cron).

**6. Review.** The user accepts, corrects or rejects each candidate.
- An accepted candidate becomes a `transactions` row (source `finva_gmail` or `finva_statement`) plus a privacy-safe `financial_input_events` row.
- Semantic duplicates (across Gmail mailboxes, Outlook and statements) are resolved deterministically (`candidate_resolution.py`).

**7. Use.** Reports, accounts, strategy and the aguinaldo read `transactions` and `payroll_salary_reports`, with deterministic engines only.

**8. Deletion.**
- Disconnecting deletes the Vault secret and revokes the token with Google (`disconnect_gmail`).
- Account deletion does the same and deletes all derived data (`auth/service.py delete_current_account`).

## 3. AI and ML: Google data cannot reach a generative-AI provider

**Invariant (after #232):** no module the API process can load talks to a generative-AI provider. Nothing in production, Gmail-derived or not, can be sent to OpenAI, Gemini or any other model.

**Evidence:**
- `backend/test_no_generative_ai.py` walks the application **import graph** from `backend/main.py`, lazy imports included. It fails if any reachable module references a provider host (`api.openai.com`, `generativelanguage.googleapis.com`, `aiplatform.googleapis.com`, Anthropic, Mistral, Cohere, Groq), `OPENAI_API_KEY`, Gemini, or an AI SDK import, or if it imports Parser Discovery. The walk includes `user_product/gmail_service.py`.
- `requirements.txt` has no AI SDK.
- `ai/openai_client.py` (the only production OpenAI client) was deleted.
- `jarvis_engine.build_financial_context` (the old Gmail → transactions → AI path) no longer exists; the chat fallback builds no context.
- Gemini was removed earlier (`test_gemini_is_gone`).

**Indirect paths checked:**
- Gmail → parsed transaction → `transactions` → financial context → AI: removed.
- Gmail → statement → aggregates → AI: no AI consumer exists.
- Gmail → account detection → AI: no AI consumer exists.

**Parser Discovery** (`backend/parser_discovery`, `backend/scripts/propose_parser.py`) is offline developer tooling:
- it is not part of the application, and a test proves it is outside the import graph;
- it is off by default (`PARSER_DISCOVERY_ENABLED`);
- it only sends local sample files that pass the sanitizer, and never touches the database or the Gmail API.

Operational rule: samples must never be exported from DINCR user data or from the Gmail API.

**Training:** no Google data is used to develop, improve or train generalized AI/ML models. There is no training pipeline in the repository.

## 4. Environment variables

| Variable | Purpose / current user | Keep or remove | When |
|---|---|---|---|
| `FINVA_GMAIL_CLIENT_ID`, `FINVA_GMAIL_CLIENT_SECRET` | OAuth client of the standard flow (`gmail_service._google_config`) | **Keep** | — |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | Legacy reader (removed) **and** fallback of the standard flow when `FINVA_*` is empty | Remove only after confirming `FINVA_GMAIL_CLIENT_ID/SECRET` are set to the DINCR OAuth client (**MANUAL**, Render) | After #233 is deployed and verified |
| `GMAIL_REFRESH_TOKEN` | Legacy reader only (the Owner's personal mailbox) | **Remove**, and revoke the grant with Google first | After #233 is deployed and both mailboxes are connected through the standard flow |
| `GMAIL_PUBSUB_TOPIC` | Legacy watch only; the standard flow uses `FINVA_GMAIL_PUBSUB_TOPIC` | Remove the variable. **MANUAL:** if its value equals `FINVA_GMAIL_PUBSUB_TOPIC`, keep the topic resource and delete only the push subscription that targets `/email-monitor/gmail-push`. | After #233 |
| `GMAIL_PUBSUB_VERIFICATION_TOKEN` | Legacy push endpoint only | Remove | After #233 |
| `GMAIL_FINANCE_QUERY` | Legacy query default (only shown in the legacy status) | Remove (optional) | After #233 |
| `EMAIL_AUTO_COMMIT_CONFIDENCE` | Legacy `email_monitor` candidate rules (manual text scan) | Keep, or remove to use the default | Optional |
| `EMAIL_MONITOR_CRON_SECRET` | Fallback secret for `/notifications/cron` and the IBKR Flex cron | **Keep** (or set `NOTIFICATION_CRON_SECRET` and `IBKR_FLEX_CRON_SECRET` first) | — |
| `FINVA_GMAIL_REDIRECT_URI`, `FINVA_GMAIL_RETURN_URL`, `FINVA_GMAIL_QUERY` | Standard flow | **Keep** | — |
| `FINVA_GMAIL_PUBSUB_TOPIC`, `FINVA_GMAIL_PUBSUB_VERIFICATION_TOKEN`, `FINVA_GMAIL_CRON_SECRET` | Standard flow push and maintenance | **Keep** | — |
| `OPENAI_API_KEY` | Removed Owner AI; also the local-only Parser Discovery CLI | **Remove from Render.** Revoke in OpenAI if it is not used elsewhere. A developer running Parser Discovery uses a separate local key. | After #232 is deployed |
| `OPENAI_MODEL`, `OPENAI_MONTHLY_BUDGET_USD`, `OPENAI_INPUT_USD_PER_1M`, `OPENAI_OUTPUT_USD_PER_1M`, `OPENAI_OWNER_ONLY`, `OPENAI_TIMEOUT_SECONDS`, `OWNER_WEB_ACCESS_ONLY` | Removed AI modules | **Remove** | After #232 |
| `PARSER_DISCOVERY_*` | Local CLI only | Must not exist in Render | — |
| Gemini keys, service accounts (for example the "JARVIS" API key or service account in Google Cloud) | No production code references a Google API key, `GOOGLE_APPLICATION_CREDENTIALS` or a service account (grep of backend and frontend; `google-auth` is only used with user OAuth credentials) | Candidate for deletion. **MANUAL:** in Console, check its API restrictions and usage metrics first, and do not confuse it with the Firebase "Android key (auto created by Firebase)" used by `google-services.json`. | After #232 |

## 5. Existing Owner data

- **Nothing is deleted.** Legacy transactions, debts, goals, accounts, reports and strategy state stay as they are.
- **Mailbox the legacy reader used:** when the Owner reconnects it through the standard flow, a Gmail message the legacy reader already turned into a transaction in the same workspace is marked `duplicate` (`resolution_reason='legacy_owner_import'`, `user_product/legacy_owner_mail.py`). No new transaction is created unless the user accepts one.
- **Limits:**
  - statement rows and never-committed legacy messages are not correlated and stay pending for review;
  - the second mailbox has no legacy history.
- **Stored bodies:** the legacy reader stored `raw_body` and `body_text` of the Owner's own messages in `email_ingested_messages`. That contradicts the "full bodies are not stored" practice of the standard flow. **Human decision:** clear those two columns for the Owner workspace after the migration (a destructive update, not done in code).

## 6. Redirect URIs (MANUAL; remove only after migration)

| URI | Assessment |
|---|---|
| `https://api.dincr.com/user-product/vip/gmail/callback` | **Keep.** It is the only Gmail callback in code (`FINVA_GMAIL_REDIRECT_URI`). |
| Supabase `https://<project>.supabase.co/auth/v1/callback` | Keep if "Sign in with Google" uses this client. **MANUAL:** compare with Supabase → Auth → Google. Remove any Supabase callback of an old or unused Supabase project. |
| Legacy Render Gmail callback (`*.onrender.com/...`) | No code references it; the standard flow uses `FINVA_GMAIL_REDIRECT_URI`. **Safe to remove** after confirming `FINVA_GMAIL_REDIRECT_URI` is `https://api.dincr.com/...` in Render. |
| OAuth Playground `https://developers.google.com/oauthplayground` | Only used to mint the legacy `GMAIL_REFRESH_TOKEN`. **Safe to remove** after that token is revoked. |

## 7. Reviewer access (no production changes yet)

**Path:**
1. Install the app (Android internal testing or TestFlight; **MANUAL:** Google needs a way to install it).
2. Sign in with Google.
3. Accept Terms and Privacy.
4. Choose VIP (free until 2026-12-31 through the launch promotion, with no payment).
5. Go to Perfil → Correos financieros.
6. Accept the in-app explanation and tap Conectar Gmail.
7. Complete Google consent.
8. Review the detected movements.

**Requirements:**
- `gmail_automation` must be enabled in production (**MANUAL**).
- The reviewer's mailbox needs at least one supported bank notice, or the list is empty. **Option:** a dedicated reviewer account with forwarded synthetic notices, plus `backend/scripts/seed_review_demo.py`.

## 8. Demo video checklist (MANUAL against the submitted video)

- [ ] The consent screen shows "DINCR" and the read-only Gmail scope.
- [ ] Only `gmail.readonly` plus sign-in scopes appear.
- [ ] It shows the path Perfil → Correos financieros → explanation → Conectar Gmail.
- [ ] It shows the result in DINCR: detected movements with accept, correct and reject.
- [ ] The language, or English captions, is understandable.

The flow shown for Users has not changed. #232 and #233 change neither scopes nor the Users flow. #228 adds a sheet before OAuth; mention it if it ships before approval.

**Video status: B**, likely sufficient, pending the manual checklist.

## 9. CASA

`gmail.readonly` is restricted, and DINCR's servers (Render and Supabase) store and process Gmail-derived data. An annual CASA assessment is therefore **required**. The architecture change does not remove it; it only removes the AI and legacy-token findings a CASA assessor would raise.

## 10. Google Cloud Console checks (MANUAL)

| Item | Expected (repo) |
|---|---|
| App name | DINCR |
| User support email | soporte@dincr.com (privacy contact: privacidad@dincr.com) |
| Homepage | https://dincr.com/ |
| Privacy Policy | https://dincr.com/privacidad/ (v4 after deploy; the app also serves `/privacy`) |
| Terms | https://dincr.com/terminos/ |
| Authorized domains | `dincr.com`, plus the Supabase domain if Google sign-in uses this project |
| Redirect URIs | See section 6 |
| Scopes | `gmail.readonly`, plus `openid`, `email`, `profile` only |
| OAuth client | "DINCR OAuth" = the value of `FINVA_GMAIL_CLIENT_ID` in Render |
| Publishing status | In production, verification pending |

## 11. Reply draft (do not send before #232, #233 and Privacy v4 are live)

> Hello Google Developer Review Team,
>
> Thank you for reviewing DINCR (project jarvis-auth-498317).
>
> Scopes: DINCR requests only https://www.googleapis.com/auth/gmail.readonly (plus openid/email/profile for Google Sign-In). It is used exclusively for the optional, user-initiated "Financial emails" feature: DINCR reads messages from a fixed list of supported bank and payroll senders, extracts proposed transactions (date, description, amount, currency, bank, last four digits), and shows them to the user, who accepts, corrects or rejects each one. DINCR never sends, modifies or deletes email. A narrower scope is not sufficient because the feature needs message bodies and PDF statement attachments.
>
> Data handling: refresh tokens are stored encrypted in Supabase Vault and never reach the mobile app. Full message bodies and attachments are not stored; review evidence is deleted after 30 days and sender/subject metadata after 90 days. Disconnecting Gmail or deleting the account deletes the token and revokes it with Google; account deletion also deletes all derived data.
>
> Limited Use and AI: DINCR's use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements. Google Workspace API data, raw or derived, is not transferred to OpenAI or any other generative-AI provider and is not used to develop, improve, or train generalized AI/ML models. It is not sold, not used for advertising, not transferred to data brokers and not used for credit or lending decisions. These statements are in our Privacy Policy: https://dincr.com/privacidad/ (section 6).
>
> Demo video: the submitted video shows the OAuth consent screen with the Gmail read-only scope and the in-app flow (Profile → Financial emails → Connect Gmail → review of detected movements). [Add or adjust per the section 8 checklist.]
>
> Security assessment: we understand gmail.readonly is a restricted scope and we will complete the CASA assessment as instructed.
>
> Kind regards,
> DINCR team
