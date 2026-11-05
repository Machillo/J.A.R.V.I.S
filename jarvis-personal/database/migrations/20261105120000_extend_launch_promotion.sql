-- The launch promotion now ends on March 31, 2027 (Costa Rica). Accounts that already activated it
-- keep their courtesy until the new date. Only rows still on the old end date change, so it can run twice.
UPDATE account_subscriptions
SET expires_at = '2027-04-01 06:00:00+00', updated_at = NOW()
WHERE courtesy_note = 'launch-free-2026'
  AND access_source = 'courtesy'
  AND status = 'active'
  AND expires_at = '2027-01-01 06:00:00+00';
