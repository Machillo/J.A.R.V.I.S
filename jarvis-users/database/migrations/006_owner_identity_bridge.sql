-- JARVIS Users: stable account identity + secure owner -> Personal bridge.
-- Run once in the JARVIS Users Supabase SQL Editor.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS account_id UUID;

UPDATE profiles
SET account_id = gen_random_uuid()
WHERE account_id IS NULL;

ALTER TABLE profiles
    ALTER COLUMN account_id SET DEFAULT gen_random_uuid();

ALTER TABLE profiles
    ALTER COLUMN account_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_account_id
    ON profiles(account_id);

CREATE TABLE IF NOT EXISTS owner_personal_links (
    id BIGSERIAL PRIMARY KEY,
    users_profile_id BIGINT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    personal_supabase_user_id UUID NOT NULL UNIQUE,
    personal_allowed_user_id BIGINT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_owner_personal_links_personal_uid
    ON owner_personal_links(personal_supabase_user_id);
