# Google OAuth verification: DINCR (project `jarvis-auth-498317`)

Evidence for the "[Action Needed] Your Google APIs Verification Request" email of 2026-09-25, updated for the pre-launch architecture:
- **#232:** the private Owner generative AI is retired.
- **#233:** the Owner uses the standard per-account mailbox OAuth flow.
- **Privacy Policy v4:** the `docs(privacy)` PR.

Everything below comes from the repository. Items marked **MANUAL** must be confirmed in Google Cloud Console, Render, production or the submitted video.

#232, #233 and the privacy PR (#234) are merged into `main`.

**2026-09-26 revision.** Google answered that the `gmail.readonly` justification is insufficient, and that the scopes in code, in Console, on the consent screen and in the video must match exactly. This revision adds:
- the exact scope set (section 8);
- the video script (section 8);
- the reviewer account (section 8b);
- the analysis of narrower scopes (section 8c);
- step-by-step Console changes (section 10);
- a new reply and justification (section 11).

The code now requests `gmail.readonly` alone and rejects a consent that does not grant it (the `fix/gmail-granted-scope` PR). **The statements about that behavior are true only once that PR is deployed; send nothing before then.**

## 1. Scopes

| Scope | Where requested | DINCR feature | Narrower alternative | Google class | Needed |
|---|---|---|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | `backend/user_product/gmail_service.py` (`GMAIL_SCOPE`, `begin_gmail_connection`: only this scope, no `include_granted_scopes`, `access_type=offline`, PKCE S256, server-side state; the callback refuses a token whose granted `scope` lacks it) | VIP and Owner "Correos financieros": reads notices from admitted financial senders only (`FINVA_QUERY` plus the CCSS payroll-order query) to propose transactions the user reviews, detect accounts, reconcile statements (PDF attachments) and compute the aguinaldo | None. `gmail.metadata` gives no bodies or attachments. The add-on scopes only work inside Gmail add-ons. | **Restricted** | Yes |
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
- `finva_gmail_connections` holds one row per `(account_id, workspace_id, google_email)`, with its own Vault secret, sync state, watch and disconnect.
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

## 8. Demo video (script) and checklist

Google's 2026-09 feedback: the scopes **requested in code**, **listed in Cloud Console**, **shown on the consent screen** and **shown in the video** must be the same set. For DINCR that set is exactly:

| # | Scope | Class | Requested by |
|---|---|---|---|
| 1 | `openid` | non-sensitive | Supabase "Sign in with Google" |
| 2 | `https://www.googleapis.com/auth/userinfo.email` (`email`) | non-sensitive | Supabase "Sign in with Google" |
| 3 | `https://www.googleapis.com/auth/userinfo.profile` (`profile`) | non-sensitive | Supabase "Sign in with Google" |
| 4 | `https://www.googleapis.com/auth/gmail.readonly` | **restricted** | "Correos financieros" (`gmail_service.begin_gmail_connection`) |

If Supabase sign-in uses an OAuth client of **another** Google Cloud project, rows 1–3 do not belong to this project: the list is then only row 4. **MANUAL:** check which client ID Supabase → Authentication → Providers → Google uses.

**Script** (screen recording of the Android or iOS app plus the browser, 3–4 min, English captions or narration):

| Time | Show | Say / caption |
|---|---|---|
| 0:00 | The app icon and name "DINCR" | "DINCR is a personal finance app for Costa Rica. This video shows how it uses the Gmail read-only scope." |
| 0:15 | Sign in with Google | "Users sign in with Google (openid, email, profile)." |
| 0:35 | Perfil → Correos financieros (VIP) | "Connecting Gmail is optional, VIP-only and started by the user." |
| 0:50 | The in-app explanation sheet: what is read (only notices from a fixed list of bank and payroll senders), what is stored, how to disconnect; the user accepts | "Before Google's screen, DINCR explains exactly what it reads and stores." |
| 1:10 | Tap "Conectar Gmail" → Google account chooser → **consent screen**. Pause on it and **zoom into the app name "DINCR" and the permission "View your email messages and settings"** | "The consent screen shows DINCR and the single Gmail permission: read-only." |
| 1:40 | Tick the permission and continue; back in the app, "Conectado" | "The token is stored encrypted on our server and never on the phone." |
| 1:55 | The list of detected movements; open one; show amount, date, bank, last four digits; tap **Aceptar**, then **Corregir** on another, **Rechazar** on a third | "Each notice becomes a proposed transaction; the user accepts, corrects or rejects it. Nothing is written without review." |
| 2:40 | Show a statement (PDF attachment) result and the aguinaldo estimate, if the test mailbox has them | "PDF statements from the same senders are read to reconcile balances. Bodies and PDFs are not stored." |
| 3:00 | Perfil → Correos financieros → **Desconectar** | "Disconnecting deletes the token and revokes it with Google." |
| 3:15 | End card: the privacy policy URL and the Limited Use sentence | "DINCR complies with the Google API Services User Data Policy, including Limited Use. No Gmail data reaches any AI provider." |

Before uploading, check:
- [ ] The consent screen shows "DINCR" and **only** `gmail.readonly` in the Gmail step (and only openid/email/profile at sign-in).
- [ ] The OAuth client in the URL bar (`client_id=`) is the same one listed in Console (zoom it once).
- [ ] The path Perfil → Correos financieros → explanation → Conectar Gmail is shown.
- [ ] Accept, correct and reject are shown on real (test-mailbox) notices.
- [ ] Disconnect is shown.
- [ ] The language is understandable, with English captions if the UI is in Spanish.
- [ ] No personal data of a real person appears (use the reviewer test account below).

## 8b. Reviewer test account and steps

- **Account:** a dedicated Google account created only for review (never a real user's). Its password goes into the Google review form's "test credentials" field only, never into the repo or the reply email.
- **Mailbox content:** forward to it a few synthetic notices from the supported senders, or use `backend/scripts/seed_review_demo.py` so the review list is not empty. **MANUAL:** confirm the reviewer will see at least one notice.
- **Access:**
  - the app through Google Play internal testing (add the reviewer address to the testers list) or TestFlight;
  - VIP comes from the launch promotion (no payment), or an Owner courtesy on that account;
  - `gmail_automation` enabled in production.
- **Steps for the reviewer:** install → Sign in with Google (test account) → accept Terms and Privacy → choose VIP → Perfil → Correos financieros → read the explanation → Conectar Gmail → allow → review the detected movements → optionally Desconectar.

## 8c. Why `gmail.readonly` and not a narrower option

| Option | Why it does not work for DINCR |
|---|---|
| `gmail.metadata` | Headers and labels only: no bodies and no attachments, and Gmail rejects the `q` search parameter with it. DINCR must read the amount, date and card in the body and the PDF statements. |
| `gmail.addons.current.message.readonly` / `.metadata` | Only valid inside a Gmail add-on for the message the user opens; DINCR is a mobile app that processes notices in the background. |
| `gmail.labels`, `gmail.send`, `gmail.compose`, `gmail.insert` | Do not allow reading. |
| `gmail.modify` / full `mail.google.com` | Broader; DINCR never changes, sends or deletes mail. |
| No Gmail scope (the user forwards notices to a DINCR address) | Considered. It avoids the restricted scope but moves every bank notice through a third inbox DINCR controls, loses PDF statements and history, and depends on bank-specific forwarding rules. Kept as a possible future alternative; the in-app Gmail connection stays optional and users can always enter data manually. |

**Minimization inside the scope** (these are what the justification must stress):
- one search restricted to a fixed allowlist of bank and CCSS payroll sender addresses (`FINVA_QUERY`), excluding spam and trash, with a bounded window;
- the From header is re-verified per message (`bank_sender_allowed`);
- bodies and PDFs are processed in memory and not stored; only the extracted fields, sender/subject for 90 days and review evidence for 30 days;
- deterministic parsers, no AI, no human reading of mail;
- the token is used only by the backend and revoked on disconnect or account deletion;
- a consent without the Gmail permission is refused and its grant revoked (`permission_missing`).

## 9. CASA

`gmail.readonly` is restricted, and DINCR's servers (Render and Supabase) store and process Gmail-derived data. An annual CASA assessment is therefore **required**. The architecture change does not remove it; it only removes the AI and legacy-token findings a CASA assessor would raise.

## 10. Google Cloud Console: exact steps (MANUAL, in this order)

Project `jarvis-auth-498317`. Record evidence (a screenshot without secrets) of each screen after the change, in the private evidence folder, not in the repo. "Current value" is what Console shows today: read it first; this repo cannot see it.

| # | Screen | Current value | New value | Scope / field | Evidence |
|---|---|---|---|---|---|
| 1 | Google Auth Platform → **Data Access** (OAuth consent screen → Scopes) | Read the list | Exactly rows 1–4 of section 8 (or only row 4 if sign-in uses another project). Remove every other scope, sensitive or not. | Scopes | Screenshot of the scope list |
| 2 | Data Access → `gmail.readonly` → **justification** text | The text Google rejected | The text in section 11b below | Restricted-scope justification | Screenshot |
| 3 | Data Access → **demo video link** | Current video | The new video (section 8), unlisted YouTube | Video | The URL |
| 4 | **Branding** | Read | App name `DINCR`; support email; logo; homepage `https://dincr.com/`; privacy `https://dincr.com/privacidad/`; terms `https://dincr.com/terminos/`; authorized domains `dincr.com` (+ the Supabase domain only if sign-in uses this project) | Branding | Screenshot |
| 5 | **Clients** → the web client whose ID equals `FINVA_GMAIL_CLIENT_ID` in Render | Read the redirect URIs | Only `https://api.dincr.com/user-product/vip/gmail/callback` (+ the Supabase callback only if sign-in uses this client). Remove legacy Render and OAuth Playground URIs (section 6). | Redirect URIs | Screenshot |
| 6 | Clients → other clients | Read | Delete clients that no code uses (after confirming none is the Supabase or Firebase one) | Clients | List before/after |
| 7 | **Audience** | In production | Unchanged | Publishing status | — |
| 8 | **Verification Center** | "Action needed" | Resubmit only after 1–5 are done and the new video is uploaded | Submission | Screenshot of the submitted state |

Render and Supabase checks that must agree:
- Render: `FINVA_GMAIL_CLIENT_ID` = the client of step 5; `FINVA_GMAIL_REDIRECT_URI` = the URI of step 5.
- Supabase → Authentication → Providers → Google: which client ID (decides rows 1–3).
- Code: `GMAIL_SCOPE` = `gmail.readonly` is the only Google API scope (`git grep googleapis.com/auth`).

## 11. Reply draft (NOT sent; send only after section 10 is done and the new video is uploaded)

> Hello Google Developer Review Team,
>
> Thank you for the feedback on DINCR (project jarvis-auth-498317). We have aligned the requested scopes, the Cloud Console configuration, the consent screen and the demo video, and we are providing a more detailed justification for gmail.readonly.
>
> **Scopes.** The app requests exactly: openid, email and profile (Google Sign-In) and https://www.googleapis.com/auth/gmail.readonly (optional "Financial emails" feature). No other scope is requested in code or configured in Console. The Gmail authorization request asks for gmail.readonly alone (it does not merge previously granted scopes), and a consent in which the user does not grant it is rejected and revoked.
>
> **Why gmail.readonly is needed.** DINCR is a personal finance app for Costa Rica. With the user's explicit, optional consent (VIP plan, Profile → Financial emails), DINCR searches the user's mailbox only for messages from a fixed list of bank and social-security payroll sender addresses, excluding spam and trash. From each notice it extracts the amount, date, currency, bank and card's last four digits, and from PDF statements attached to those messages it reconciles account balances. Each result is shown to the user as a proposed transaction that they accept, correct or reject; nothing is recorded without that review. This requires reading message bodies and PDF attachments, and using Gmail search to restrict access to the allowed senders.
>
> **Why narrower scopes are insufficient.** gmail.metadata provides no message bodies or attachments and does not allow the search query we use to limit access to bank senders. The Gmail add-on scopes only work inside a Gmail add-on for the message being viewed, while DINCR is a mobile app that processes notices in the background. DINCR never modifies, sends or deletes email, so no broader scope is requested.
>
> **Data handling.** Refresh tokens are stored encrypted on our server (Supabase Vault) and never reach the device. Message bodies and attachments are processed in memory and not stored; only the extracted transaction fields are kept, review evidence is deleted after 30 days and sender/subject metadata after 90 days. Processing is deterministic (templates); no person reads the emails. Disconnecting Gmail or deleting the account deletes the token and revokes it with Google.
>
> **Limited Use.** DINCR's use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements. Google Workspace API data is not transferred to any AI provider and is not used to develop, improve or train AI/ML models; it is not sold, not used for advertising and not used for credit decisions. See https://dincr.com/privacidad/.
>
> **Demo video.** [URL] shows Google Sign-In, the in-app explanation, the consent screen with the Gmail read-only permission (client ID visible), the review of detected transactions (accept, correct, reject) and disconnection.
>
> **Test access.** Test account credentials and installation instructions are provided in the verification form.
>
> **Security assessment.** We understand gmail.readonly is a restricted scope and will complete the CASA assessment as instructed.
>
> Kind regards,
> DINCR team

### 11b. Console justification text for `gmail.readonly` (paste into Data Access)

> DINCR (personal finance, Costa Rica) offers an optional, user-initiated feature that reads bank transaction notices and PDF account statements sent by a fixed list of bank and payroll sender addresses. It searches only those senders (Gmail search query), extracts amount, date, currency, bank and card last four digits, and shows each as a proposed transaction the user must accept, correct or reject. It needs message bodies and attachments, so gmail.metadata is insufficient; add-on scopes do not apply to a mobile app. DINCR never modifies, sends or deletes mail. Tokens are encrypted server-side; bodies and attachments are not stored; processing is deterministic, with no AI and no human access. Users can disconnect at any time, which revokes the token.
