import {
  getNotificationStatus,
  getVapidPublicKey,
  savePushSubscription,
  sendTestNotification,
} from "./services/jarvisApi";

const urlBase64ToUint8Array = (base64String) => {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
};

export const isPushSupported = () =>
  "serviceWorker" in navigator &&
  "PushManager" in window &&
  "Notification" in window;

export const registerJarvisServiceWorker = async () => {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/sw.js");
};

export const enableJarvisPushNotifications = async () => {
  if (!isPushSupported()) {
    throw new Error("Este dispositivo o navegador no soporta Web Push. En iPhone debe estar instalada como app web/PWA.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Permiso de notificaciones no concedido.");
  }

  const vapid = await getVapidPublicKey();
  if (!vapid?.public_key) {
    throw new Error("Falta VAPID_PUBLIC_KEY en Render.");
  }

  const registration = await registerJarvisServiceWorker();
  if (!registration) {
    throw new Error("No pude registrar el service worker de JARVIS.");
  }

  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
    });
  }

  const payload = subscription.toJSON();
  await savePushSubscription({
    subscription: payload,
    endpoint: payload.endpoint,
    keys: payload.keys,
    permission,
    userAgent: navigator.userAgent,
    device: /iphone|ipad|ipod/i.test(navigator.userAgent) ? "ios-pwa" : "browser",
  });

  const test = await sendTestNotification();
  const status = await getNotificationStatus();

  return { permission, subscription: payload, test, status };
};
