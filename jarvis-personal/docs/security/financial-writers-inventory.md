# Financial writers inventory

Every code path that inserts, updates or deletes a financial table, grouped by table and by surface. It is generated from the backend source with an AST scan of SQL string literals in non-test modules.

**Surfaces**
- **Users:** `user_product/`, `auth/`.
- **Owner:** internal modules behind `INTERNAL_ONLY` or an owner/admin role check.
- **Script:** operator scripts in `backend/scripts/`.

Regenerate this file whenever a writer is added. Any Users writer must satisfy `CLAUDE.md` §4 (tenancy, reads never write) and the DINCR Data Integrity checklist.

## Findings (at generation time)

1. **Users writers are commands.**
   - Every financial write inside `user_product/` and `auth/` sits in a command function (create/update/delete/confirm/discover), not in a read function. This was checked by function name only.
   - Reads can still write through shared modules. The VIP lifecycle read reaches the snapshot write in finding 5.
   - `tests/test_read_surfaces_are_read_only.py` is the executable guard for the main read surfaces.
2. **Scoping:**
   - Every application DELETE of a financial table is scoped by `workspace_id`.
   - No DELETE selects rows by a legacy `user_id`.
   - The only unscoped financial deletes are in the isolation-check scripts, which delete their own sentinel rows by primary key.
3. **Account deletion cascades through the legacy identity.**
   - It deletes the legacy `users` row by email, and `users`-referencing financial tables are `ON DELETE CASCADE`.
   - The cascade reaches every row whose `user_id` equals that id. That includes rows in other workspaces that carry the same integer from the other identity space.
   - Guarding this is part of the financial ownership integrity work (identity delete guard). Until that lands, the risk is structural.
4. **Owner automation writes from reads:**
   - `finance.service._sync_automatic_debt_payments` rewrites every Owner debt row on each read, even when nothing changed.
   - It is documented and Owner-only (`finance/debt_automation.py`), but it inflates write volume and makes `updated_at` meaningless.
   - Recommended: skip the UPDATE when the values are unchanged.
5. **Snapshot writes from reads:** `finance.deterioration` and `finance.service._save_net_worth_snapshot` persist derived snapshots during reads. These are derived tables, not financial truth, but they are writes on a read path.

## Writers by table

| Table | Users | Owner | Script |
|---|---|---|---|
| `account_balance_history` | — | `finance/intelligence.upsert_account_balance` INSERT<br>`finance/reconciliation.confirm_account_reconciliation` INSERT | — |
| `account_balances` | `user_product/financial_identity.confirm_financial_account` UPDATE<br>`user_product/financial_identity.discover_candidate_account` INSERT | `finance/intelligence.deactivate_account_balance` UPDATE<br>`finance/intelligence.upsert_account_balance` INSERT<br>`finance/intelligence.upsert_account_balance` UPDATE<br>`finance/reconciliation.confirm_account_reconciliation` UPDATE | — |
| `bonuses` | — | `finance/service.add_bonus` INSERT | — |
| `business_movements` | — | `finance/business_center.add_business_movement` INSERT | — |
| `credit_card_settings` | — | `finance/card_cycle.set_credit_card_settings` DELETE<br>`finance/card_cycle.set_credit_card_settings` INSERT | — |
| `debt_payments` | — | `finance/service._sync_automatic_debt_payments` INSERT<br>`finance/service.apply_extra_payment_to_debt` INSERT<br>`finance/service.apply_monthly_payment_to_debt` INSERT<br>`finance/service.delete_debt` DELETE | `scripts/finva_personal_isolation_check.main` DELETE |
| `debts` | `user_product/service.create_user_debt` INSERT<br>`user_product/service.delete_user_debt` DELETE<br>`user_product/service.pay_user_debt` UPDATE<br>`user_product/service.update_user_debt` UPDATE | `finance/service._sync_automatic_debt_payments` UPDATE<br>`finance/service.add_debt` INSERT<br>`finance/service.apply_extra_payment_to_debt` UPDATE<br>`finance/service.apply_monthly_payment_to_debt` UPDATE<br>`finance/service.delete_debt` DELETE<br>`finance/service.update_debt` UPDATE | `scripts/finva_personal_isolation_check.create_sentinels` INSERT<br>`scripts/finva_personal_isolation_check.main` DELETE |
| `email_transaction_candidates` | — | `email_monitor/service._delete_pending_internal_mirrors` DELETE<br>`email_monitor/service._repair_historical_cross_bank_mirrors` DELETE<br>`email_monitor/service._repair_historical_scheduled_commitments` UPDATE<br>`email_monitor/service._repair_orphan_duplicate_links` UPDATE<br>`email_monitor/service.bulk_decide_candidates` UPDATE<br>`email_monitor/service.classify_candidate` UPDATE<br>`email_monitor/service.decide_candidate` UPDATE<br>`email_monitor/service.scan_email_text` DELETE<br>`email_monitor/service.scan_email_text` INSERT<br>`email_monitor/service.scan_email_text` UPDATE | — |
| `exchange_rates` | — | `transactions/service._save_exchange_rate` INSERT | — |
| `expenses` | `user_product/free_service.update_free_movement` UPDATE<br>`user_product/service.create_expense_entry` INSERT<br>`user_product/service.delete_expense` DELETE<br>`user_product/service.update_expense` UPDATE | `finance/service.add_expense` INSERT<br>`finance/service.delete_expense` DELETE<br>`finance/service.update_expense` UPDATE | — |
| `financial_goals` | `user_product/service.contribute_user_goal` UPDATE<br>`user_product/service.create_user_goal` INSERT<br>`user_product/service.delete_user_goal` DELETE<br>`user_product/service.update_user_goal` UPDATE | `goals/service.add_financial_goal` INSERT<br>`goals/service.add_financial_goal` UPDATE<br>`goals/service.add_goal_contribution` UPDATE<br>`goals/service.delete_financial_goal` DELETE<br>`goals/service.update_financial_goal` UPDATE | `scripts/finva_personal_isolation_check.create_sentinels` INSERT<br>`scripts/finva_personal_isolation_check.main` DELETE |
| `financial_input_events` | `user_product/gmail_service._publish_confirmed_financial_input` INSERT<br>`user_product/own_transfer_review.confirm_own_transfer` UPDATE | — | — |
| `financial_profiles` | `auth/saas.complete_onboarding` INSERT<br>`user_product/service.update_financial_situation` INSERT | — | — |
| `finva_budget_items` | `user_product/basic_service.save_guided_budget` DELETE<br>`user_product/basic_service.save_guided_budget` INSERT | — | — |
| `finva_email_candidates` | `user_product/candidate_resolution.release_cross_source_duplicates` UPDATE<br>`user_product/candidate_resolution.resolve_candidate` UPDATE<br>`user_product/financial_identity.confirm_financial_account` UPDATE<br>`user_product/financial_identity.discover_candidate_account` UPDATE<br>`user_product/gmail_retention.apply_gmail_retention` UPDATE<br>`user_product/gmail_service._insert_finva_candidate` INSERT<br>`user_product/gmail_service.review_gmail_candidate` UPDATE<br>`user_product/legacy_owner_mail.mark_legacy_duplicate` UPDATE<br>`user_product/own_transfer_review.confirm_own_transfer` UPDATE | — | — |
| `finva_goal_contributions` | `user_product/service.contribute_user_goal` INSERT | — | — |
| `finva_recurring_items` | `user_product/basic_service.create_recurring_item` INSERT<br>`user_product/basic_service.delete_recurring_item` DELETE<br>`user_product/basic_service.update_recurring_item` UPDATE | — | — |
| `finva_savings_plan_contributions` | `user_product/service.contribute_savings_plan` INSERT | — | — |
| `finva_savings_plans` | `user_product/service.contribute_savings_plan` UPDATE<br>`user_product/service.create_savings_plan` INSERT<br>`user_product/service.delete_savings_plan` DELETE<br>`user_product/service.update_savings_plan` UPDATE | — | — |
| `fixed_expenses` | — | `finance/fixed_expenses.create_fixed_expense` INSERT<br>`finance/fixed_expenses.create_fixed_expense` UPDATE<br>`finance/fixed_expenses.update_fixed_expense` UPDATE | — |
| `investment_cashflows` | — | `finance/investment_center.add_cashflow` INSERT | — |
| `investments` | — | `finance/service.add_investment` INSERT<br>`finance/service.delete_investment` DELETE<br>`finance/service.update_investment` UPDATE | — |
| `net_worth_snapshots` | — | `finance/service._save_net_worth_snapshot` INSERT | — |
| `payroll_deductions` | — | `finance/service.add_payroll_deduction` INSERT | — |
| `payroll_events` | `user_product/free_service.update_free_movement` UPDATE<br>`user_product/service.create_overtime` INSERT | `finance/service.add_payroll_event` INSERT | — |
| `payroll_salary_reports` | `auth/service.delete_current_account` DELETE<br>`user_product/gmail_service._ingest_message` INSERT<br>`user_product/payroll_income.link_received_payroll` UPDATE | `email_monitor/service.scan_email_text` INSERT | — |
| `receivable_entries` | — | `finance/intelligence._backfill_receivable_entries` INSERT<br>`finance/intelligence._sync_auto_additional_card_receivables` INSERT<br>`finance/intelligence._sync_receivable_payments_from_income` INSERT<br>`finance/intelligence.add_receivable_entry` INSERT<br>`finance/intelligence.apply_receivable_payment` INSERT<br>`finance/intelligence.update_receivable_entry` UPDATE | — |
| `receivable_payments` | — | `email_monitor/service._auto_apply_receivable_payment_from_candidate` INSERT<br>`finance/intelligence._sync_receivable_payments_from_income` INSERT<br>`finance/intelligence.apply_receivable_payment` INSERT<br>`finance/intelligence.update_receivable_entry` UPDATE | — |
| `receivables` | — | `email_monitor/service._auto_apply_receivable_payment_from_candidate` UPDATE<br>`finance/intelligence._get_or_create_person_receivable` INSERT<br>`finance/intelligence._recalculate_receivable` UPDATE<br>`finance/intelligence._sync_auto_additional_card_receivables` UPDATE | — |
| `salaries` | `user_product/free_service.update_free_movement` UPDATE<br>`user_product/service.create_income` INSERT<br>`user_product/service.delete_income` DELETE<br>`user_product/service.update_income` UPDATE | `finance/service.add_salary` INSERT | — |
| `savings` | — | `finance/service.add_saving` INSERT<br>`finance/service.delete_saving` DELETE<br>`finance/service.update_saving` UPDATE | — |
| `transactions` | `user_product/free_service.delete_free_movement` DELETE<br>`user_product/free_service.update_free_movement` UPDATE<br>`user_product/gmail_service._create_candidate_transaction` INSERT<br>`user_product/own_transfer_review.confirm_own_transfer` UPDATE<br>`user_product/service.create_user_transaction` INSERT<br>`user_product/service.delete_user_transaction` DELETE<br>`user_product/service.pay_user_debt` INSERT | `email_monitor/service._insert_transaction` INSERT<br>`email_monitor/statement_reconciliation._import_missing_statement_movement` INSERT<br>`finance/business_center.add_business_movement` INSERT<br>`finance/intelligence.apply_receivable_payment` INSERT<br>`finance/intelligence.update_receivable_entry` UPDATE<br>`finance/intelligence.upsert_account_balance` UPDATE<br>`finance/service._sync_automatic_debt_payments` INSERT<br>`finance/service.apply_extra_payment_to_debt` INSERT<br>`finance/service.apply_monthly_payment_to_debt` INSERT<br>`transactions/service._reuse_saved_rates` UPDATE<br>`transactions/service.apply_currency_rate` UPDATE<br>`transactions/service.create_transaction` INSERT<br>`transactions/service.delete_transaction` DELETE<br>`transactions/service.update_transaction` UPDATE | `scripts/workspace_isolation_check.main` DELETE |
