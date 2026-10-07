# DINCR frontend — surfaces (UX-10/11)

| Surface | What it is | Where it lives | Deploy |
|---|---|---|---|
| **Commercial app** | DINCR for users | `native/ios`, `native/android` (SwiftUI, Compose) | App Store / Google Play |
| **Internal lab** | This web build: development, diagnosis, Owner/JARVIS tools | `src/`, `index.html` (`npm run build` → `dist/`) | Vercel, `noindex` (`vercel.json`) — never the commercial app |
| **Public landing** | dincr.com: marketing, legal, support | `landing/` (`npm run build:landing` → `landing-dist/`) | Cloudflare Worker `dincr` (`wrangler.jsonc`) |

Rules (`npm run test:surfaces`, in CI):
- the landing and the native apps never link to the lab;
- the lab is never indexable (Vercel `X-Robots-Tag`, robots meta) and its install name says it is the lab;
- the landing deploy serves only `landing-dist/`, never `dist/`.

The web build also feeds the older Capacitor shells (`android/`, `ios-dincr/`); keep it working for them.

---

# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
