import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Minimal WebView globals: mailOAuth.js runs in the Capacitor WebView.
const memoryStorage = () => {
  const store = new Map();
  return {
    store,
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
};
const events = [];
let onReturn = () => {};
globalThis.window = {
  sessionStorage: memoryStorage(),
  localStorage: memoryStorage(),
  // Mirrors UsersApp: every queued return triggers a redeem.
  dispatchEvent: (event) => { events.push(event); if (event.type === "dincr:mail-oauth-return") onReturn(); },
};
globalThis.CustomEvent ??= class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } };

const {
  MAIL_OAUTH_RESULT_EVENT, captureMailOAuthReturns, parseMailOAuthReturn, redeemPendingMailOAuth, takeMailOAuthOutcome,
} = await import("../src/lib/mailOAuth.js");

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
let flowSeq = 0;
const newFlow = () => `0f6b6c1e-1111-4222-8333-${String(++flowSeq).padStart(12, "0")}`;
const returnUrl = (provider, status, extra = {}, scheme = "com.dincr.app") =>
  `${scheme}://gmail/callback?${new URLSearchParams({ [provider]: status, ...extra, ret: `r${++flowSeq}` })}`;
const authorized = (provider, scheme) => {
  const flow = newFlow();
  return { flow, url: returnUrl(provider, "authorized", { flow, completion: `code-${flow}` }, scheme) };
};

// A fake backend that, like mail_oauth.complete_flow, attaches each flow once.
function backend() {
  const attached = [];
  const calls = [];
  let failNext = null;
  return {
    attached, calls,
    failNextWith(error) { failNext = error; },
    async complete(flow, completion) {
      calls.push(flow);
      await settle();
      if (failNext) { const error = failNext; failNext = null; throw error; }
      assert.equal(completion, `code-${flow}`);
      if (!attached.includes(flow)) attached.push(flow);
      return { status: "connected" };
    },
  };
}

// Capacitor App plugin with the delivery semantics observed on each platform:
// appUrlOpen is retained until a listener exists (cold start), and
// getLaunchUrl() returns the launch intent (Android) / last opened URL (iOS).
function fakeApp({ launchUrl = null, retained = [] } = {}) {
  const listeners = [];
  const queue = [...retained];
  return {
    closes: 0,
    addListener(name, callback) {
      if (name === "appUrlOpen") {
        listeners.push(callback);
        while (queue.length) callback({ url: queue.shift() });
      }
    },
    getLaunchUrl: async () => (launchUrl ? { url: launchUrl } : undefined),
    open(url) { for (const listener of listeners) listener({ url }); },
  };
}
const fakeBrowser = () => ({ closes: 0, async close() { this.closes += 1; } });

function freshSession(api) {
  window.sessionStorage = memoryStorage();
  events.length = 0;
  takeMailOAuthOutcome();
  onReturn = () => { redeemPendingMailOAuth(api.complete); };
}
const results = () => events.filter((event) => event.type === MAIL_OAUTH_RESULT_EVENT).map((event) => event.detail);

// --- Parsing --------------------------------------------------------------
{
  const flow = newFlow();
  assert.deepEqual(parseMailOAuthReturn(`com.finva.app://gmail/callback?gmail=authorized&flow=${flow}&completion=one-time&ret=abc`),
    { provider: "gmail", status: "authorized", flow, completion: "one-time", ret: "abc" });
  assert.equal(parseMailOAuthReturn("com.dincr.app://gmail/callback?microsoft=invalid_state").provider, "microsoft");
  assert.equal(parseMailOAuthReturn("https://evil.example/?gmail=authorized&flow=x&completion=y"), null);
  assert.equal(parseMailOAuthReturn("com.dincr.app://auth/callback?code=x"), null, "sign-in returns are not mail returns");
}

for (const platform of ["android", "ios"]) {
  for (const provider of ["gmail", "microsoft"]) {
    for (const scheme of ["com.dincr.app", "com.finva.app"]) {
      const label = `${platform}/${provider}/${scheme}`;

      // 1-2, 6. Cold start: the link arrives as a retained appUrlOpen AND via getLaunchUrl.
      {
        const api = backend();
        freshSession(api);
        const { flow, url } = authorized(provider, scheme);
        const browser = fakeBrowser();
        captureMailOAuthReturns({ app: fakeApp({ launchUrl: url, retained: [url] }), browser, isNative: () => true });
        await redeemPendingMailOAuth(api.complete); // UsersApp mount
        await settle(); await settle();
        assert.deepEqual(api.calls, [flow], `${label}: cold start completes once`);
        assert.deepEqual(results(), [{ provider, ok: true }], `${label}: one success is reported`);
        assert.deepEqual(takeMailOAuthOutcome(), { provider, ok: true });
        assert.ok(browser.closes >= 1, `${label}: the in-app browser is closed`);
      }

      // 7, 4. App already open: appUrlOpen fires (twice on some resumes).
      {
        const api = backend();
        freshSession(api);
        const app = fakeApp();
        captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => true });
        const { flow, url } = authorized(provider, scheme);
        app.open(url);
        app.open(url);
        await settle(); await settle();
        app.open(url); // late duplicate after the first completion finished
        await settle(); await settle();
        assert.deepEqual(api.calls, [flow], `${label}: duplicate appUrlOpen completes once`);
        assert.equal(results().length, 1, `${label}: duplicates are silent`);
      }

      // 8, 5. Background resume + React remount (StrictMode mounts effects twice).
      {
        const api = backend();
        freshSession(api);
        const app = fakeApp();
        const browser = fakeBrowser();
        captureMailOAuthReturns({ app, browser, isNative: () => true });
        captureMailOAuthReturns({ app, browser, isNative: () => true }); // remount: no second listener
        const { flow, url } = authorized(provider, scheme);
        app.open(url);
        await Promise.all([redeemPendingMailOAuth(api.complete), redeemPendingMailOAuth(api.complete)]);
        await settle(); await settle();
        assert.deepEqual(api.calls, [flow], `${label}: remount and resume complete once`);
        assert.equal(browser.closes, 1, `${label}: one listener per app`);
      }

      // Process restart: Android recreates the activity with its launch intent and
      // iOS keeps lastURL; the new WebView must not redeem the old link again.
      {
        const api = backend();
        freshSession(api);
        const { flow, url } = authorized(provider, scheme);
        captureMailOAuthReturns({ app: fakeApp({ launchUrl: url, retained: [url] }), browser: fakeBrowser(), isNative: () => true });
        await settle(); await settle();
        freshSession(api); // sessionStorage is lost with the process
        captureMailOAuthReturns({ app: fakeApp({ launchUrl: url, retained: [url] }), browser: fakeBrowser(), isNative: () => true });
        await redeemPendingMailOAuth(api.complete);
        await settle(); await settle();
        assert.deepEqual(api.calls, [flow], `${label}: a stale launch URL is ignored after restart`);
        assert.deepEqual(results(), [], `${label}: and shows nothing`);
      }

      // 9. The completion request fails on the network: kept and retried safely.
      {
        const api = backend();
        freshSession(api);
        const app = fakeApp();
        captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => true });
        const { flow, url } = authorized(provider, scheme);
        api.failNextWith(Object.assign(new Error("Network"), { status: 0 }));
        app.open(url);
        await settle(); await settle();
        assert.deepEqual(results(), [{ provider, ok: false, code: "completion_pending" }], `${label}: network failure is recoverable`);
        await redeemPendingMailOAuth(api.complete); // back online / resumed
        assert.deepEqual(api.calls, [flow, flow]);
        assert.deepEqual(results().at(-1), { provider, ok: true }, `${label}: retry connects`);
        app.open(url);
        await settle(); await settle();
        assert.deepEqual(api.calls, [flow, flow], `${label}: no third attempt after success`);
      }

      // 10, 12-15. Backend rejection (reused/expired/wrong code, other account): definitive.
      {
        const api = backend();
        freshSession(api);
        const app = fakeApp();
        captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => true });
        const { flow, url } = authorized(provider, scheme);
        api.failNextWith(Object.assign(new Error("Esta autorización de correo no pertenece a tu cuenta DINCR."), { status: 403 }));
        app.open(url);
        await settle(); await settle();
        const [rejected] = results();
        assert.equal(rejected.code, "completion_failed");
        assert.match(rejected.message, /no pertenece a tu cuenta/);
        app.open(url);
        await redeemPendingMailOAuth(api.complete);
        assert.deepEqual(api.calls, [flow], `${label}: a rejected completion is not retried`);
      }

      // The browser delivered the provider redirect twice: the backend reports the
      // replay as already_processed. After a success it is silent; otherwise explained.
      {
        const api = backend();
        freshSession(api);
        window.localStorage = memoryStorage(); // no recent connection on this device
        const app = fakeApp();
        captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => true });
        app.open(returnUrl(provider, "already_processed", {}, scheme));
        await settle(); await settle();
        assert.deepEqual(results(), [{ provider, ok: false, code: "already_processed" }], `${label}: replay without a success is explained`);
        const { url } = authorized(provider, scheme);
        app.open(url);
        await settle(); await settle();
        app.open(returnUrl(provider, "already_processed", {}, scheme));
        await settle(); await settle();
        assert.deepEqual(results().slice(1), [{ provider, ok: true }], `${label}: replay after success is silent`);
      }

      // Provider errors are reported without calling the API; each response once.
      {
        const api = backend();
        freshSession(api);
        const app = fakeApp();
        captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => true });
        const denied = returnUrl(provider, "denied", {}, scheme);
        app.open(denied);
        app.open(denied);
        await settle(); await settle();
        app.open(returnUrl(provider, "denied", {}, scheme)); // a new, genuine denial
        await settle(); await settle();
        assert.deepEqual(results().map((item) => item.code), ["denied", "denied"], `${label}: each denial shown once`);
        assert.deepEqual(api.calls, []);
      }
    }
  }
}

// Web builds never register native listeners.
{
  const app = fakeApp();
  let listened = false;
  app.addListener = () => { listened = true; };
  captureMailOAuthReturns({ app, browser: fakeBrowser(), isNative: () => false });
  assert.equal(listened, false);
}

// Only identifiers are persisted; completion codes never reach localStorage.
assert.doesNotMatch([...window.localStorage.store.values()].join(" "), /code-/);

// Wiring: UsersApp redeems for every DINCR session (and retries on resume/online);
// the screen only reports the outcome.
const usersApp = readFileSync(new URL("../src/users/UsersApp.jsx", import.meta.url), "utf8");
const gmail = readFileSync(new URL("../src/users/pages/GmailAutomation.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/users/services/jarvisApi.js", import.meta.url), "utf8");
assert.match(usersApp, /captureMailOAuthReturns\(\)/);
assert.match(usersApp, /redeemPendingMailOAuth\(completeVipMailConnection\)/);
assert.match(usersApp, /addEventListener\("online", redeem\)/);
assert.match(usersApp, /addEventListener\("visibilitychange", redeemWhenVisible\)/);
assert.match(api, /completeVipMailConnection = \(flow, completion\) => json\("\/user-product\/vip\/mail\/oauth\/complete", "POST"/);
assert.doesNotMatch(gmail, /appUrlOpen/, "only one place may redeem a single-use completion");
assert.match(gmail, /takeMailOAuthOutcome\(\)/);
for (const code of ["already_processed", "completion_pending", "invalid_state"]) assert.match(gmail, new RegExp(`${code}: \\[`));

// 19-20. Android and iOS accept the same mail return schemes; DINCR is canonical.
const manifest = readFileSync(new URL("../android/app/src/main/AndroidManifest.xml", import.meta.url), "utf8");
const plist = readFileSync(new URL("../ios-dincr/App/App/Info.plist", import.meta.url), "utf8");
for (const scheme of ["com.dincr.app", "com.finva.app"]) {
  assert.match(manifest, new RegExp(`android:scheme="${scheme.replaceAll(".", "\\.")}" android:host="gmail"`), `Android receives ${scheme} mail returns`);
  assert.match(plist, new RegExp(`<string>${scheme.replaceAll(".", "\\.")}</string>`), `iOS receives ${scheme} mail returns`);
}

// 21. Before the provider opens, the user chooses the history to import (v1: this
// month or this year, no custom date); the choice is sent to the server-side flow.
assert.match(api, /connectVipGmail = \(importScope\) => json\("\/user-product\/vip\/gmail\/connect", "POST", \{ import_scope: importScope \}\)/);
assert.match(api, /connectVipMicrosoftMail = \(importScope\) => json\("\/user-product\/vip\/mail\/microsoft\/connect", "POST", \{ import_scope: importScope \}\)/);
const importOptions = gmail.slice(gmail.indexOf("const IMPORT_OPTIONS"), gmail.indexOf("];", gmail.indexOf("const IMPORT_OPTIONS")));
assert.deepEqual([...importOptions.matchAll(/scope: "(\w+)"/g)].map((match) => match[1]), ["current_month", "current_year"]);
assert.doesNotMatch(gmail, /type="date"[^>]*mail-history|custom_date/, "no custom date in v1");
const connectStep = gmail.slice(gmail.indexOf("const connect = (provider) =>"), gmail.indexOf("const startConnection"));
assert.match(connectStep, /setHistoryChoice\(\{ provider, scope: "current_month" \}\)/);
assert.doesNotMatch(connectStep, /Browser\.open|connectVipGmail|connectVipMicrosoftMail/, "the provider opens only after the choice");
assert.match(gmail, /connectVipMicrosoftMail\(scope\) : connectVipGmail\(scope\)/);
assert.match(gmail, /DINCR buscará correos bancarios dentro del período seleccionado\. Los movimientos detectados aparecerán en Cuentas/);
assert.match(gmail, /Si tu banco no envía estados de cuenta, DINCR solo podrá detectar la información presente en los correos bancarios que reciba\./);

console.log("DINCR mail OAuth returns are completed once on Android and iOS, for Gmail and Outlook.");
