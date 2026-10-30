// Shared helpers - saare pages par base.html se load hote hain.
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const show = (el) => { el.classList.remove("hidden"); el.classList.add("flex"); };
const hide = (el) => { el.classList.add("hidden"); el.classList.remove("flex"); };

// "HH:MM"/"HH:MM:SS" (24h) -> "h:mm AM/PM"
function to12Hour(t) {
  const [h, m] = String(t).split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

// alert() ki jagah toast - kai mobile/webview browsers alert() ko silently block kar dete hain.
// type: "error" (ya truthy second arg) => red, warna green.
let toastTimer = null;
function showToast(message, type) {
  const t = $("toast");
  if (!t) return;
  t.textContent = message;
  t.className = `fixed bottom-5 left-1/2 -translate-x-1/2 z-[80] max-w-sm w-[calc(100%-2rem)] rounded-xl shadow-lg px-4 py-3 text-sm font-medium text-white ${type ? "bg-red-600" : "bg-green-dark"}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 5000);
}

// Avatar: photo ho to photo, warna naam ka pehla akshar. Naam sirf tooltip/screen-reader ke liye.
function avatarHtml(url, name, size = "w-9 h-9") {
  const initial = esc((name || "?").trim().charAt(0).toUpperCase());
  const fallback = `<span class="${size} rounded-full bg-green/15 text-green-dark font-display font-semibold flex items-center justify-center text-sm shrink-0" title="${esc(name)}" aria-label="${esc(name)}">${initial}</span>`;
  if (!url) return fallback;
  return `<img src="${esc(url)}" alt="${esc(name)}" title="${esc(name)}" referrerpolicy="no-referrer"
    class="${size} rounded-full object-cover border border-green/20 shrink-0"
    onerror="this.outerHTML=this.dataset.fb" data-fb="${esc(fallback)}">`;
}

// Rating stars: 4.5 => saade chaar star (pehle round hoke 5 dikhta tha)
function starsHtml(avg) {
  const pct = Math.max(0, Math.min(5, Number(avg) || 0)) / 5 * 100;
  return `<span class="stars" style="--p:${pct.toFixed(0)}%" role="img" aria-label="${Number(avg || 0).toFixed(1)} out of 5">★★★★★</span>`;
}
