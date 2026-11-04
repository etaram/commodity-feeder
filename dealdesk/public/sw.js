// Sinder Deal Desk service worker: fast start, push notifications. Data is never cached (the API answers live or
// from the server's own snapshot); only the shell, the shim, brand files and fonts are kept for an instant open.
const SHELL = "sinder-shell-v2";  // v1 kept a stale panel-shim.js forever; bumping the name clears it
const STATIC = ["/panel-shim.js", "/brand/mark.svg", "/brand/mark-512.png", "/manifest.webmanifest"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(STATIC)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (u.pathname.startsWith("/api/")) return;  // live data, never cached
  if (u.pathname === "/" ) {  // the panel: network first, last copy when offline
    e.respondWith(fetch(e.request).then((r) => { const c = r.clone(); caches.open(SHELL).then((k) => k.put("/", c)); return r; }).catch(() => caches.match("/")));
    return;
  }
  // the shim and the manifest change with every release: network first, the cached copy only when offline
  if (u.pathname === "/panel-shim.js" || u.pathname === "/manifest.webmanifest") {
    e.respondWith(fetch(e.request, { cache: "no-store" }).then((r) => { const c = r.clone(); caches.open(SHELL).then((k) => k.put(e.request, c)); return r; }).catch(() => caches.match(e.request)));
    return;
  }
  if (u.pathname.startsWith("/brand/")) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => { const c = r.clone(); caches.open(SHELL).then((k) => k.put(e.request, c)); return r; })));
  }
});
self.addEventListener("push", (e) => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch { d = { title: "Sinder Deal Desk", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Sinder Deal Desk", { body: d.body || "", icon: "/brand/mark-512.png", badge: "/brand/mark-512.png", data: { url: d.url || "/#today" }, tag: d.tag || "sinder", renotify: !!d.tag }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/#today";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => { for (const c of cs) { if ("focus" in c) { c.navigate(url); return c.focus(); } } return self.clients.openWindow(url); }));
});
