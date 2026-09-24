"""Firebase may distribute DINCR test builds. Firebase must not observe DINCR users.

PostHog is DINCR's only analytics/observability system. Firebase is kept
temporarily for Firebase App Distribution, which uploads a built APK (console,
Firebase CLI or its Gradle upload plugin) and needs nothing inside the app. This
guard fails if a Firebase runtime SDK, analytics/crash plugin or telemetry call
comes back. Only build-time distribution tooling is allowlisted.
"""
import json
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Build-time App Distribution tooling (uploads the APK; never runs on a device).
ALLOWED = (
    re.compile(r"com\.google\.firebase\.appdistribution['\"]"),    # Gradle upload plugin id
    re.compile(r"com\.google\.firebase:firebase-appdistribution-gradle"),  # its classpath
)
FORBIDDEN_NPM = re.compile(r"^(firebase|@firebase/.*|@capacitor-firebase/.*|@react-native-firebase/.*)$")
ALLOWED_NPM = frozenset({"firebase-tools"})  # Firebase CLI: `firebase appdistribution:distribute`
FORBIDDEN_BUILD = re.compile(
    r"com\.google\.firebase[:.]|com\.google\.gms[:.]google-services|google-services['\"]|crashlytics|"
    r"play-services-measurement|capacitor-firebase|firebase-bom", re.I,
)
FORBIDDEN_NATIVE = re.compile(
    r"com\.google\.firebase|import\s+Firebase|FirebaseApp|Crashlytics|FirebaseAnalytics|"
    r"firebase_analytics_collection|firebase_crashlytics_collection|google_app_id", re.I,
)
FORBIDDEN_JS = re.compile(
    r"from\s+[\"'](firebase(/[^\"']*)?|@firebase/[^\"']*|@capacitor-firebase/[^\"']*)[\"']|"
    r"FirebaseAnalytics|FirebaseCrashlytics|\bsetUserId\s*\(|\brecordException\s*\(|\blogEvent\s*\(|"
    r"setCrashlyticsCollectionEnabled|setAnalyticsCollectionEnabled",
)


def _strip_allowed(text: str) -> str:
    for pattern in ALLOWED:
        text = pattern.sub("", text)
    return text


def npm_violations(root: Path) -> list[str]:
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    names = {**package.get("dependencies", {}), **package.get("devDependencies", {}), **package.get("optionalDependencies", {})}
    return [name for name in names if FORBIDDEN_NPM.match(name) and name not in ALLOWED_NPM]


def _files(root: Path, patterns: tuple[str, ...]):
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and "node_modules" not in path.parts and "build" not in path.parts and ".gradle" not in path.parts:
                yield path


def build_violations(root: Path) -> list[str]:
    found = []
    for path in _files(root, ("android/**/*.gradle", "android/**/*.gradle.kts", "android/**/*.properties")):
        text = _strip_allowed(path.read_text(encoding="utf-8", errors="ignore"))
        found += [f"{path.relative_to(root)}: {m.group(0)}" for m in FORBIDDEN_BUILD.finditer(text)]
    return found


def native_violations(root: Path) -> list[str]:
    found = []
    patterns = ("android/app/src/**/*.java", "android/app/src/**/*.kt", "android/app/src/**/AndroidManifest.xml",
                "android/app/src/**/res/values/*.xml", "ios*/**/*.swift", "ios*/**/Podfile", "ios*/**/Package.swift",
                "ios*/**/*.plist")
    for path in _files(root, patterns):
        text = path.read_text(encoding="utf-8", errors="ignore")
        found += [f"{path.relative_to(root)}: {m.group(0)}" for m in FORBIDDEN_NATIVE.finditer(text)]
    return found


def js_violations(root: Path) -> list[str]:
    found = []
    for path in _files(root, ("src/**/*.js", "src/**/*.jsx", "src/**/*.ts", "src/**/*.tsx", "vite.config.js")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        found += [f"{path.relative_to(root)}: {m.group(0)}" for m in FORBIDDEN_JS.finditer(text)]
    return found


# --- The real repository ---------------------------------------------------------

def test_no_firebase_runtime_sdk_or_analytics_package():
    assert npm_violations(FRONTEND) == []


def test_android_build_has_no_firebase_sdk_crashlytics_or_google_services():
    assert build_violations(FRONTEND) == []


def test_native_code_never_initializes_or_calls_firebase():
    assert native_violations(FRONTEND) == []


def test_app_code_sends_nothing_to_firebase():
    assert js_violations(FRONTEND) == []


def test_telemetry_facade_only_reaches_posthog():
    telemetry = (FRONTEND / "src" / "lib" / "telemetry.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from \"([^\"]+)\";", telemetry, re.M)
    assert imports == ["@capacitor/core", "./productAnalytics"]


def test_google_services_json_stays_out_of_git_and_the_build():
    assert re.search(r"^google-services\.json$", (FRONTEND / "android" / ".gitignore").read_text(encoding="utf-8"), re.M)
    for path in _files(FRONTEND, ("android/**/*.gradle",)):
        assert not re.search(r"file\(\s*['\"]google-services\.json", path.read_text(encoding="utf-8")), path


# --- Mutation checks: reintroducing Firebase telemetry fails the guard -------------

def _synthetic(tmp_path: Path, files: dict[str, str]) -> Path:
    base = {"package.json": json.dumps({"dependencies": {"@capacitor/core": "^8"}}), "android/app/build.gradle": "apply plugin: 'com.android.application'\n"}
    for name, text in {**base, **files}.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("package", ["@capacitor-firebase/analytics", "@capacitor-firebase/crashlytics", "firebase", "@firebase/analytics"])
def test_guard_rejects_firebase_npm_packages(tmp_path, package):
    root = _synthetic(tmp_path, {"package.json": json.dumps({"dependencies": {package: "^1"}})})
    assert npm_violations(root) == [package]


def test_guard_allows_the_firebase_cli_for_distribution(tmp_path):
    root = _synthetic(tmp_path, {"package.json": json.dumps({"devDependencies": {"firebase-tools": "^14"}})})
    assert npm_violations(root) == []


@pytest.mark.parametrize("line", [
    'implementation "com.google.firebase:firebase-analytics:22.1.0"',
    'implementation platform("com.google.firebase:firebase-bom:33.0.0")',
    "classpath 'com.google.firebase:firebase-crashlytics-gradle:2.9.9'",
    "apply plugin: 'com.google.firebase.crashlytics'",
    "classpath 'com.google.gms:google-services:4.4.4'",
    "apply plugin: 'com.google.gms.google-services'",
    "implementation project(':capacitor-firebase-analytics')",
    'debugImplementation "com.google.firebase:firebase-appdistribution:16.0.0-beta20"',  # in-app runtime SDK
])
def test_guard_rejects_firebase_runtime_in_gradle(tmp_path, line):
    root = _synthetic(tmp_path, {"android/app/build.gradle": f"apply plugin: 'com.android.application'\n{line}\n"})
    assert build_violations(root)


def test_guard_allows_the_app_distribution_upload_plugin(tmp_path):
    root = _synthetic(tmp_path, {
        "android/build.gradle": "classpath 'com.google.firebase:firebase-appdistribution-gradle:5.1.1'\n",
        "android/app/build.gradle": "apply plugin: 'com.android.application'\napply plugin: 'com.google.firebase.appdistribution'\n",
    })
    assert build_violations(root) == []


@pytest.mark.parametrize(("name", "text"), [
    ("android/app/src/main/java/com/dincr/app/MainActivity.java", "import com.google.firebase.FirebaseApp;"),
    ("android/app/src/main/AndroidManifest.xml", '<meta-data android:name="firebase_analytics_collection_enabled" />'),
    ("ios-dincr/App/App/AppDelegate.swift", "import FirebaseCore\nFirebaseApp.configure()"),
])
def test_guard_rejects_native_firebase(tmp_path, name, text):
    assert native_violations(_synthetic(tmp_path, {name: text}))


@pytest.mark.parametrize("line", [
    'import { FirebaseAnalytics } from "@capacitor-firebase/analytics";',
    'import { FirebaseCrashlytics } from "@capacitor-firebase/crashlytics";',
    'import { getAnalytics, logEvent } from "firebase/analytics";',
    "FirebaseAnalytics.setUserId({ userId });",
    "FirebaseCrashlytics.recordException({ message });",
])
def test_guard_rejects_firebase_telemetry_in_app_code(tmp_path, line):
    assert js_violations(_synthetic(tmp_path, {"src/lib/telemetry.js": line}))
