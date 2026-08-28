# JARVIS Users — Clean Basic Baseline

This project intentionally contains only the SaaS surface needed for the first Basic version.

Kept: Supabase authentication, profiles/roles/subscriptions, finance overview, income, expenses, overtime, debts, deterministic Basic strategy, goals, transactions, and limited deterministic JARVIS chat.

Removed from Users because it belongs to JARVIS Personal: receivables/additional cards, BAC-specific logic and PDF/email importers, Gmail/email monitor, investments/IBKR, Wealth/business center, premium strategy, memory, sports, calendar/events, push notifications, web search, personal settings, personal reports/advisor experiments, owner-specific seeds, and unused AI/Gemini/OpenAI orchestration.

The backend never accepts `user_id` from client financial endpoints. Every financial query obtains the authenticated internal profile id from the request context and filters by it.

For the already-created development database, execute `database/migrations/002_cleanup_to_basic.sql` once. It preserves `profiles`, `plans`, `features`, `plan_features`, and `subscriptions`, but intentionally deletes old copied financial/personal module tables before recreating the small Basic finance surface.

For a brand-new Users database, execute only `database/schema.sql`.
