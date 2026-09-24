// One release identity for Android, iOS and the web bundle (which reads versionName
// from android/app/build.gradle, see vite.config.js).
//
//   npm run release:version                 show and check both platforms
//   npm run release:version -- 1.10.0       set versionName/MARKETING_VERSION and bump
//                                           versionCode/CURRENT_PROJECT_VERSION to max+1
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const GRADLE = `${root}/android/app/build.gradle`;
const XCODE = `${root}/ios-dincr/App/App.xcodeproj/project.pbxproj`;

export function readIdentity(gradle = readFileSync(GRADLE, "utf8"), xcode = readFileSync(XCODE, "utf8")) {
  const unique = (values) => [...new Set(values)];
  return {
    android: {
      name: gradle.match(/versionName\s+"([^"]+)"/)?.[1],
      code: Number(gradle.match(/versionCode\s+(\d+)/)?.[1]),
    },
    ios: {
      names: unique([...xcode.matchAll(/MARKETING_VERSION = ([^;]+);/g)].map((m) => m[1].trim())),
      builds: unique([...xcode.matchAll(/CURRENT_PROJECT_VERSION = ([^;]+);/g)].map((m) => Number(m[1]))),
    },
  };
}

export function identityProblems(identity) {
  const problems = [];
  const { android, ios } = identity;
  if (!/^\d+\.\d+\.\d+$/.test(android.name || "")) problems.push(`Android versionName inválido: ${android.name}`);
  if (!Number.isInteger(android.code) || android.code < 1) problems.push(`Android versionCode inválido: ${android.code}`);
  if (ios.names.length !== 1) problems.push(`iOS tiene varios MARKETING_VERSION: ${ios.names.join(", ")}`);
  if (ios.builds.length !== 1) problems.push(`iOS tiene varios CURRENT_PROJECT_VERSION: ${ios.builds.join(", ")}`);
  if (ios.names[0] !== android.name) problems.push(`Versión distinta: Android ${android.name} vs iOS ${ios.names[0]}`);
  if (ios.builds[0] !== android.code) problems.push(`Build distinto: Android ${android.code} vs iOS ${ios.builds[0]}`);
  return problems;
}

function setVersion(version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error("Usá una versión semántica, por ejemplo 1.10.0");
  const gradle = readFileSync(GRADLE, "utf8");
  const xcode = readFileSync(XCODE, "utf8");
  const current = readIdentity(gradle, xcode);
  // Store build numbers must only grow; both platforms share the next one.
  const build = Math.max(current.android.code, ...current.ios.builds) + 1;
  writeFileSync(GRADLE, gradle.replace(/versionName\s+"[^"]+"/, `versionName "${version}"`).replace(/versionCode\s+\d+/, `versionCode ${build}`));
  writeFileSync(XCODE, xcode.replace(/MARKETING_VERSION = [^;]+;/g, `MARKETING_VERSION = ${version};`).replace(/CURRENT_PROJECT_VERSION = [^;]+;/g, `CURRENT_PROJECT_VERSION = ${build};`));
  return { version, build };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [version] = process.argv.slice(2);
  if (version) {
    const result = setVersion(version);
    console.log(`DINCR ${result.version} (build ${result.build}) en Android e iOS. Recordá npm run build + cap sync.`);
  }
  const identity = readIdentity();
  console.log(`Android ${identity.android.name} (${identity.android.code}) · iOS ${identity.ios.names.join("/")} (${identity.ios.builds.join("/")})`);
  const problems = identityProblems(identity);
  for (const problem of problems) console.error(`✗ ${problem}`);
  process.exit(problems.length ? 1 : 0);
}
