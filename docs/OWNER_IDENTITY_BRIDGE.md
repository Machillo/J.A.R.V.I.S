# JARVIS Owner Identity Bridge

## Goal

The public JARVIS app authenticates against **JARVIS Users Supabase**. Kenneth's public-app owner account can use multiple auth methods (Google, Apple, passkey) while remaining the same JARVIS Users identity. A verified server-side link maps that owner identity to Kenneth's existing **JARVIS Personal Supabase** identity.

The email address is display/contact data only; it is not the bridge security boundary.

## Security model

1. Supabase Users owns public authentication.
2. OAuth identities must be linked to the existing Users account from an already authenticated session (`linkIdentity`).
3. Passkeys are registered to the existing confirmed Supabase Users user.
4. `profiles.account_id` is JARVIS's stable application-level identity.
5. `owner_personal_links` stores the explicit Users owner -> Personal Supabase UUID mapping.
6. Users verifies a proposed Personal UUID against the Personal backend over a separate `JARVIS_OWNER_BRIDGE_API_KEY`.
7. Personal accepts the bridge only when its own DB says that exact Personal Supabase UUID is an active owner.
8. Neither browser nor mobile app receives Personal DB credentials.

## Required one-time configuration

### JARVIS Users Supabase

Run `jarvis-users/database/migrations/006_owner_identity_bridge.sql`.

In Authentication settings:
- Enable Manual Identity Linking before using **Vincular Apple**.
- Configure the Apple provider before Apple OAuth can work.
- Enable Passkeys and configure a stable WebAuthn RP ID + allowed origins before passkey registration/sign-in can work.

Do not pick a temporary production RP ID. Changing it later invalidates previously enrolled passkeys.

### Backend environment

Generate a new long random value for `JARVIS_OWNER_BRIDGE_API_KEY` and put the **same value** in:
- `jarvis-personal/backend/.env`
- `jarvis-users/backend/.env`

Also configure:
- Users: `JARVIS_PERSONAL_API_URL=http://127.0.0.1:8000` in local development.
- Personal: existing `JARVIS_USERS_API_URL=http://127.0.0.1:8001` and `JARVIS_ADMIN_API_KEY` remain unchanged.

Never expose either shared server key in a frontend `VITE_*` variable.

## Create the owner link

1. Start Personal backend on 8000 and Users backend on 8001.
2. Log into JARVIS Personal once with the original Personal account. This ensures `allowed_users.supabase_user_id` contains the real Personal Supabase UUID.
3. Log into JARVIS Users with the intended public owner Google account and confirm `/auth/me` returns `role=owner`.
4. While authenticated as Personal owner, call:
   `POST http://127.0.0.1:8000/users-admin/owner-link`
   with the normal Personal bearer token.
5. Personal sends its verified Personal UUID to Users through the protected Admin API. Users calls back to Personal through the owner-bridge verifier and stores the mapping only after verification.
6. Refresh JARVIS Users. `/auth/me.personal_bridge.linked` should be `true`.

## Apple and passkey enrollment

Always enroll additional methods while signed into the existing Users account from **Más -> Mi JARVIS -> Formas de entrar**.

- **Apple:** `linkIdentity({ provider: 'apple' })` attaches Apple to the current Supabase Users user. This avoids creating a second JARVIS account even if Apple uses Hide My Email.
- **Passkey:** `registerPasskey()` attaches a WebAuthn credential to the current Supabase Users user. On an iPhone this can be unlocked with Face ID; JARVIS never receives facial biometric data.

After a passkey exists, the login page can use `signInWithPasskey()` without asking for an email first.
