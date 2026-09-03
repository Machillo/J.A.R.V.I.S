import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const supabaseUrl = env.VITE_SUPABASE_URL || env.SUPABASE_URL || ''
  const supabaseAnonKey = env.VITE_SUPABASE_ANON_KEY || env.SUPABASE_ANON_KEY || ''

  return {
    plugins: [react()],
    build: {
      // Lightning CSS can fail on Vercel when its cached native binary does not
      // match the build image. esbuild keeps production CSS minified and makes
      // the build deterministic across local and Vercel environments.
      cssMinify: 'esbuild',
    },
    server: {
      port: 5173,
      strictPort: true,
    },
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(supabaseUrl),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(supabaseAnonKey),
    },
  }
})
