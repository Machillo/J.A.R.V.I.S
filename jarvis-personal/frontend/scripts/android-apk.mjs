// Builds a local DEBUG APK of DINCR: checks prerequisites, builds the web app,
// syncs Capacitor and runs Gradle. Release/AAB builds are out of scope on purpose:
// they need signing keys that never live in this repository.
//
//   npm run android:apk            web build + cap sync + assembleDebug
//   npm run android:apk -- --check only validate prerequisites
//
// Optional environment:
//   JAVA_HOME             JDK 17+ (falls back to Android Studio's bundled JBR)
//   ANDROID_HOME          Android SDK (falls back to local.properties / default paths)
//   GOOGLE_SERVICES_JSON  path to a local google-services.json to copy into android/app
//   DINCR_ANDROID_BUILD_DIR  where Gradle runs when the repo lives in OneDrive (see below)
//
// OneDrive: Gradle cannot snapshot OneDrive placeholder files ("Cannot snapshot …: not a
// regular file"). When the repo is inside OneDrive on Windows, the Gradle step runs on an
// incremental robocopy mirror of android/ + node_modules/ outside OneDrive and the APK is
// copied back. Pass --in-place to skip the mirror.
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir, platform } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const androidDir = join(root, "android");
const apkPath = join(androidDir, "app", "build", "outputs", "apk", "debug", "app-debug.apk");
const APP_ID = "com.dincr.app";
const MIN_JAVA = 17;
const isWindows = platform() === "win32";
const checkOnly = process.argv.includes("--check");
const inPlace = process.argv.includes("--in-place");
const oneDriveRoots = [process.env.OneDrive, process.env.OneDriveConsumer, process.env.OneDriveCommercial].filter(Boolean);
const inOneDrive = isWindows && (oneDriveRoots.some((dir) => root.toLowerCase().startsWith(dir.toLowerCase())) || /[\\/]OneDrive[^\\/]*[\\/]/i.test(root));
const mirrorRoot = process.env.DINCR_ANDROID_BUILD_DIR || (process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "DINCR", "android-build"));
const useMirror = inOneDrive && !inPlace;

const problems = [];
const notes = [];
const fail = (message) => problems.push(message);

function javaMajor(javaHome) {
  const bin = join(javaHome, "bin", isWindows ? "java.exe" : "java");
  if (!existsSync(bin)) return null;
  const out = spawnSync(bin, ["-version"], { encoding: "utf8" });
  const match = `${out.stderr}${out.stdout}`.match(/version "(\d+)(?:\.(\d+))?/);
  if (!match) return null;
  return match[1] === "1" ? Number(match[2]) : Number(match[1]);
}

function findJava() {
  const candidates = [
    process.env.JAVA_HOME,
    isWindows && "C:\\Program Files\\Android\\Android Studio\\jbr",
    platform() === "darwin" && "/Applications/Android Studio.app/Contents/jbr/Contents/Home",
    platform() === "linux" && "/opt/android-studio/jbr",
  ].filter(Boolean).map((path) => path.replace(/[\\/]+$/, ""));
  for (const home of candidates) {
    const major = javaMajor(home);
    if (major >= MIN_JAVA) return { home, major };
    if (home === process.env.JAVA_HOME?.replace(/[\\/]+$/, "")) {
      notes.push(major ? `JAVA_HOME apunta a Java ${major}; se necesita ${MIN_JAVA}+. Probando el JDK de Android Studio.` : "JAVA_HOME no contiene bin/java. Probando el JDK de Android Studio.");
    }
  }
  return null;
}

function findSdk() {
  const fromLocal = (() => {
    const file = join(androidDir, "local.properties");
    if (!existsSync(file)) return null;
    const line = readFileSync(file, "utf8").split(/\r?\n/).find((l) => l.startsWith("sdk.dir="));
    return line ? line.slice("sdk.dir=".length).replace(/\\\\/g, "\\").replace(/\\:/g, ":") : null;
  })();
  // Same priority as Gradle: local.properties sdk.dir wins over environment variables.
  const candidates = [
    fromLocal,
    process.env.ANDROID_HOME,
    process.env.ANDROID_SDK_ROOT,
    isWindows && process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "Android", "Sdk"),
    platform() === "darwin" && join(homedir(), "Library", "Android", "sdk"),
    platform() === "linux" && join(homedir(), "Android", "Sdk"),
  ].filter(Boolean);
  return candidates.find((path) => existsSync(join(path, "platforms"))) || null;
}

function readEnvKeys() {
  // Only key names and whether they look usable are inspected; values are never printed.
  const env = {};
  for (const name of [".env", ".env.local", ".env.production", ".env.production.local"]) {
    const file = join(root, name);
    if (!existsSync(file)) continue;
    for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
      const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (match) env[match[1]] = match[2].replace(/^["']|["']$/g, "");
    }
  }
  return { ...env, ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("VITE_") || key.startsWith("SUPABASE_"))) };
}

function checkGoogleServices() {
  const target = join(androidDir, "app", "google-services.json");
  const source = process.env.GOOGLE_SERVICES_JSON && resolve(process.env.GOOGLE_SERVICES_JSON);
  if (source && !existsSync(source)) return fail(`GOOGLE_SERVICES_JSON apunta a un archivo inexistente: ${source}`);
  const file = source || target;
  if (!existsSync(file)) {
    notes.push("Sin android/app/google-services.json: el APK se genera, pero Firebase Analytics/Crashlytics quedan desactivados. Definí GOOGLE_SERVICES_JSON=<ruta> para incluirlo (nunca se commitea).");
    return;
  }
  let packages = [];
  try {
    packages = JSON.parse(readFileSync(file, "utf8")).client.map((c) => c.client_info.android_client_info.package_name);
  } catch {
    return fail(`google-services.json no es válido: ${file}`);
  }
  if (!packages.includes(APP_ID)) return fail(`google-services.json no incluye el paquete ${APP_ID}.`);
  if (source && source !== target) {
    if (!checkOnly) copyFileSync(source, target);
    notes.push(checkOnly ? "google-services.json válido; se copiará a android/app al compilar." : "google-services.json copiado a android/app (ignorado por git).");
  }
}

function mirror(from, to) {
  // /MIR deletes stale sources (e.g. after a plugin upgrade); /XD keeps Gradle outputs,
  // since excluded directories are neither copied nor purged.
  // robocopy exit codes 0-7 mean success (files copied/skipped); 8+ are failures.
  const args = [from, to, "/MIR", "/XD", "build", ".gradle", ".kotlin", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1"];
  const result = spawnSync("robocopy", args, { stdio: "inherit" });
  if (result.error) throw result.error;
  return result.status !== null && result.status < 8;
}

function run(command, args, env) {
  const result = spawnSync(command, args, { cwd: env.cwd || root, stdio: "inherit", shell: isWindows, env: env.vars });
  if (result.error) throw result.error;
  return result.status === 0;
}

// --- prerequisites -------------------------------------------------------
const nodeMajor = Number(process.versions.node.split(".")[0]);
if (nodeMajor < 20) fail(`Node ${process.versions.node}: se necesita Node 20 o superior.`);

const java = findJava();
if (!java) fail(`No se encontró un JDK ${MIN_JAVA}+. Instalá Android Studio o un JDK ${MIN_JAVA}/21 y definí JAVA_HOME.`);

const sdk = findSdk();
if (!sdk) fail("No se encontró el Android SDK. Instalalo desde Android Studio o definí ANDROID_HOME.");

if (!existsSync(join(root, "node_modules", "@capacitor", "cli"))) fail("Faltan dependencias: ejecutá `npm ci` en jarvis-personal/frontend.");

const env = readEnvKeys();
if (!(env.VITE_SUPABASE_URL || env.SUPABASE_URL) || !(env.VITE_SUPABASE_ANON_KEY || env.SUPABASE_ANON_KEY)) {
  fail("Faltan VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY en .env (ver .env.example).");
}
// Native builds ignore VITE_API_URL (src/lib/apiUrl.js): they call VITE_NATIVE_API_URL or production.
if (!env.VITE_NATIVE_API_URL) {
  notes.push("Backend del APK: producción (VITE_NATIVE_API_URL no está definido).");
} else if (/localhost|127\.0\.0\.1/.test(env.VITE_NATIVE_API_URL)) {
  notes.push("VITE_NATIVE_API_URL apunta a localhost: un teléfono físico no podrá alcanzar ese backend.");
} else {
  notes.push("Backend del APK: VITE_NATIVE_API_URL (no producción).");
}

if (!env.VITE_POSTHOG_KEY) notes.push("PostHog desactivado en este APK (falta VITE_POSTHOG_KEY): no sirve para la prueba teléfono → PostHog.");

const capacitorConfig = JSON.parse(readFileSync(join(root, "capacitor.config.json"), "utf8"));
if (capacitorConfig.appId !== APP_ID) fail(`capacitor.config.json tiene appId ${capacitorConfig.appId}; se esperaba ${APP_ID}.`);

checkGoogleServices();

for (const note of notes) console.warn(`! ${note}`);
if (problems.length) {
  console.error("\nNo se puede generar el APK:");
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
if (useMirror && !mirrorRoot) {
  console.error("\nEl repo está en OneDrive y no se pudo determinar una carpeta de build fuera de OneDrive. Definí DINCR_ANDROID_BUILD_DIR.");
  process.exit(1);
}
console.log(`✓ Node ${process.versions.node} · Java ${java.major} (${java.home}) · Android SDK ${sdk}`);
if (useMirror) console.log(`✓ Repo en OneDrive: Gradle correrá en ${mirrorRoot}`);
if (checkOnly) process.exit(0);

// --- build ---------------------------------------------------------------
const vars = { ...process.env, JAVA_HOME: java.home, ANDROID_HOME: sdk, ANDROID_SDK_ROOT: sdk, VITE_NATIVE_APP_ID: APP_ID };
const gradleDir = useMirror ? join(mirrorRoot, "android") : androidDir;
const steps = [
  ["Build web", () => run("npm", ["run", "build"], { cwd: root, vars })],
  ["Capacitor sync", () => run("npx", ["cap", "sync", "android"], { cwd: root, vars })],
  ...(useMirror ? [["Copia fuera de OneDrive", () =>
    mirror(join(root, "node_modules"), join(mirrorRoot, "node_modules"))
    && mirror(androidDir, gradleDir)]] : []),
  // Absolute, quoted path: cmd.exe may not search the working directory for gradlew.bat.
  ["Gradle assembleDebug", () => (isWindows
    ? run(`"${join(gradleDir, "gradlew.bat")}"`, ["assembleDebug"], { cwd: gradleDir, vars })
    // gradlew is committed without the executable bit, so invoke it through sh.
    : run("sh", ["gradlew", "assembleDebug"], { cwd: gradleDir, vars }))],
];
for (const [label, step] of steps) {
  console.log(`\n▶ ${label}`);
  if (!step()) {
    console.error(`\n✗ Falló: ${label}. Revisá la salida de arriba.`);
    process.exit(1);
  }
}
if (useMirror) {
  const builtApk = join(gradleDir, "app", "build", "outputs", "apk", "debug", "app-debug.apk");
  if (!existsSync(builtApk)) {
    console.error(`\n✗ Gradle terminó pero no existe ${builtApk}.`);
    process.exit(1);
  }
  mkdirSync(join(apkPath, ".."), { recursive: true });
  copyFileSync(builtApk, apkPath);
}

if (!existsSync(apkPath)) {
  console.error(`\n✗ Gradle terminó pero no existe ${apkPath}.`);
  process.exit(1);
}
const version = readFileSync(join(androidDir, "app", "build.gradle"), "utf8").match(/versionName\s+"([^"]+)"/)?.[1];
const sizeMb = (statSync(apkPath).size / 1024 / 1024).toFixed(1);
console.log(`\n✓ APK debug de DINCR ${version || ""} (${sizeMb} MB):\n  ${apkPath}`);
console.log("  Instalar en un dispositivo conectado: adb install -r \"" + apkPath + "\"");
