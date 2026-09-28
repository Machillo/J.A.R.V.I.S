// Store billing on the device (src/lib/storeBilling): the real service against a
// simulated DINCR backend and simulated App Store / Google Play. The backend
// simulation applies the backend's own rules (customer token, 503 while store
// verification is off, a purchase bound to one account -> 409, unknown product -> 422,
// Google acknowledged only by the backend, the plan derived from verified purchases).
// The stores record what the device asked for, so the device's side of the contract
// (tokens, acknowledgement, finishing, never granting a plan) is checked, not assumed.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import {
  backendFailure, catalogProducts, createStoreBilling, liveStoreSubscription, matchOffers,
  purchaseEvidence, storeFailure, storePlatform,
} from "../src/lib/storeBilling/core.js";
import { outcomeMessage, restoreMessage } from "../src/lib/storeBilling/messages.js";

const IDS = { basic: { monthly: "dincr.basic.monthly", annual: "dincr.basic.annual" }, vip: { monthly: "dincr.vip.monthly", annual: "dincr.vip.annual" } };
const CATALOG = {
  currency: "CRC",
  plans: [
    { code: "basic", monthly: { price_crc: 2990, product_id: IDS.basic.monthly }, annual: { price_crc: 29900, product_id: IDS.basic.annual } },
    { code: "vip", monthly: { price_crc: 4990, product_id: IDS.vip.monthly }, annual: { price_crc: 49900, product_id: IDS.vip.annual } },
  ],
};
const httpError = (status) => Object.assign(new Error(`HTTP ${status}`), { status });
const uuid = (n) => `0000000${n}-aaaa-4bbb-8ccc-${String(n).padStart(12, "0")}`;

// ---- simulated backend ------------------------------------------------------------
function backend({ account = "acc-a", enabled = true } = {}) {
  const state = {
    enabled, down: false, account,
    tokens: new Map([["acc-a", uuid(1)], ["acc-b", uuid(2)]]),
    purchases: new Map(), // purchase key -> { account, plan, live }
    acknowledged: new Set(), calls: [],
  };
  const planOf = (productId) => Object.entries(IDS).find(([, periods]) => Object.values(periods).includes(productId))?.[0];
  const accountOfToken = (token) => [...state.tokens].find(([, value]) => value === token)?.[0];
  const guard = () => {
    if (state.down) throw httpError(0);
    if (!state.enabled) throw httpError(503);
  };
  const bind = (key, token, productId, live) => {
    const plan = planOf(productId);
    if (!plan) throw httpError(422);
    const owner = state.purchases.get(key)?.account || accountOfToken(token) || state.account;
    if (owner !== state.account) throw httpError(409);
    state.purchases.set(key, { account: owner, plan, live });
    return { status: "applied", plan: live ? plan : "free", store_status: live ? "active" : "expired", resolved: true };
  };
  const plan = () => {
    const live = [...state.purchases.values()].filter((p) => p.account === state.account && p.live).map((p) => p.plan);
    return live.includes("vip") ? "vip" : live.includes("basic") ? "basic" : "free";
  };
  const api = {
    customerToken: async () => { state.calls.push("customer-token"); guard(); return { token: state.tokens.get(state.account).toUpperCase() }; },
    storeCatalog: async () => CATALOG,
    verifyApple: async (body) => {
      state.calls.push("apple"); guard();
      assert.deepEqual(Object.keys(body), ["signed_transaction"]);
      const claims = JSON.parse(Buffer.from(body.signed_transaction.split(".")[1], "base64url"));
      return bind(`apple:${claims.originalTransactionId}`, claims.appAccountToken, claims.productId, claims.live !== false);
    },
    verifyGoogle: async (body) => {
      state.calls.push("google"); guard();
      assert.deepEqual(Object.keys(body).sort(), ["product_id", "purchase_token"]);
      const record = state.google?.get(body.purchase_token);
      if (!record || record.productId !== body.product_id) throw httpError(422); // the Play API is authoritative
      const result = bind(`google:${body.purchase_token}`, record.accountId, record.productId, true);
      state.acknowledged.add(body.purchase_token); // the backend acknowledges after verifying
      record.acknowledged = true;
      return result;
    },
    entitlement: async () => ({ provider: plan() === "free" ? null : "apple", entitlement: plan(), plan: plan(), billing_period: "monthly" }),
    profile: async () => ({ role: "user", plan_selected: true, subscription: { plan: plan(), status: "active", access_source: "self_service" } }),
  };
  return { state, api };
}

// ---- simulated stores -------------------------------------------------------------
const PRODUCTS = Object.values(IDS).flatMap((periods) => Object.entries(periods)).map(([period, id]) => ({
  identifier: id, priceString: id.includes("vip") ? "US$4.99" : "US$2.99", currencyCode: "USD", title: id, period,
}));
// iOS (StoreKit): identifier = product id.
const APPLE_PRODUCTS = PRODUCTS.map(({ period, ...product }) => product);
// Android subscriptions, as the plugin reports them (NativePurchasesPlugin.getProducts):
// one entry per offer; identifier = base plan id, planIdentifier = Play product id.
const GOOGLE_PRODUCTS = PRODUCTS.flatMap(({ identifier, period, ...product }) => [
  { ...product, identifier: period, planIdentifier: identifier, offerId: "free-trial", priceString: "Gratis" },
  { ...product, identifier: period, planIdentifier: identifier, offerId: null },
]);

function appleStore() {
  const store = { mode: "ok", calls: [], finished: [], owned: [], nextId: 1000 };
  const jws = (claims) => ["eyJhbGciOiJFUzI1NiJ9", Buffer.from(JSON.stringify(claims)).toString("base64url"), "c2lnbmF0dXJlLXNpZ25hdHVyZQ"].join(".");
  store.plugin = {
    getProducts: async (options) => { store.calls.push(["getProducts", options]); return { products: [...APPLE_PRODUCTS, { identifier: "someone.else.product", priceString: "US$1" }] }; },
    purchaseProduct: async (options) => {
      store.calls.push(["purchaseProduct", options]);
      if (store.mode === "cancel") throw new Error("User cancelled");
      if (store.mode === "pending") throw new Error("Transaction pending");
      const id = String(store.nextId++);
      const transaction = {
        transactionId: id, productIdentifier: options.productIdentifier, appAccountToken: options.appAccountToken,
        jwsRepresentation: jws({ originalTransactionId: `orig-${id}`, productId: options.productIdentifier, appAccountToken: options.appAccountToken }),
      };
      store.owned.push(transaction);
      return transaction;
    },
    getPurchases: async (options) => { store.calls.push(["getPurchases", options]); return { purchases: store.owned }; },
    restorePurchases: async () => { store.calls.push(["restorePurchases"]); },
    acknowledgePurchase: async ({ purchaseToken }) => { store.finished.push(purchaseToken); },
    manageSubscriptions: async () => {},
  };
  return store;
}

function googleStore(backendState) {
  const store = { mode: "ok", calls: [], owned: [], clientAcks: 0, nextId: 1 };
  backendState.google = new Map();
  store.plugin = {
    getProducts: async (options) => { store.calls.push(["getProducts", options]); return { products: GOOGLE_PRODUCTS }; },
    purchaseProduct: async (options) => {
      store.calls.push(["purchaseProduct", options]);
      if (store.mode === "cancel") throw Object.assign(new Error("Purchase is not purchased"), { code: "USER_CANCELED" });
      const token = `play-token-${String(store.nextId++).padStart(6, "0")}`;
      const purchase = {
        purchaseToken: token, transactionId: token, productIdentifier: options.productIdentifier,
        appAccountToken: options.appAccountToken, purchaseState: store.mode === "pending" ? "2" : "1", isAcknowledged: false,
      };
      backendState.google.set(token, { productId: options.productIdentifier, accountId: options.appAccountToken, acknowledged: false });
      store.owned.push(purchase);
      if (store.mode === "pending") throw new Error("Purchase is pending");
      return purchase;
    },
    getPurchases: async (options) => {
      store.calls.push(["getPurchases", options]);
      return { purchases: store.owned.map((p) => ({ ...p, isAcknowledged: backendState.google.get(p.purchaseToken)?.acknowledged || false })) };
    },
    restorePurchases: async () => { throw new Error("restorePurchases acknowledges every purchase on Android: never call it"); },
    acknowledgePurchase: async () => { store.clientAcks += 1; throw new Error("the device must never acknowledge on Google Play"); },
    manageSubscriptions: async () => {},
  };
  return store;
}

const setup = (platform, options) => {
  const server = backend(options);
  const store = platform === "ios" ? appleStore() : googleStore(server.state);
  const billing = createStoreBilling({ platform, plugin: store.plugin, api: server.api });
  return { server, store, billing };
};

// ---- platform and catalog ---------------------------------------------------------
assert.equal(storePlatform({ isNativePlatform: () => false, getPlatform: () => "web" }), null, "web: no store billing");
assert.equal(storePlatform(undefined), null);
assert.equal(storePlatform({ isNativePlatform: () => true, getPlatform: () => "ios" }), "ios");
assert.equal(storePlatform({ isNativePlatform: () => true, getPlatform: () => "android" }), "android");
assert.equal(storePlatform({ isNativePlatform: () => true, getPlatform: () => "electron" }), null);

const products = catalogProducts(CATALOG);
assert.deepEqual(products.map((p) => `${p.plan}/${p.period}=${p.productId}`), [
  "basic/monthly=dincr.basic.monthly", "basic/annual=dincr.basic.annual", "vip/monthly=dincr.vip.monthly", "vip/annual=dincr.vip.annual",
]);
assert.deepEqual(catalogProducts({ plans: [{ code: "owner", monthly: { product_id: "x" } }, { code: "vip", monthly: { product_id: " " } }] }), [], "only Basic/VIP with an id");
const offers = matchOffers(products, [...APPLE_PRODUCTS.filter((p) => p.identifier !== IDS.vip.annual), { identifier: "foreign", priceString: "1" }], "ios");
assert.deepEqual(offers.map((o) => o.productId), [IDS.basic.monthly, IDS.basic.annual, IDS.vip.monthly], "store-missing products are not offered, foreign ones ignored");
assert.equal(offers[2].priceString, "US$4.99", "the price is the store's, never the backend's");
assert.ok(!JSON.stringify(offers).includes("4990"), "no backend price reaches an offer");
const googleOffers = matchOffers(products, GOOGLE_PRODUCTS, "android");
assert.deepEqual(googleOffers.map((o) => `${o.productId}@${o.basePlanId}`), [
  "dincr.basic.monthly@monthly", "dincr.basic.annual@annual", "dincr.vip.monthly@monthly", "dincr.vip.annual@annual",
], "Android: product id from planIdentifier, base plan from identifier");
assert.ok(googleOffers.every((o) => o.priceString.startsWith("US$")), "the base plan's regular price, not a trial offer's");
assert.deepEqual(matchOffers(products, APPLE_PRODUCTS, "android"), [], "iOS-shaped entries never match on Android");
assert.equal(matchOffers(products, [
  { planIdentifier: IDS.basic.monthly, identifier: "legacy", priceString: "1" },
  { planIdentifier: IDS.basic.monthly, identifier: "monthly", priceString: "2" },
], "android")[0].basePlanId, "monthly", "a base plan named after the period is preferred");

// ---- evidence and error mapping ---------------------------------------------------
const ids = new Set(Object.values(IDS).flatMap((p) => Object.values(p)));
assert.throws(() => purchaseEvidence("ios", { productIdentifier: "evil.product", jwsRepresentation: "a.b.c", transactionId: "1" }, ids), { kind: "unknown_product" });
assert.throws(() => purchaseEvidence("ios", { productIdentifier: IDS.vip.monthly, jwsRepresentation: "not-a-jws", transactionId: "1" }, ids), { kind: "malformed" });
assert.throws(() => purchaseEvidence("ios", { productIdentifier: IDS.vip.monthly, jwsRepresentation: "aaaaaaa.bbbbbbb.cccccc", transactionId: "x1" }, ids), { kind: "malformed" });
assert.throws(() => purchaseEvidence("android", { productIdentifier: IDS.vip.monthly, purchaseToken: "short" }, ids), { kind: "malformed" });
assert.throws(() => purchaseEvidence("android", { productIdentifier: IDS.vip.monthly, purchaseToken: "x".repeat(20), purchaseState: "2" }, ids), { kind: "pending" });
assert.deepEqual(purchaseEvidence("android", { productIdentifier: IDS.vip.monthly, purchaseToken: "x".repeat(20), purchaseState: "1" }, ids).body,
  { purchase_token: "x".repeat(20), product_id: IDS.vip.monthly });
assert.equal(storeFailure(new Error("User cancelled")), "cancelled");
assert.equal(storeFailure({ code: "USER_CANCELED", message: "Purchase is not purchased" }), "cancelled");
assert.equal(storeFailure(new Error("Purchase is pending")), "pending");
assert.equal(storeFailure({ code: "BILLING_UNAVAILABLE" }), "unavailable");
assert.equal(storeFailure(new Error("boom")), "store");
assert.deepEqual([503, 409, 422, 401, 0, 500].map((status) => backendFailure({ status })), ["disabled", "conflict", "rejected", "session", "network", "backend"]);
assert.equal(liveStoreSubscription({ provider: "sandbox", entitlement: "vip" }), null, "the Owner simulator's rows are not a store subscription");

// ---- purchase flows ---------------------------------------------------------------
{
  // App Store: token from the backend as appAccountToken; finish only after the backend answered.
  const { server, store, billing } = setup("ios");
  const [offer] = (await billing.loadOffers()).filter((o) => o.productId === IDS.vip.monthly);
  const stages = [];
  const result = await billing.purchase(offer, { onStage: (stage) => stages.push(stage) });
  assert.equal(result.outcome, "verified");
  assert.deepEqual(stages, ["store", "verifying"]);
  const purchase = store.calls.find(([name]) => name === "purchaseProduct")[1];
  assert.equal(purchase.appAccountToken, uuid(1), "the backend's customer token, exactly (normalized to lowercase)");
  assert.equal(purchase.autoAcknowledgePurchases, false, "StoreKit does not finish before the backend answered");
  assert.equal(purchase.productType, "subs");
  assert.deepEqual(store.finished, ["1000"], "finished after the backend verified it");
  assert.equal(result.profile.subscription.plan, "vip", "the plan shown is the backend's");
  assert.deepEqual(server.state.calls, ["customer-token", "apple"]);
}
{
  // Google Play: obfuscated account id = customer token; the backend alone acknowledges.
  const { server, store, billing } = setup("android");
  const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.basic.annual);
  const result = await billing.purchase(offer);
  assert.equal(result.outcome, "verified");
  const purchase = store.calls.find(([name]) => name === "purchaseProduct")[1];
  assert.equal(purchase.appAccountToken, uuid(1));
  assert.equal(purchase.productIdentifier, IDS.basic.annual);
  assert.equal(purchase.planIdentifier, "annual", "the base plan the store returned (the plugin's option name)");
  assert.ok(store.calls.every(([, options]) => !options || options.autoAcknowledgePurchases === false), "every plugin call disables auto-acknowledge");
  assert.equal(store.clientAcks, 0, "the device never acknowledges");
  assert.equal(server.state.acknowledged.size, 1, "the backend acknowledged after verifying");
  assert.equal(result.profile.subscription.plan, "basic");
}
{
  // Store verification off (503): nothing is bought, nothing is granted.
  const { server, store, billing } = setup("ios", { enabled: false });
  assert.equal(await billing.availability(), "disabled");
  await billing.loadOffers();
  const result = await billing.purchase({ productId: IDS.vip.monthly, plan: "vip", period: "monthly" });
  assert.equal(result.outcome, "disabled");
  assert.ok(!store.calls.some(([name]) => name === "purchaseProduct"), "the store is never opened while DINCR cannot verify");
  assert.equal((await server.api.profile()).subscription.plan, "free");
  assert.match(outcomeMessage("disabled").text, /todavía no están disponibles|aren’t available yet/);
}
{
  // Cancelled by the user: no backend call, no plan.
  const { server, store, billing } = setup("android");
  const offer = (await billing.loadOffers())[0];
  store.mode = "cancel";
  assert.equal((await billing.purchase(offer)).outcome, "cancelled");
  assert.deepEqual(server.state.calls, ["customer-token"]);
}
{
  // Pending payment (Google): no plan now; recovered once the store completes it.
  const { server, store, billing } = setup("android");
  const offer = (await billing.loadOffers())[0];
  store.mode = "pending";
  assert.equal((await billing.purchase(offer)).outcome, "pending");
  assert.equal((await server.api.profile()).subscription.plan, "free");
  assert.equal((await billing.reconcile()).results.length, 0, "a pending purchase is not sent");
  store.owned[0].purchaseState = "1"; // the payment completes later
  const recovered = await billing.reconcile();
  assert.deepEqual(recovered.results.map((r) => r.outcome), ["verified"]);
  assert.equal(recovered.profile.subscription.plan, "basic");
  assert.equal(store.clientAcks, 0);
}
{
  // Pending (Apple Ask to Buy) is reported, nothing granted.
  const { billing, store } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  store.mode = "pending";
  assert.equal((await billing.purchase(offer)).outcome, "pending");
}
{
  // Charged, then DINCR unreachable: not finished / not acknowledged, recovered later, once.
  for (const platform of ["ios", "android"]) {
    const { server, store, billing } = setup(platform);
    const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.vip.monthly);
    const originalVerify = platform === "ios" ? server.api.verifyApple : server.api.verifyGoogle;
    const key = platform === "ios" ? "verifyApple" : "verifyGoogle";
    server.api[key] = async () => { throw httpError(0); };
    const result = await billing.purchase(offer);
    assert.equal(result.outcome, "backend", platform);
    assert.match(outcomeMessage("network", { context: "purchase" }).text, /reintentaremos|retry/);
    if (platform === "ios") assert.deepEqual(store.finished, [], "unfinished: StoreKit keeps it for recovery");
    else assert.equal(server.state.acknowledged.size, 0, "unacknowledged: nothing contradicts the backend");
    server.api[key] = originalVerify; // DINCR is back (app resume)
    const recovered = await billing.reconcile();
    assert.deepEqual(recovered.results.map((r) => r.outcome), ["verified"], platform);
    assert.equal(recovered.profile.subscription.plan, "vip", platform);
    const again = await billing.reconcile();
    assert.equal(again.results.length, 0, `${platform}: an answered purchase is not sent twice`);
  }
}
{
  // Nothing bought in the store: recovery asks the backend for nothing (no token row).
  const { server, billing } = setup("ios");
  assert.deepEqual(await billing.reconcile(), { outcome: "reconciled", results: [] });
  assert.deepEqual(server.state.calls, []);
}
{
  // Kill switch off at recovery time: silent, nothing sent.
  const { server, store, billing } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  const verify = server.api.verifyApple;
  server.api.verifyApple = async () => { throw httpError(0); };
  await billing.purchase(offer);
  server.api.verifyApple = verify;
  server.state.enabled = false;
  server.state.calls.length = 0;
  assert.equal((await billing.reconcile()).outcome, "disabled");
  assert.deepEqual(server.state.calls, ["customer-token"]);
  assert.deepEqual(store.finished, []);
}
{
  // Restore from another DINCR account: the backend says 409; nothing changes here.
  const { server, store, billing } = setup("ios");
  const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.vip.annual);
  assert.equal((await billing.purchase(offer)).outcome, "verified");
  server.state.account = "acc-b"; // another DINCR login on the same Apple ID
  const restored = await billing.restore();
  assert.deepEqual(restored.results.map((r) => r.outcome), ["conflict"]);
  assert.equal(restored.profile.subscription.plan, "free", "account B gains nothing");
  assert.ok(store.calls.some(([name]) => name === "restorePurchases"), "iOS restore syncs with the App Store first");
  const message = restoreMessage(restored, "free");
  assert.match(message.text, /otra cuenta DINCR|another DINCR account/);
  assert.ok(!/acc-|0000|orig-/.test(message.text), "no internal id in the message");
  // Silent recovery skips purchases made for another account's token.
  const silent = await billing.reconcile();
  assert.equal(silent.results.length, 0);
}
{
  // Silent recovery sends only this account's purchases: another DINCR account signed in
  // on a device whose store account bought for account A never claims it by itself.
  for (const platform of ["ios", "android"]) {
    const { server, store, billing } = setup(platform);
    const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.basic.monthly);
    const key = platform === "ios" ? "verifyApple" : "verifyGoogle";
    const verify = server.api[key];
    server.api[key] = async () => { throw httpError(0); };
    assert.equal((await billing.purchase(offer)).outcome, "backend");
    server.api[key] = verify;
    server.state.account = "acc-b";
    const other = createStoreBilling({ platform, plugin: store.plugin, api: server.api });
    const silent = await other.reconcile();
    assert.equal(silent.results.length, 0, `${platform}: account B does not send A's purchase`);
    assert.ok(!server.state.calls.slice(-3).includes(platform === "ios" ? "apple" : "google"));
  }
}
{
  // Android restore: current purchases only (no restorePurchases, no client acknowledgement).
  const { server, store, billing } = setup("android");
  const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.vip.monthly);
  const verifyGoogle = server.api.verifyGoogle;
  server.api.verifyGoogle = async () => { throw httpError(0); };
  assert.equal((await billing.purchase(offer)).outcome, "backend");
  server.api.verifyGoogle = verifyGoogle;
  const restored = await billing.restore();
  assert.deepEqual(restored.results.map((r) => r.outcome), ["verified"]);
  assert.equal(restored.profile.subscription.plan, "vip");
  assert.equal(store.clientAcks, 0);
  assert.ok(!store.calls.some(([name]) => name === "restorePurchases"));
}
{
  // The backend is authoritative: a purchase it finds inactive grants nothing.
  const { server, store, billing } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  const original = store.plugin.purchaseProduct;
  store.plugin.purchaseProduct = async (options) => {
    const transaction = await original(options);
    const parts = transaction.jwsRepresentation.split(".");
    const claims = { ...JSON.parse(Buffer.from(parts[1], "base64url")), live: false };
    return { ...transaction, jwsRepresentation: [parts[0], Buffer.from(JSON.stringify(claims)).toString("base64url"), parts[2]].join(".") };
  };
  const result = await billing.purchase(offer);
  assert.equal(result.outcome, "verified");
  assert.equal(result.profile.subscription.plan, "free", "a local success is not a plan");
  assert.equal(outcomeMessage("verified", { plan: "free" }).tone, "warning");
  assert.equal(server.state.calls.filter((c) => c === "apple").length, 1);
}
{
  // Unknown product and malformed store results never reach the backend.
  const { server, store, billing } = setup("ios");
  await billing.loadOffers();
  assert.equal((await billing.purchase({ productId: "evil.product", plan: "vip", period: "monthly" })).outcome, "unknown_product");
  store.plugin.purchaseProduct = async (options) => ({ productIdentifier: options.productIdentifier, transactionId: "5", jwsRepresentation: "garbage" });
  assert.equal((await billing.purchase({ productId: IDS.vip.monthly, plan: "vip", period: "monthly" })).outcome, "malformed");
  assert.equal((await billing.purchase({ productId: IDS.vip.monthly, plan: "vip", period: "monthly" })).outcome, "malformed");
  assert.ok(!server.state.calls.includes("apple"));
}
{
  // No double purchase: a second tap while the first is in progress is refused.
  const { store, billing } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  let release;
  const original = store.plugin.purchaseProduct;
  store.plugin.purchaseProduct = (options) => new Promise((resolve) => { release = () => resolve(original(options)); });
  const first = billing.purchase(offer);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal((await billing.purchase(offer)).outcome, "busy");
  assert.equal((await billing.restore()).outcome, "busy");
  assert.equal((await billing.reconcile()).outcome, "busy", "recovery waits for the purchase in progress");
  release();
  assert.equal((await first).outcome, "verified");
  assert.equal(store.calls.filter(([name]) => name === "purchaseProduct").length, 1);
}

{
  // One live store subscription at a time: no second, concurrently billed purchase.
  for (const platform of ["ios", "android"]) {
    const { store, billing } = setup(platform);
    const loaded = await billing.loadOffers();
    assert.equal((await billing.purchase(loaded.find((o) => o.productId === IDS.basic.monthly))).outcome, "verified");
    const second = await billing.purchase(loaded.find((o) => o.productId === IDS.vip.monthly));
    assert.equal(second.outcome, "already_subscribed", platform);
    assert.equal(store.calls.filter(([name]) => name === "purchaseProduct").length, 1, `${platform}: the store is not opened again`);
    assert.match(outcomeMessage("already_subscribed").text, /Gestionar suscripción|Manage subscription/);
  }
}
{
  // 503 after the store charged (switched off mid-purchase / deploy): "we'll retry", not "unavailable".
  const { server, billing } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  const verify = server.api.verifyApple;
  server.api.verifyApple = async () => { throw httpError(503); };
  const result = await billing.purchase(offer);
  assert.equal(result.outcome, "backend");
  assert.match(outcomeMessage(result.outcome, { context: "purchase" }).text, /reintentaremos|retry/);
  server.api.verifyApple = verify;
  assert.deepEqual((await billing.reconcile()).results.map((r) => r.outcome), ["verified"], "still recovered");
}
{
  // Google: an acknowledgement the backend could not make yet, or a 422 (possibly a
  // temporary Play API failure), is sent again on the next resume.
  const { server, store, billing } = setup("android");
  const offer = (await billing.loadOffers())[0];
  const verify = server.api.verifyGoogle;
  server.api.verifyGoogle = async () => { throw httpError(422); };
  assert.equal((await billing.purchase(offer)).outcome, "backend", "a Google 422 may be temporary: retry message");
  server.api.verifyGoogle = async (body) => {
    const result = await verify(body);
    server.state.acknowledged.delete(body.purchase_token);
    server.state.google.get(body.purchase_token).acknowledged = false;
    return { ...result, acknowledgement: "pending" };
  };
  assert.deepEqual((await billing.reconcile()).results.map((r) => r.outcome), ["verified"]);
  server.api.verifyGoogle = verify;
  assert.deepEqual((await billing.reconcile()).results.map((r) => r.outcome), ["verified"], "resent until acknowledged");
  assert.equal(server.state.acknowledged.size, 1);
  assert.equal((await billing.reconcile()).results.length, 0, "acknowledged: done");
  assert.equal(store.clientAcks, 0);
}
{
  // Apple: a 422 (signature not verifiable) is final; the transaction is finished.
  const { server, store, billing } = setup("ios");
  const offer = (await billing.loadOffers())[0];
  server.api.verifyApple = async () => { throw httpError(422); };
  assert.equal((await billing.purchase(offer)).outcome, "rejected");
  assert.deepEqual(store.finished, ["1000"]);
}

// ---- restore: the store first, the backend only when the store holds DINCR purchases ----
// One ordered log across store and backend, so the sequence itself is checked.
const traced = ({ server, store }) => {
  const order = [];
  const wrap = (target, name, label) => {
    const original = target[name];
    target[name] = async (...args) => { order.push(label); return original(...args); };
  };
  wrap(store.plugin, "restorePurchases", "store:sync");
  wrap(store.plugin, "getPurchases", "store:purchases");
  wrap(server.api, "customerToken", "backend:customer-token");
  wrap(server.api, "verifyApple", "backend:verify");
  wrap(server.api, "verifyGoogle", "backend:verify");
  return order;
};
{
  // A. No DINCR purchase in the store: no customer token, no verification.
  for (const platform of ["ios", "android"]) {
    const context = setup(platform);
    const order = traced(context);
    assert.deepEqual(await context.billing.restore(), { outcome: "restored", results: [] }, platform);
    assert.deepEqual(order, platform === "ios" ? ["store:sync", "store:purchases"] : ["store:purchases"], platform);
    assert.deepEqual(context.server.state.calls, [], `${platform}: the backend is not asked anything`);
    assert.match(restoreMessage({ outcome: "restored", results: [] }).text, /No encontramos|didn’t find/);
  }
  // Also with store verification off: the store answers first, and it holds nothing.
  const off = setup("ios", { enabled: false });
  traced(off);
  assert.deepEqual(await off.billing.restore(), { outcome: "restored", results: [] });
  assert.deepEqual(off.server.state.calls, []);
}
{
  // B. DINCR purchases in the store, store verification off (503): the store is read
  // first, then the customer token is refused, and no evidence reaches the backend.
  for (const platform of ["ios", "android"]) {
    const context = setup(platform);
    const { server, store, billing } = context;
    const offer = (await billing.loadOffers())[0];
    const key = platform === "ios" ? "verifyApple" : "verifyGoogle";
    const verify = server.api[key];
    server.api[key] = async () => { throw httpError(0); };
    assert.equal((await billing.purchase(offer)).outcome, "backend"); // charged, not verified
    server.api[key] = verify;
    server.state.enabled = false;
    server.state.calls.length = 0;
    const order = traced(context);
    const result = await billing.restore();
    assert.deepEqual(result, { outcome: "disabled", results: [] }, platform);
    assert.deepEqual(order, [...(platform === "ios" ? ["store:sync"] : []), "store:purchases", "backend:customer-token"], platform);
    assert.deepEqual(server.state.calls, ["customer-token"], `${platform}: no evidence sent`);
    if (platform === "ios") assert.deepEqual(store.finished, [], "still unfinished, so recovery can send it later");
    else assert.equal(store.clientAcks, 0);
    assert.match(restoreMessage(result).text, /todavía no están disponibles|aren’t available yet/);
    // D. Android never calls the plugin's restorePurchases (it acknowledges everything).
    if (platform === "android") assert.ok(!store.calls.some(([name]) => name === "restorePurchases"));
  }
}
{
  // C. DINCR purchases and verification on: restore verifies them, as before.
  for (const platform of ["ios", "android"]) {
    const context = setup(platform);
    const { server, store, billing } = context;
    const offer = (await billing.loadOffers()).find((o) => o.productId === IDS.vip.monthly);
    const key = platform === "ios" ? "verifyApple" : "verifyGoogle";
    const verify = server.api[key];
    server.api[key] = async () => { throw httpError(0); };
    await billing.purchase(offer);
    server.api[key] = verify;
    const order = traced(context);
    const restored = await billing.restore();
    assert.deepEqual(restored.results.map((r) => r.outcome), ["verified"], platform);
    assert.equal(restored.profile.subscription.plan, "vip", platform);
    // E. iOS: AppStore.sync before reading current entitlements; D. Android: neither
    // restorePurchases nor a client acknowledgement.
    assert.deepEqual(order, [...(platform === "ios" ? ["store:sync"] : []), "store:purchases", "backend:customer-token", "backend:verify"], platform);
    if (platform === "ios") assert.deepEqual(store.finished, ["1000"]);
    else assert.equal(store.clientAcks, 0);
  }
}

// ---- static checks on the device code ---------------------------------------------
const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const sources = [
  ...readdirSync(new URL("../src/lib/storeBilling/", import.meta.url)).map((name) => `src/lib/storeBilling/${name}`),
  "src/users/components/StoreSubscriptionPanel.jsx",
];
for (const path of sources) {
  const source = read(path);
  assert.doesNotMatch(source, /console\.|localStorage|sessionStorage|indexedDB|trackEvent|captureProductEvent|posthog/, `${path}: evidence is never logged, stored or tracked`);
  assert.doesNotMatch(source, /private_key|service_account|BEGIN (EC )?PRIVATE KEY|p8|client_secret/i, `${path}: no store secret on the device`);
  assert.doesNotMatch(source, /restorePurchases\(\)[^\n]*android|platform === "android"[^\n]*restorePurchases/, `${path}: no restorePurchases on Android`);
  // These create a Play billing client without our options, which auto-acknowledges.
  assert.doesNotMatch(source, /isBillingSupported|getStorefront|consumePurchase/, `${path}: no plugin call that can acknowledge on Android`);
}
const recoveryRule = read("src/lib/operationRecovery.js").match(/const RECOVERABLE_PATH = (\/.*\/);/)[1];
const recoverable = new Function(`return ${recoveryRule}`)();
for (const path of ["/product-ops/billing/store/customer-token", "/product-ops/billing/store/apple/transactions", "/product-ops/billing/store/google/purchases"]) {
  assert.equal(recoverable.test(path), false, `${path} is never queued on the device`);
}
const api = read("src/users/services/jarvisApi.js");
assert.match(api, /verifyAppleTransaction = \(body\) => json\("\/product-ops\/billing\/store\/apple\/transactions", "POST", body\)/);
assert.match(api, /verifyGooglePurchase = \(body\) => json\("\/product-ops\/billing\/store\/google\/purchases", "POST", body\)/);
assert.match(read("src/lib/storeBilling/index.js"), /await import\("@capgo\/native-purchases"\)/, "the plugin is loaded only in the native app");
assert.match(read("src/users/pages/Settings.jsx"), /nativeStorePlatform\(\) && user\?\.role === "user" && <StoreSubscriptionPanel/, "web and Owner never see store buttons");
const iosConfig = JSON.parse(read("capacitor.ios.dincr.json"));
assert.ok(iosConfig.includePlugins.includes("@capgo/native-purchases"), "iOS bundles the purchases plugin");
assert.match(read("ios-dincr/App/CapApp-SPM/Package.swift"), /\.product\(name: "CapgoNativePurchases"/);
assert.match(read("android/capacitor.settings.gradle"), /capgo-native-purchases/);
assert.equal(JSON.parse(read("package.json")).dependencies["@capgo/native-purchases"], "8.8.1", "the plugin version is pinned");

console.log("Store billing on the device: backend-authoritative purchase, restore and recovery contracts passed.");
