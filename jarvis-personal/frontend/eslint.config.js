import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Generated output is copied/compiled from Vite and Capacitor dependencies.
  // Lint source files only; never lint Android build intermediates or packaged assets.
  globalIgnores([
    'dist/**',
    'android/app/src/main/assets/public/**',
    'android/app/build/**',
    'android/build/**',
    'android/.gradle/**',
    'ios-dincr/App/App/public/**',
    'ios-dincr/DerivedData/**',
    'ios-jarvis/App/App/public/**',
    'ios-jarvis/DerivedData/**',
  ]),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Existing screens intentionally load remote data when they mount.
      // Refactor those effects incrementally instead of blocking security releases.
      'react-hooks/set-state-in-effect': 'off',
      'no-unused-vars': 'warn',
    },
  },
  {
    files: ['public/sw.js'],
    languageOptions: { globals: globals.serviceworker },
  },
  {
    files: ['vite.config.js'],
    languageOptions: { globals: globals.node },
  },
])
