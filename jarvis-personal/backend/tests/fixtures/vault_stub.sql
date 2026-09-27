-- Synthetic stand-in for Supabase Vault in PostgreSQL tests: the same objects the
-- application touches (vault.secrets, vault.decrypted_secrets, vault.create_secret)
-- with the same shape, no encryption. Test databases only.
CREATE SCHEMA IF NOT EXISTS vault;
CREATE TABLE IF NOT EXISTS vault.secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    description TEXT NOT NULL DEFAULT '',
    secret TEXT NOT NULL
);
CREATE OR REPLACE VIEW vault.decrypted_secrets AS
    SELECT id, name, description, secret, secret AS decrypted_secret FROM vault.secrets;
CREATE OR REPLACE FUNCTION vault.create_secret(new_secret TEXT, new_name TEXT DEFAULT NULL, new_description TEXT DEFAULT '')
RETURNS UUID LANGUAGE sql AS $$
    INSERT INTO vault.secrets(secret, name, description) VALUES (new_secret, new_name, new_description) RETURNING id
$$;
REVOKE ALL ON SCHEMA vault FROM PUBLIC;
