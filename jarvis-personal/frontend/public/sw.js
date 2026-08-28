self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = { title: "J.A.R.V.I.S.", body: event.data ? event.data.text() : "Nueva notificación." };
  }

  const title = data.title || "J.A.R.V.I.S.";
  const options = {
    body: data.body || "Señor, tiene una alerta pendiente.",
    icon: data.icon || "/jarvis-icon-192.png",
    badge: data.badge || "/jarvis-icon-192.png",
    data: { url: data.url || "/", category: data.category || "general" },
    vibrate: [120, 60, 120],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification?.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
