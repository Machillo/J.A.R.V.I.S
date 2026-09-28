import { Capacitor } from "@capacitor/core";
import {
  getMe,
  getStoreBillingCatalog,
  getStoreCustomerToken,
  getStoreEntitlement,
  verifyAppleTransaction,
  verifyGooglePurchase,
} from "../../users/services/jarvisApi";
import { createStoreBilling, storePlatform } from "./core";

export { StoreBillingError, liveStoreSubscription } from "./core";

const api = {
  customerToken: getStoreCustomerToken,
  storeCatalog: getStoreBillingCatalog,
  verifyApple: verifyAppleTransaction,
  verifyGoogle: verifyGooglePurchase,
  entitlement: getStoreEntitlement,
  profile: getMe,
};

let service = null;

/** "ios" / "android" when store billing can run here; null on the web. */
export const nativeStorePlatform = () => storePlatform(Capacitor);

/** The store billing service in the native app; null on the web. */
export async function storeBilling() {
  const platform = storePlatform(Capacitor);
  if (!platform) return null;
  if (!service) {
    // Loaded only in the native app: the web bundle never reaches store billing.
    const { NativePurchases } = await import("@capgo/native-purchases");
    service = createStoreBilling({ platform, plugin: NativePurchases, api });
    if (platform === "ios") {
      // Renewals, Ask to Buy approvals and purchases made on another device.
      let timer = null;
      NativePurchases.addListener("transactionUpdated", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => { service.reconcile().then(notify).catch(() => {}); }, 1500);
      });
    }
  }
  return service;
}

const notify = (result) => {
  if (result?.profile || result?.entitlement) {
    window.dispatchEvent(new CustomEvent("dincr:store-entitlement", { detail: result }));
  }
  return result;
};

/**
 * Recover purchases the store charged but DINCR has not verified yet (app start and
 * resume). Silent: does nothing on the web, while store verification is off, or when
 * nothing is pending.
 */
export async function recoverStorePurchases() {
  try {
    const billing = await storeBilling();
    if (!billing) return null;
    return notify(await billing.reconcile());
  } catch {
    return null;
  }
}
