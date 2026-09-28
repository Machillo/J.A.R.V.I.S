// App Store / Google Play subscriptions: the device side.
//
// The DINCR backend is the only authority on plans. The device never grants a plan:
// it asks the backend for the account's store customer token, buys through the store
// with that token (Apple appAccountToken / Play obfuscated account id), hands the
// store's evidence (Apple's signed JWS / the Play purchase token) to the backend, which
// verifies it with Apple or Google, and then reads the plan back from the backend.
//
// Who finishes what:
// - Google Play: only the backend acknowledges a purchase, after verifying it. An
//   unverified purchase is left unacknowledged, so Google refunds it after 3 days
//   instead of charging for a plan DINCR never granted. The device never
//   acknowledges: every call passes autoAcknowledgePurchases:false, and the plugin's
//   restorePurchases (which acknowledges everything) is never called on Android.
// - App Store: the device finishes a transaction only after the backend gave a
//   definitive answer (verified, refused or bound to another account). A transaction
//   left unfinished (backend down, kill switch off) is still in StoreKit's current
//   entitlements, so reconcile() sends it again later.
//
// Evidence (JWS, purchase tokens) is sent to the backend and never logged, stored or
// sent to analytics.

export const STORE_PLANS = ["basic", "vip"];
export const STORE_PERIODS = ["monthly", "annual"];
const SUBSCRIPTIONS = "subs";
const JWS = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const ANDROID_PURCHASED = "1";

export class StoreBillingError extends Error {
  constructor(kind, cause) {
    super(kind);
    this.name = "StoreBillingError";
    this.kind = kind;
    if (cause) this.cause = cause;
  }
}

/** "ios" / "android" in the native app, null on the web (no store billing there). */
export function storePlatform(capacitor) {
  if (!capacitor?.isNativePlatform?.()) return null;
  const platform = capacitor.getPlatform?.();
  return platform === "ios" || platform === "android" ? platform : null;
}

/** DINCR's store products, from the backend catalog: [{ plan, period, productId }]. */
export function catalogProducts(catalog) {
  const products = [];
  for (const entry of catalog?.plans || []) {
    if (!STORE_PLANS.includes(entry?.code)) continue;
    for (const period of STORE_PERIODS) {
      const productId = entry?.[period]?.product_id;
      if (typeof productId === "string" && productId.trim()) {
        products.push({ plan: entry.code, period, productId: productId.trim() });
      }
    }
  }
  return products;
}

/**
 * A store product as { productId, basePlanId, offerId, ... }. The plugin reports
 * Android subscriptions per offer: `planIdentifier` is the Play product id and
 * `identifier` the base plan id. On iOS `identifier` is the product id.
 */
export function storeProduct(platform, item) {
  if (platform === "android") {
    return { ...item, productId: item?.planIdentifier, basePlanId: item?.identifier, offerId: item?.offerId || null };
  }
  return { ...item, productId: item?.identifier, basePlanId: undefined, offerId: null };
}

/**
 * The offers to show: DINCR's catalog products that the store also returned, with
 * the store's own localized price. A store product outside the catalog is ignored;
 * a catalog product the store does not return is not offered. No backend price.
 */
export function matchOffers(products, storeProducts, platform = "ios") {
  const offers = [];
  const items = (storeProducts || []).map((item) => storeProduct(platform, item));
  for (const product of products) {
    const candidates = items.filter((item) => item.productId === product.productId);
    // Google: one entry per offer. The base plan itself (no offer id) carries the
    // regular price; a base plan named after the period is preferred.
    const base = candidates.filter((item) => !item.offerId);
    const match = base.find((item) => item.basePlanId === product.period) || base[0] || candidates[0];
    if (!match || typeof match.priceString !== "string" || !match.priceString) continue;
    offers.push({
      ...product,
      basePlanId: match.basePlanId || undefined,
      priceString: match.priceString,
      currencyCode: match.currencyCode || "",
      title: match.title || "",
    });
  }
  return offers;
}

/**
 * The verification request for a store transaction, or a StoreBillingError:
 * "pending" (Google, payment not completed), "unknown_product", "malformed".
 */
export function purchaseEvidence(platform, transaction, productIds) {
  const productId = transaction?.productIdentifier;
  if (typeof productId !== "string" || !productIds.has(productId)) throw new StoreBillingError("unknown_product");
  if (platform === "ios") {
    const jws = transaction.jwsRepresentation;
    const transactionId = String(transaction.transactionId ?? "");
    if (typeof jws !== "string" || jws.length < 20 || jws.length > 20000 || !JWS.test(jws) || !/^\d+$/.test(transactionId)) {
      throw new StoreBillingError("malformed");
    }
    return { provider: "apple", productId, body: { signed_transaction: jws }, finishId: transactionId };
  }
  if (platform === "android") {
    if (transaction.purchaseState !== undefined && String(transaction.purchaseState) !== ANDROID_PURCHASED) {
      throw new StoreBillingError("pending");
    }
    const token = transaction.purchaseToken;
    if (typeof token !== "string" || token.length < 10 || token.length > 4096) throw new StoreBillingError("malformed");
    return { provider: "google", productId, body: { purchase_token: token, product_id: productId }, finishId: null };
  }
  throw new StoreBillingError("unavailable");
}

/** What a rejected store call means: "cancelled", "pending", "unavailable" or "store". */
export function storeFailure(error) {
  const text = `${error?.code || ""} ${error?.message || ""}`.toLowerCase();
  if (/user_?cancel|cancelled|canceled/.test(text)) return "cancelled";
  if (/pending/.test(text)) return "pending";
  if (/billing_unavailable|service_unavailable|service_disconnected|feature_not_supported|not found|cannot find product|item_unavailable|not available/.test(text)) {
    return "unavailable";
  }
  return "store";
}

/**
 * What a failed backend call means: "disabled" (503: store verification is off or the
 * service is down), "conflict" (409: the purchase belongs to another DINCR account),
 * "rejected" (422: the store did not confirm it), "network", "session" or "backend".
 */
export function backendFailure(error) {
  const status = Number(error?.status ?? -1);
  if (status === 503) return "disabled";
  if (status === 409) return "conflict";
  if (status === 422) return "rejected";
  if (status === 401) return "session";
  if (status === 0) return "network";
  return "backend";
}

/** A store subscription the backend reports as live (never the Owner simulator's rows). */
export function liveStoreSubscription(entitlement) {
  return ["apple", "google"].includes(entitlement?.provider) && STORE_PLANS.includes(entitlement?.entitlement)
    ? entitlement : null;
}

/**
 * The store billing service. `plugin` is the native purchases plugin; `api` the DINCR
 * backend: { customerToken, storeCatalog, verifyApple, verifyGoogle, entitlement, profile }.
 */
export function createStoreBilling({ platform, plugin, api }) {
  let busy = false;
  let productIds = new Set();
  // Evidence already answered by the backend during this app session (memory only).
  const answered = new Set();

  const exclusive = async (work) => {
    if (busy) return { outcome: "busy", results: [] };
    busy = true;
    try {
      return await work();
    } finally {
      busy = false;
    }
  };

  // Before any purchase: also the kill-switch check (503 -> nothing is bought).
  const customerToken = async () => {
    let response;
    try {
      response = await api.customerToken();
    } catch (error) {
      throw new StoreBillingError(backendFailure(error), error);
    }
    const token = String(response?.token || "").toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(token)) {
      throw new StoreBillingError("backend");
    }
    return token;
  };

  const knownProducts = async () => {
    const products = catalogProducts(await api.storeCatalog());
    productIds = new Set(products.map((product) => product.productId));
    return products;
  };

  const finishApple = async (evidence) => {
    if (platform !== "ios" || !evidence?.finishId) return;
    // Already finished by StoreKit's update listener is fine: nothing left to do.
    await plugin.acknowledgePurchase({ purchaseToken: evidence.finishId }).catch(() => {});
  };

  const refresh = async () => {
    const [entitlement, profile] = await Promise.all([
      api.entitlement().catch(() => null),
      api.profile().catch(() => null),
    ]);
    return { entitlement, profile };
  };

  // Send one store transaction to the backend and report what the backend decided.
  // A purchase is marked answered (not sent again this session) only when nothing
  // is left to do; otherwise recovery sends it again on the next resume.
  const submit = async (transaction) => {
    let evidence;
    try {
      evidence = purchaseEvidence(platform, transaction, productIds);
    } catch (error) {
      return { outcome: error.kind || "malformed" };
    }
    const key = `${evidence.provider}:${evidence.finishId || evidence.body.purchase_token}`;
    try {
      const result = evidence.provider === "apple" ? await api.verifyApple(evidence.body) : await api.verifyGoogle(evidence.body);
      // Google: the backend could not acknowledge yet; unacknowledged, Google refunds in 3 days.
      if (!(evidence.provider === "google" && result?.acknowledgement === "pending")) answered.add(key);
      await finishApple(evidence);
      return { outcome: "verified", storeStatus: result?.store_status || "", plan: result?.plan || null };
    } catch (error) {
      const kind = backendFailure(error);
      if (kind === "conflict" || (kind === "rejected" && evidence.provider === "apple")) {
        // A definitive answer: StoreKit need not deliver it again. A Google purchase
        // DINCR refused stays unacknowledged, so Google refunds it.
        answered.add(key);
        await finishApple(evidence);
        return { outcome: kind };
      }
      // The store may have charged and DINCR has not decided: say so, and retry later.
      // (503 after the store step, network, 5xx; a 422 from Google can be a temporary
      // Play API failure.)
      return { outcome: kind === "session" ? kind : "backend" };
    }
  };

  const currentPurchases = async () => {
    const result = await plugin.getPurchases({
      productType: SUBSCRIPTIONS,
      onlyCurrentEntitlements: true,
      autoAcknowledgePurchases: false,
    });
    return (result?.purchases || []).filter((purchase) => productIds.has(purchase?.productIdentifier));
  };

  return {
    platform,

    /** Offers to show, priced by the store. Throws StoreBillingError("unavailable"|...). */
    async loadOffers() {
      const products = await knownProducts();
      if (!products.length) return [];
      let storeProducts;
      try {
        const result = await plugin.getProducts({
          productIdentifiers: products.map((product) => product.productId),
          productType: SUBSCRIPTIONS,
          autoAcknowledgePurchases: false,
        });
        storeProducts = result?.products || [];
      } catch (error) {
        throw new StoreBillingError(storeFailure(error) === "store" ? "unavailable" : storeFailure(error), error);
      }
      return matchOffers(products, storeProducts, platform);
    },

    /** Whether the backend accepts store purchases now (the kill switch). */
    async availability() {
      try {
        await customerToken();
        return "available";
      } catch (error) {
        return error.kind || "backend";
      }
    },

    /**
     * Buy one offer. Resolves { outcome, entitlement?, profile? }; never grants a plan
     * itself. onStage("store" | "verifying") reports progress for the UI.
     */
    purchase(offer, { onStage = () => {} } = {}) {
      return exclusive(async () => {
        if (!offer || !productIds.has(offer.productId)) return { outcome: "unknown_product" };
        // A live store subscription (either store) is changed in the store, never
        // bought twice: Play has no in-app replacement here, so it would bill both.
        let current;
        try {
          current = await api.entitlement();
        } catch (error) {
          return { outcome: backendFailure(error) };
        }
        if (liveStoreSubscription(current)) return { outcome: "already_subscribed" };
        let token;
        try {
          token = await customerToken();
        } catch (error) {
          return { outcome: error.kind };
        }
        let transaction;
        onStage("store");
        try {
          transaction = await plugin.purchaseProduct({
            productIdentifier: offer.productId,
            productType: SUBSCRIPTIONS,
            // Play: the base plan to buy (the plugin's "planIdentifier" option).
            planIdentifier: platform === "android" ? offer.basePlanId : undefined,
            appAccountToken: token,
            quantity: 1,
            autoAcknowledgePurchases: false,
          });
        } catch (error) {
          return { outcome: storeFailure(error) };
        }
        onStage("verifying");
        const result = await submit(transaction);
        return result.outcome === "verified" ? { ...result, ...(await refresh()) } : result;
      });
    },

    /** "Restaurar compras": every current store subscription goes to the backend, which decides ownership. */
    restore() {
      return exclusive(async () => {
        try {
          await customerToken();
        } catch (error) {
          return { outcome: error.kind, results: [] };
        }
        await knownProducts();
        if (platform === "ios") {
          try {
            await plugin.restorePurchases(); // AppStore.sync(): refreshes this Apple ID's transactions
          } catch (error) {
            const kind = storeFailure(error);
            if (kind === "cancelled") return { outcome: "cancelled", results: [] };
          }
        }
        let purchases;
        try {
          purchases = await currentPurchases();
        } catch (error) {
          return { outcome: storeFailure(error) === "store" ? "unavailable" : storeFailure(error), results: [] };
        }
        const results = [];
        for (const purchase of purchases) results.push(await submit(purchase));
        return { outcome: "restored", results, ...(await refresh()) };
      });
    },

    /**
     * Silent recovery (app start, resume, StoreKit updates): a purchase the store charged
     * for this account but the backend has not answered yet is sent again.
     */
    async reconcile() {
      if (busy) return { outcome: "busy", results: [] };
      busy = true;
      try {
        await knownProducts();
        let purchases;
        try {
          purchases = await currentPurchases();
        } catch {
          return { outcome: "unavailable", results: [] };
        }
        if (!purchases.length) return { outcome: "reconciled", results: [] };
        let token;
        try {
          token = await customerToken();
        } catch (error) {
          return { outcome: error.kind, results: [] };
        }
        const pending = purchases.filter((purchase) => {
          if (String(purchase?.appAccountToken || "").toLowerCase() !== token) return false; // only this account's
          const key = platform === "ios" ? `apple:${purchase.transactionId}` : `google:${purchase.purchaseToken}`;
          if (answered.has(key)) return false;
          // Google: an acknowledged purchase was already verified by the backend.
          return platform === "ios" || (String(purchase.purchaseState) === ANDROID_PURCHASED && !purchase.isAcknowledged);
        });
        const results = [];
        for (const purchase of pending) results.push(await submit(purchase));
        const changed = results.some((result) => result.outcome === "verified");
        return { outcome: "reconciled", results, ...(changed ? await refresh() : {}) };
      } finally {
        busy = false;
      }
    },

    /** The store's own subscription management screen. */
    async manage() {
      await plugin.manageSubscriptions();
    },
  };
}
