// Har same-origin state-changing fetch me X-Requested-With header lagata hai (server CSRF guard ke liye).
(() => {
  const orig = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method || (input && input.method) || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (url.startsWith("/") || url.startsWith(location.origin)) {
        const h = new Headers(init.headers || (input && input.headers) || {});
        h.set("X-Requested-With", "GreenBEE");
        init.headers = h;
      }
    }
    return orig.call(this, input, init);
  };
})();
