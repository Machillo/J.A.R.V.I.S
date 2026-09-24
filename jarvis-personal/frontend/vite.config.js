import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

const androidBuild = readFileSync(new URL('./android/app/build.gradle', import.meta.url), 'utf8')
const nativeVersion = androidBuild.match(/versionName\s+["']([^"']+)["']/)?.[1] || 'dev'

const OWNER_CHART_DEPS = /node_modules[/\\](?:recharts|victory-vendor|d3-[a-z-]+|internmap|reselect|react-redux|immer|eventemitter3|es-toolkit|decimal\.js-light|@reduxjs|redux-thunk|redux|@standard-schema|tiny-invariant|use-sync-external-store|clsx)[/\\]/

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const supabaseUrl = env.VITE_SUPABASE_URL || env.SUPABASE_URL || ''
  const supabaseAnonKey = env.VITE_SUPABASE_ANON_KEY || env.SUPABASE_ANON_KEY || ''

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
    },
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(supabaseUrl),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(supabaseAnonKey),
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(env.VITE_APP_VERSION || nativeVersion),
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (id.includes('@supabase')) return 'supabase'
            // recharts and its dependency tree are only used by Owner screens: leave them to the
            // lazily loaded Owner chunk (shared modules are split out automatically).
            if (OWNER_CHART_DEPS.test(id)) return undefined
            if (id.includes('react')) return 'react'
            return 'vendor'
          },
        },
      },
    },
  }
})
