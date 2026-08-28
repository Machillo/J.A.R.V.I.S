# SaaS identity foundation

This phase changes only JARVIS Users.

## Identity model

- Supabase Auth UUID is the external authenticated identity.
- `profiles.id` remains a BIGINT internal tenant key so the existing financial core does not need a risky mass refactor.
- The backend derives the profile from the verified Supabase bearer token. The frontend never supplies `user_id`.
- New authenticated users are auto-provisioned into `profiles` and receive a `basic` subscription in `pending` status.
- Owner assignment uses `OWNER_SUPABASE_USER_IDS`; there is no owner-email fallback.

## Subscription status in this phase

Subscriptions are stored but are NOT yet an access gate. The enforcement middleware belongs to the subscription phase.

## Security invariant added now

`user_id DEFAULT 1` is removed from the Users schema. Missing tenant ownership must fail instead of silently writing data under user 1.

## Not implemented yet

- onboarding flow/UI
- subscription access gate and expiry scheduler
- Admin subscription actions
- RLS policies
- Basic feature pruning
- Strategy Basic extraction
