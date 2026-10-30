// Companion ki location har 5 minute mein background se DB mein save hoti hai
// (page refresh / manual update ki zaroorat nahi). base.html se sab pages par chalta hai,
// sirf tab jab companion logged-in ho (<body data-companion="1">).
(() => {
  if (!document.body || document.body.dataset.companion !== "1" || !navigator.geolocation) return;

  const INTERVAL_MS = 5 * 60 * 1000;
  const CHECK_MS = 30 * 1000;          // chhota tick: throttled/sleeping tab ke baad bhi 5 min se zyada der nahi
  const KEY = "gb_comp_loc_ts";        // tabs ke beech shared - ek hi ping, duplicate nahi
  let busy = false, stopped = false;

  const lastPush = () => { try { return Number(localStorage.getItem(KEY)) || 0; } catch (e) { return mem; } };
  let mem = 0;
  const markPush = (t) => { mem = t; try { localStorage.setItem(KEY, String(t)); } catch (e) { /* private mode */ } };

  function position() {
    return new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject,
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 }));
  }

  async function push(force) {
    if (busy || stopped) return;
    if (!force && Date.now() - lastPush() < INTERVAL_MS - 5000) return;
    busy = true;
    markPush(Date.now());  // pehle mark: doosra tab same waqt par dobara na bheje
    try {
      const pos = await position();
      const res = await fetch("/api/companion/location", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
        keepalive: true
      });
      if (res.status === 401) { stopped = true; return; }   // logout / suspend - band
      if (!res.ok) markPush(0);                             // fail -> agle tick par retry
    } catch (e) {
      markPush(0);  // GPS/network error -> agle tick (30s) par retry
    } finally {
      busy = false;
    }
  }

  push(false);                                       // page load par (agar 5 min purana hai)
  setInterval(() => push(false), CHECK_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) push(false); });
  window.addEventListener("online", () => push(false));
  window.addEventListener("pageshow", () => push(false));  // bfcache se wapas aane par
})();
