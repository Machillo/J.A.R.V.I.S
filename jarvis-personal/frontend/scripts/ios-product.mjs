import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const products = {
  finva: { config: "capacitor.ios.finva.json", appId: "com.finva.app", nativePath: "ios-finva" },
  jarvis: { config: "capacitor.ios.jarvis.json", appId: "com.jarvis.personal", nativePath: "ios-jarvis" },
};

const [productName, action = "sync"] = process.argv.slice(2);
const product = products[productName];

if (!product || !["sync", "open"].includes(action)) {
  console.error("Uso: node scripts/ios-product.mjs <finva|jarvis> <sync|open>");
  process.exit(1);
}

const canonicalConfigPath = "capacitor.config.json";
const originalConfig = readFileSync(canonicalConfigPath, "utf8");
const iosConfig = readFileSync(product.config, "utf8");

function run(command, args, extraEnv = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: false,
    env: { ...process.env, ...extraEnv },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exitCode = result.status || 1;
  return result.status === 0;
}

function generatedFiles(root) {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = `${root}/${entry.name}`;
    return entry.isDirectory() ? generatedFiles(path) : [path];
  });
}

function verifyNativeBundle() {
  const nativeConfigPath = `${product.nativePath}/App/App/capacitor.config.json`;
  const publicPath = `${product.nativePath}/App/App/public`;
  const generatedConfig = JSON.parse(readFileSync(nativeConfigPath, "utf8"));
  if (generatedConfig.appId !== product.appId) {
    throw new Error(`El proyecto iOS generado no corresponde a ${product.appId}.`);
  }

  if (productName === "finva") {
    const hasBiometricOnboarding = generatedFiles(publicPath)
      .filter((path) => path.endsWith(".js"))
      .some((path) => readFileSync(path, "utf8").includes("finva:app-lock-onboarding:v1"));
    if (!hasBiometricOnboarding) {
      throw new Error("El bundle iOS de FINVA no contiene el onboarding biométrico. No abras Xcode con archivos antiguos.");
    }
  }
}

try {
  writeFileSync(canonicalConfigPath, iosConfig);
  if (!run("npm", ["run", "build"], { VITE_NATIVE_APP_ID: product.appId })) throw new Error("Falló el build web.");
  if (!existsSync(product.nativePath) && !run("npx", ["cap", "add", "ios"])) throw new Error("No se pudo crear el proyecto iOS.");
  if (!run("npx", ["cap", "sync", "ios"])) throw new Error("No se pudo sincronizar el proyecto iOS.");
  verifyNativeBundle();
  if (action === "open") run("npx", ["cap", "open", "ios"]);
} finally {
  writeFileSync(canonicalConfigPath, originalConfig);
}
