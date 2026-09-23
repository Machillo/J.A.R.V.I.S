# DINCR product analytics

PostHog is the behavioral analytics layer for DINCR. Operational records remain
in PostgreSQL/Supabase and crash diagnostics remain in Firebase.

## Privacy contract

- Analytics starts only after the DINCR user has accepted the active legal documents.
- Owner, admin and J.A.R.V.I.S. sessions are excluded.
- Autocapture, session replay, console capture and pageview capture are disabled.
- Never send email addresses or bodies, names, subjects, senders, descriptions,
  amounts, balances, account/card identifiers, tokens or free-form text.
- Counts from Gmail sync are bucketed (`0`, `1`, `2_5`, `6_20`, `21_plus`).
- `bank` and `institution_country` are normalized categorical values only.

The runtime allowlist lives in `src/lib/productAnalytics.js`. A new event or
property must be added there deliberately before PostHog can receive it.

## Event catalog

| Event | Purpose | Safe properties |
| --- | --- | --- |
| `screen_viewed` | Product navigation and feature adoption | `screen`, `surface`, `plan`, `platform` |
| `app_resumed` | Returning use | `plan`, `platform` |
| `gmail_connection_started` | Gmail activation funnel | `plan`, `platform` |
| `gmail_sync_completed` | Sync activation and usefulness | `scan_scope`, `initial_scan_complete`, count buckets |
| `gmail_disconnected` | Gmail churn signal | `plan`, `platform` |
| `email_candidate_reviewed` | Trust and parser outcomes | `decision`, `bank`, `institution_country`, `source_type`, `is_internal_transfer` |
| `financial_account_ownership_reviewed` | Detected-account trust | `ownership_status`, `bank`, `institution_country` |
| `plan_access_granted` | Plan activation during free launch and later access changes | `plan`, `access_type` (`free` or `promotion`), `platform` |

## Dashboards

- **Producto y Retención:** activation, feature adoption, return usage and plan.
- **Gmail y Confianza:** connection, sync, accepted/corrected/rejected candidates.
- **Retención VIP:** VIP return usage and lifecycle feature adoption.
- **Mercado:** country, institution and platform signals from categorical events.

Saved insights are created only after a real deployment emits each event. This
prevents synthetic production data and dashboards that silently query nonexistent
events.

## Deployment

Set these frontend environment variables in the DINCR build environment and rebuild the APK/IPA:

```text
VITE_POSTHOG_KEY=<project token from PostHog>
VITE_POSTHOG_HOST=https://us.i.posthog.com
```

The project token is public by design but must still be managed as deployment
configuration so development, staging and production projects can remain separate.
Existing APKs compiled without `VITE_POSTHOG_KEY` cannot start sending events from
this code change alone; distribute a new build and verify real events in the
connected PostHog project. The event captures plan access, not payment or
financial contents. After store purchases are implemented, introduce a verified
`store` access type and compare cohorts by event time and plan in PostHog.
