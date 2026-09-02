BEGIN;

-- Kenneth already reviewed these two personal patterns. Future matches remain
-- constrained by each rule's exact direction, accounts and concept.
UPDATE email_classification_rules
SET allow_auto_commit = TRUE,
    updated_at = NOW()
WHERE active = TRUE
  AND action = 'classify'
  AND LOWER(TRIM(output_description)) IN (
      'lavado y doblado de ropa',
      'abono de sidey por celular'
  );

COMMIT;
