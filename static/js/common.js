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
