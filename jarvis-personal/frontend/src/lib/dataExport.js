import { Capacitor } from "@capacitor/core";
import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";

// Saves the account export as a JSON file: the share sheet on iOS/Android
// (so the user picks Files, Drive, email...), a regular download on the web.
export async function saveDataExport(payload) {
  const date = new Date().toISOString().slice(0, 10);
  const filename = `dincr-mis-datos-${date}.json`;
  const contents = JSON.stringify(payload, null, 2);

  if (Capacitor.isNativePlatform()) {
    const { uri } = await Filesystem.writeFile({ path: filename, data: contents, directory: Directory.Cache, encoding: Encoding.UTF8 });
    await Share.share({ title: "DINCR", files: [uri] });
    return;
  }

  const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
