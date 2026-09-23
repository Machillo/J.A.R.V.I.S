import { API_URL } from "../../lib/apiUrl";
import { apiError, apiNetworkError } from "../../lib/apiErrors";
import { flushIncidentQueue } from "../../lib/incidentReporter";
import { flushPendingOperations, recoverableFetch } from "../../lib/operationRecovery";

const OBSERVABILITY_PATHS = new Set([
  "/product-ops/incidents",
  "/product-ops/events",
  "/product-ops/health",
]);

async function request(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const autoReport = !OBSERVABILITY_PATHS.has(path);
  let response;
  try {
    response = await recoverableFetch(`${API_URL}${path}`, options);
  } catch (cause) {
    throw apiNetworkError(cause, path, method, autoReport);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(response, payload, path, method, autoReport);
  if (path !== "/product-ops/incidents") flushIncidentQueue();
  if (path !== "/product-ops/incidents") flushPendingOperations();
  if (!OBSERVABILITY_PATHS.has(path)) {
    window.dispatchEvent(new CustomEvent("dincr:api-recovered"));
  }
  return payload;
}

function json(path, method, body) {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getMe = () => request("/auth/me");
export const deleteMyAccount = () => request("/auth/me", { method: "DELETE" });
export const exportMyData = () => request("/auth/me/export");
export const getPlans = () => request("/auth/plans");
export const selectPlan = (plan, accept_beta_terms = false) => json("/auth/plan", "POST", { plan, accept_beta_terms, consent_version: "regular-2027-v1" });
export const getBillingCatalog = () => request("/product-ops/billing/catalog");
export const getStoreBillingCatalog = () => request("/product-ops/billing/store/catalog");
export const getStoreEntitlement = () => request("/product-ops/billing/store/entitlement");
export const uploadPaymentReceipt = (orderId, file) => {
  const body = new FormData();
  body.append("receipt", file);
  return request(`/product-ops/billing/orders/${orderId}/receipt`, { method: "POST", body });
};
export const trackProductEvent = (payload) => json("/product-ops/events", "POST", payload);
export const getFeedback = () => request("/product-ops/feedback");
export const createFeedback = (payload) => json("/product-ops/feedback", "POST", payload);
export const updateFeedbackResolution = (id, resolution) => json(`/product-ops/feedback/${id}/resolution`, "PATCH", { resolution });
export const getPlatformHealth = () => request("/product-ops/health");

export const getFinancialSituation = () => request("/user-product/financial-situation");
export const updateFinancialSituation = (payload) => json("/user-product/financial-situation", "PUT", payload);

export const getFinanceSummary = () => request("/user-product/finance/summary");
export const getIncome = () => request("/user-product/finance/income");
export const createIncome = (payload) => json("/user-product/finance/income", "POST", payload);
export const updateIncome = (id, payload) => json(`/user-product/finance/income/${id}`, "PUT", payload);
export const deleteIncome = (id) => request(`/user-product/finance/income/${id}`, { method: "DELETE" });
export const getExpenses = () => request("/user-product/finance/expenses");
export const createExpense = (payload) => json("/user-product/finance/expenses", "POST", payload);
export const updateExpense = (id, payload) => json(`/user-product/finance/expenses/${id}`, "PUT", payload);
export const deleteExpense = (id) => request(`/user-product/finance/expenses/${id}`, { method: "DELETE" });

export const getDebts = () => request("/user-product/finance/debts");
export const createDebt = (payload) => json("/user-product/finance/debts", "POST", payload);
export const updateDebt = (id, payload) => json(`/user-product/finance/debts/${id}`, "PUT", payload);
export const deleteDebt = (id) => request(`/user-product/finance/debts/${id}`, { method: "DELETE" });
export const payDebt = (id, payload) => json(`/user-product/finance/debts/${id}/payments`, "POST", payload);

export const getStrategyBasic = () => request("/user-product/finance/strategy-basic");
export const simulateStrategyBasic = (extra_monthly) => json("/user-product/finance/strategy-basic/simulate", "POST", { extra_monthly });
export const getStrategyVip = () => request("/user-product/finance/strategy-vip");
export const simulateStrategyVip = (payload) => json("/user-product/finance/strategy-vip/simulate", "POST", payload);
export const getVipCommandCenter = () => request("/user-product/vip/command-center");
export const captureVipLifecycleSnapshot = () => request("/user-product/vip/lifecycle/snapshots", { method: "POST" });
export const getVipMonthlyReview = (period = "") => request(`/user-product/vip/lifecycle/monthly-review${period ? `?period=${encodeURIComponent(period)}` : ""}`);
export const getVipProactiveAdvisor = () => request("/user-product/vip/lifecycle/proactive-advisor");
export const getVipStrategyDashboard = () => request("/user-product/vip/strategy-dashboard");
export const getVipDebtAdvisory = (extraCash = null) => request(`/user-product/vip/debt-advisory${extraCash == null ? "" : `?extra_cash=${encodeURIComponent(extraCash)}`}`);
export const getVipDebtStrategies = () => request("/user-product/vip/debt-strategies");
export const getVipSalvavidas = () => request("/user-product/vip/salvavidas");
export const updateVipSalvavidas = (payload) => json("/user-product/vip/salvavidas", "PUT", payload);
export const getVipAguinaldo = () => request("/user-product/vip/aguinaldo");
export const getVipGmailStatus = () => request("/user-product/vip/gmail/status");
export const connectVipGmail = () => request("/user-product/vip/gmail/connect", { method: "POST" });
export const connectVipMicrosoftMail = () => request("/user-product/vip/mail/microsoft/connect", { method: "POST" });
export const acceptVipGmailConsent = (version) => json("/user-product/vip/gmail/consent", "POST", { accepted: true, version });
export const syncVipGmail = () => request("/user-product/vip/gmail/sync", { method: "POST" });
export const disconnectVipGmail = (connectionId) => request(`/user-product/vip/gmail?connection_id=${encodeURIComponent(connectionId)}`, { method: "DELETE" });
export const getVipGmailEmails = (status = "") => request(`/user-product/vip/gmail/emails${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const getVipOwnTransferSuggestions = () => request("/user-product/vip/gmail/own-transfer-suggestions");
export const confirmVipOwnTransfer = (id, counterpartId, unknownDirection = null) => json(
  `/user-product/vip/gmail/candidates/${id}/own-transfer`, "POST",
  { counterpart_id: counterpartId, confirm_owned_accounts: true, unknown_direction: unknownDirection },
);
export const acceptVipGmailCandidate = (id, corrections = null) => corrections
  ? json(`/user-product/vip/gmail/candidates/${id}/accept`, "PUT", corrections)
  : request(`/user-product/vip/gmail/candidates/${id}/accept`, { method: "POST" });
export const rejectVipGmailCandidate = (id) => request(`/user-product/vip/gmail/candidates/${id}/reject`, { method: "POST" });
export const getVipFinancialIdentity = () => request("/user-product/vip/financial-identity");
export const confirmVipFinancialAccount = (id, ownershipStatus, displayName = "") => json(
  `/user-product/vip/financial-identity/accounts/${id}`,
  "PUT",
  { ownership_status: ownershipStatus, display_name: displayName || null },
);

export const getGoals = () => request("/user-product/goals");
export const createGoal = (payload) => json("/user-product/goals", "POST", payload);
export const updateGoal = (id, payload) => json(`/user-product/goals/${id}`, "PUT", payload);
export const contributeGoal = (id, payload) => json(`/user-product/goals/${id}/contributions`, "POST", payload);
export const deleteGoal = (id) => request(`/user-product/goals/${id}`, { method: "DELETE" });
export const getSavingsPlans = () => request("/user-product/savings-plans");
export const createSavingsPlan = (payload) => json("/user-product/savings-plans", "POST", payload);
export const updateSavingsPlan = (id, payload) => json(`/user-product/savings-plans/${id}`, "PUT", payload);
export const contributeSavingsPlan = (id, payload) => json(`/user-product/savings-plans/${id}/contributions`, "POST", payload);
export const deleteSavingsPlan = (id) => request(`/user-product/savings-plans/${id}`, { method: "DELETE" });

export const getTransactions = () => request("/user-product/transactions");
export const createTransaction = (payload) => json("/user-product/transactions", "POST", payload);
export const deleteTransaction = (id) => request(`/user-product/transactions/${id}`, { method: "DELETE" });

export const getBasicDashboard = () => request("/user-product/basic/dashboard");
export const getBudget = () => request("/user-product/basic/budget");
export const saveBudget = (payload) => json("/user-product/basic/budget", "PUT", payload);
export const getFinancialCalendar = (period) => request(`/user-product/basic/calendar${period ? `?period=${period}` : ""}`);
export const getRecurring = () => request("/user-product/basic/recurring");
export const createRecurring = (payload) => json("/user-product/basic/recurring", "POST", payload);
export const updateRecurring = (id, payload) => json(`/user-product/basic/recurring/${id}`, "PUT", payload);
export const deleteRecurring = (id) => request(`/user-product/basic/recurring/${id}`, { method: "DELETE" });
export const getBasicReport = (period) => request(`/user-product/basic/reports${period ? `?period=${period}` : ""}`);
export const getFreeDashboard = () => request("/user-product/free/dashboard");
export const getFreeMonthlySummary = (period) => request(`/user-product/free/monthly-summary${period ? `?period=${period}` : ""}`);
export const getFreeMovements = () => request("/user-product/free/movements");
export const updateFreeMovement = (id, payload) => json(`/user-product/free/movements/${encodeURIComponent(id)}`, "PUT", payload);
export const deleteFreeMovement = (id) => request(`/user-product/free/movements/${encodeURIComponent(id)}`, { method: "DELETE" });
