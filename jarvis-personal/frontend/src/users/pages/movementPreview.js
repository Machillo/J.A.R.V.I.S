// The full-history endpoint owns the aggregation and workspace filtering.
// This only adapts its rows to the filters used by the Movimientos screen.
export function movementPreview(rows, query = "", filter = "all") {
  const term = query.trim().toLowerCase();
  return rows.map((row) => ({
    ...row,
    kind: row.transaction_type === "income" ? "income"
      : /deud|debt|pr[eé]stamo|loan|cuota/i.test(`${row.category || ""} ${row.description || ""}`) ? "debt" : "expense",
  })).filter((row) => (filter === "all" || row.kind === filter)
    && `${row.description || ""} ${row.category || ""}`.toLowerCase().includes(term))
    .sort((a, b) => String(b.transaction_date || "").localeCompare(String(a.transaction_date || "")));
}
