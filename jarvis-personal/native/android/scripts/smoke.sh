#!/usr/bin/env bash
# Android smoke test on a connected emulator/device, using fixture data (no backend, no account).
# Launches each fixture scenario and asserts on the rendered accessibility tree (uiautomator),
# in the device language (English or Spanish copy both accepted).
#
#   ./gradlew :app:assembleDebug && scripts/smoke.sh
set -euo pipefail

ADB="${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb"
APK="$(dirname "$0")/../app/build/outputs/apk/debug/app-debug.apk"
PKG="com.dincr.app.nativedev"
failures=0

"$ADB" install -r "$APK" >/dev/null

screen() {
  sleep "${1:-4}"
  "$ADB" shell uiautomator dump /sdcard/dincr-ui.xml >/dev/null 2>&1
  "$ADB" shell cat /sdcard/dincr-ui.xml
}

launch() { # scenario skipLogin
  "$ADB" shell am force-stop "$PKG"
  "$ADB" shell am start -W -n "$PKG/com.dincr.app.MainActivity" --es dincrFixtures "$1" --ez dincrSkipLogin "$2" >/dev/null
}

expect() { # name ui pattern...
  local name="$1" ui="$2"; shift 2
  for pattern in "$@"; do
    if ! grep -qE "$pattern" <<<"$ui"; then
      echo "FAIL $name: missing /$pattern/"; failures=$((failures + 1)); return
    fi
  done
  echo "ok   $name"
}

launch POPULATED false
ui="$(screen)"
expect "login shows Google sign-in and the demo notice" "$ui" 'Continu(e|ar) (with|con) Google' 'Demo mode|Modo de demostraci'
if grep -q 'Apple' <<<"$ui"; then echo "FAIL login: Apple sign-in must not appear on Android"; failures=$((failures + 1)); else echo "ok   login has no Apple button on Android"; fi

launch POPULATED true
expect "home key figure, signed amounts, spoken labels" "$(screen)" \
  'Available this month|Disponible este mes' '₡257\.550' '\+₡865\.000' '−₡512\.450' \
  'content-desc="(plus|más) 865000 colones"' 'Income and expenses|Ingresos y gastos'

launch EMPTY true
expect "empty account teaches the first action" "$(screen)" 'No transactions yet|Todavía no hay movimientos' 'Add transaction|Agregar movimiento'

launch FAILING true
expect "failing backend offers recovery and sign-out" "$(screen)" "load your account|cargar tu cuenta" 'Try again|Intentar de nuevo' 'Sign out|Cerrar sesi'

launch NEW_USER true
expect "new user lands in profile setup" "$(screen)" 'What should we call you|llamemos' 'Continue|Continuar'

"$ADB" shell am force-stop "$PKG"
if [ "$failures" -gt 0 ]; then echo "$failures smoke check(s) failed"; exit 1; fi
echo "android smoke: all checks passed"
