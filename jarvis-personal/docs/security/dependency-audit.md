# Frontend dependency audit (npm)

Scope: `jarvis-personal/frontend` (mobile app, Capacitor tooling and the `dincr.com` landing build). The root `jarvis-personal/package.json` audits clean.

## Starting point

`npm ci` reported 8 advisories (4 moderate, 4 high). `npm audit --omit=dev` reported **0**: every advisory sits in a build/dev-only tree. None of the affected packages is bundled into the Android/iOS web assets or the landing HTML.

| Package | Was | Severity | Path | Kind | Advisory |
|---|---|---|---|---|---|
| brace-expansion | 5.0.6 | high | eslint → minimatch | dev (lint) | GHSA-3jxr-9vmj-r5cp, GHSA-mh99-v99m-4gvg, GHSA-rgw5-rvv9-x895 (ReDoS/OOM on crafted globs) |
| browserslist | 4.28.2 | high | eslint-plugin-react-hooks → @babel/core → helper-compilation-targets | dev (lint) | GHSA-c83g-rgw3-j3cx, GHSA-73wf-gq98-2v4g (untrusted queries/stats files) |
| nanoid | 3.3.12 | high | vite → postcss | build | GHSA-28wg-ghj8-5hjv, GHSA-2v37-7h3g-55p8 (negative/zero size loops) |
| postcss | 8.5.15 | high | vite | build | GHSA-fxqj-rqcc-2cmp, GHSA-r28c-9q8g-f849 (attacker `sourceMappingURL` reads `.map` files) |
| baseline-browser-mapping | 2.10.33 | moderate | browserslist | dev (lint) | GHSA-w5vr-8v7q-w6rv (crash on invalid input) |
| uuid | 7.0.3 | moderate | @capacitor/cli → xcode | dev (native sync tooling) | GHSA-w5hq-g745-h8pq |
| xcode | 3.0.1 | moderate | @capacitor/cli | dev | via uuid |
| @capacitor/cli | 8.5.1 | moderate | direct devDependency | dev | via xcode |

Reachability: every vulnerable path requires an attacker to control input to a local developer/CI tool (glob patterns, browserslist config, CSS source maps, generator sizes). DINCR feeds these tools only repository-controlled files. Real risk was low, but four of them had in-range fixes.

## Fixed (lockfile only, no `package.json` range changes)

`npm update brace-expansion browserslist baseline-browser-mapping nanoid postcss`:
brace-expansion 5.0.12, browserslist 4.29.0, baseline-browser-mapping 2.11.25, nanoid 3.3.19, postcss 8.5.28. Browserslist's data packages moved with it (caniuse-lite, electron-to-chromium, node-releases, update-browserslist-db). All are semver-compatible within the ranges their parents already declare.

## Accepted residual: uuid / xcode / @capacitor/cli (3 moderate)

- `xcode@3.0.1` (latest) pins `uuid@^7`; every `@capacitor/cli` 8.5.x and 9.0 pre-release depends on it. npm's suggested "fix" is a **downgrade** to `@capacitor/cli@8.4.3`, flagged breaking, and would desync the CLI from `@capacitor/core`/`android`/`ios` 8.5.x.
- The advisory affects `uuid` v3/v5/v6 (v3/v5 in uuid 7) **when a caller passes its own output buffer**. `xcode` only calls `uuid.v4()` with no arguments (`lib/pbxProject.js`, `generateUuid`), so the vulnerable code is not reached.
- The package runs only on a developer machine or CI during `cap sync ios` to edit the Xcode project; it is never shipped in the app.
- Not overridden with `overrides.uuid`: forcing a major bump under a third-party tool trades a non-reachable advisory for an untested native-sync path.
- Revisit when `@capacitor/cli` or `xcode` moves to `uuid >= 11.1.1`.

## Validation

Note: brace-expansion 5.0.12 requires Node 20+. CI uses Node 22; local development must also use Node 20 or newer.


`npm ci`, `npm run build`, `npx eslint .` (0 errors; the 14 warnings predate this change), `npm run build:landing`, and every `npm run test:*` script pass. `npm audit --omit=dev` stays at 0; the full `npm audit` goes from 8 to 3 moderate, all explained above.

Recommended release gate: `npm audit --omit=dev --audit-level=high` must be 0. Dev-tool advisories get triaged the same way as here, not with `npm audit fix --force`.
