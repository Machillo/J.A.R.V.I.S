-- Optional cleanup for legacy rows with blank event_date.
-- Run this only if you want to remove empty-date events from the calendar table.
DELETE FROM events
WHERE event_date IS NULL
   OR TRIM(event_date::text) = '';

-- Inspect remaining invalid dates:
SELECT id, title, event_date
FROM events
WHERE event_date IS NOT NULL
  AND TRIM(event_date::text) <> ''
  AND TRIM(event_date::text) !~ '^\d{4}-\d{2}-\d{2}';
