# AI in DINCR: Gemini removed, ChatGPT only for internal parser discovery

## Gemini removal

Gemini (`google-genai`, `backend/ai/gemini_client.py`) was used **only by Owner/JARVIS**, never by Users (Free/Basic/VIP) or by ingestion. It served as:

| Call site | Before | Now |
|---|---|---|
| `ai/jarvis_engine.py` internet answer | Gemini, falling back to the first snippet | OpenAI (`ask_openai_optional`), falling back to the first snippet |
| `ai/jarvis_engine.py` finance chat | OpenAI → Gemini fallback | OpenAI only. On failure it returns the existing `AI_ERROR` message |
| `ai/intent_router.py` classifier | deterministic → OpenAI → Gemini | deterministic → OpenAI |
| `ai/response_formatter.py` | Gemini, falling back to deterministic text | OpenAI, falling back to deterministic text |
| `sports/service.py` | Gemini, falling back to the snippet | OpenAI, falling back to the snippet. Background digests have no Owner context, so they use the snippet |

`ask_openai_optional` is a wrapper around the existing budgeted, Owner-only `ask_openai`. It turns any failure (no key, budget, no Owner context) into a normal `ERROR`, so every call site keeps its deterministic fallback.

**HUMAN GATE (production config):** remove `GEMINI_API_KEY`, `GEMINI_MODEL` and `AI_ENABLED` from Render after deploy, and rotate/revoke the Gemini key in Google AI Studio. The local `backend/.env` also still holds them.

## Parser discovery: AI proposes, DINCR executes, humans approve

This is not per-transaction analysis. It is not called by the app or by the ingestion pipeline (a test enforces that). It is an **internal CLI** used only when a bank format is unknown:

1. **Collect.** The Owner saves a few examples of the unknown format as plain text.
   - Only use them with the account holder's consent: an Owner email, or a user's email volunteered for support.
2. **Sanitize locally.**
   ```bash
   python -m backend.scripts.propose_parser sample1.txt sample2.txt
   ```
   - Emails, URLs and names after greeting/holder labels are replaced, and every digit becomes `9`. The layout survives ("₡99.999,99", "99/99/9999") but no real value does.
   - The dry run prints the sanitized text. **Read it.** Uppercase full names without a label are flagged but can slip through.
3. **Propose.**
   ```bash
   PARSER_DISCOVERY_ENABLED=true OPENAI_API_KEY=… python -m backend.scripts.propose_parser sample*.txt --send
   ```
   - The request is refused while any sample still looks personal.
   - The model returns a **declarative** proposal: sender domains, a subject regex, field regexes and direction keywords. It never returns code.
   - The proposal is validated: regexes compile, each field needs a single `value` group, patterns are length-limited, and the status is **forced to `PENDING_HUMAN_REVIEW`** whatever the model says.
   - It is evaluated deterministically against the samples and written to `parser_proposals/`, which git ignores.
   - The request uses `store: false`.
4. **Human review.** The Owner or a developer reads the proposal and corrects it.
5. **Implement.** A developer writes a deterministic parser in `email_monitor/` with **synthetic** tests, following `test_parser_battery.py`, through a normal reviewed PR.
6. **Human approval.** The PR merge is the approval. Nothing is ever auto-activated: the app never loads proposal files.

### Configuration

| Variable | Where | Purpose |
|---|---|---|
| `PARSER_DISCOVERY_ENABLED=true` | local shell only | explicit opt-in before anything is sent |
| `OPENAI_API_KEY` | local shell / `backend/.env` (never committed) | the existing OpenAI project key; a separate restricted key is recommended |
| `PARSER_DISCOVERY_MODEL` | optional | defaults to `OPENAI_MODEL` (`gpt-5-mini`) |

No key is needed in Render for this flow.

### Not done (post-launch)

- A database-backed review queue.
- Automatically collecting unknown formats from `email_parser_logs` / `finva_parser_fallback_events`.

Both need a privacy review. Proposals would contain sanitized samples, and a queue would add a new place where user email content lives.
