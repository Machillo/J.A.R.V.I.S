import { Capacitor } from "@capacitor/core";

export function detectNativePlatform() {
  const capacitorPlatform = Capacitor.getPlatform();
  if (capacitorPlatform === "ios" || capacitorPlatform === "android") return capacitorPlatform;

  const agent = window.navigator.userAgent || "";
  if (/iPad|iPhone|iPod/i.test(agent)) return "ios";
  if (/Android/i.test(agent)) return "android";
  return "web";
}

export function nativePlatformClass(platform = detectNativePlatform()) {
  return `native-platform native-platform--${platform}`;
}
