// Dashboard: bookings (accept/reject/cancel, contact, payment, review, report, SOS), notifications, profile.
const to12 = to12Hour;

let role = null, roles = [], bookings = [], profile = null, activeTab = "bookings", pollTimer = null;

async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (res.status === 401) { location.href = "/"; throw new Error("auth"); }
  if (!res.ok) throw new Error(data.error || "Something went wrong");
  return data;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const toast = (msg, err) => showToast(msg, err ? "error" : "");

// ---------- modal ----------
let modalOk = null;
function openModal(title, bodyHtml, onOk, okLabel = "Submit") {
  $("modal-title").textContent = title;
  $("modal-body").innerHTML = bodyHtml;
  $("modal-error").classList.add("hidden");
  $("modal-ok").textContent = okLabel;
  $("modal-ok").classList.toggle("hidden", !onOk);
  $("modal-ok").disabled = false;
  modalOk = onOk;
  $("modal").classList.remove("hidden"); $("modal").classList.add("flex");
}
function closeModal() { $("modal").classList.add("hidden"); $("modal").classList.remove("flex"); modalOk = null; }
$("modal-cancel").addEventListener("click", closeModal);
$("modal-ok").addEventListener("click", async () => {
  if (!modalOk) return;
  $("modal-ok").disabled = true;
  try { await modalOk(); }
  catch (e) { $("modal-error").textContent = e.message; $("modal-error").classList.remove("hidden"); $("modal-ok").disabled = false; }
});

// ---------- tabs / roles ----------
function setTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab-btn").forEach((b) => {
    const on = b.dataset.tab === tab;
    b.className = `tab-btn px-3 sm:px-4 py-2 font-medium shrink-0 border-b-2 ${on ? "border-green text-green-dark" : "border-transparent text-ink/50"}`;
  });
  ["bookings", "notifications", "profile"].forEach((t) => $("tab-" + t).classList.toggle("hidden", t !== tab));
  if (tab === "bookings") loadBookings();
  if (tab === "notifications") loadNotifications(true);
  if (tab === "profile") loadProfile();
}
document.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

function renderRoleSwitch() {
  const box = $("role-switch");
  if (roles.length < 2) return box.classList.add("hidden");
  box.classList.remove("hidden"); box.classList.add("flex");
  box.innerHTML = roles.map((r) => `<button data-role="${r}" class="text-xs font-medium px-3 py-1.5 rounded-full border ${r === role ? "bg-green text-white border-green" : "border-ink/15"}">${r === "companion" ? "As companion" : "As customer"}</button>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { role = b.dataset.role; renderRoleSwitch(); setTab(activeTab); refreshBadge(); }));
}

// ---------- bookings ----------
const STATUS_STYLE = { Pending: "bg-amber-100 text-amber-700", Confirmed: "bg-green-light/25 text-green-dark", Completed: "bg-blue-100 text-blue-700", Cancelled: "bg-ink/10 text-ink/60" };
const stars = (n) => "★".repeat(n) + "☆".repeat(5 - n);

function bookingCard(b) {
  const isC = role === "companion";
  const who = isC ? "Customer" : "Companion";
  let note = "";
  if (b.status === "Cancelled") note = `<p class="text-xs text-ink/50 mt-1">Cancelled by ${esc(b.cancelled_by || "—")}${b.cancelled_by === "System" ? " (request time tak accept nahi hui)" : ""}</p>`;
  if (b.status === "Pending") note = `<p class="text-xs text-amber-700 mt-1">${isC ? "Is request ko accept ya decline karo." : "Companion ke accept karne ka intezaar hai."}</p>`;
  const phoneHint = isC ? "(booking accept karne ke baad dikhta hai)" : "(booking hote hi share hota hai)";
  const phone = b.other_phone ? `<p class="text-sm mt-2 break-all">📞 <a class="text-green-dark font-medium underline" href="tel:${esc(b.other_phone)}">${esc(b.other_phone)}</a> <span class="text-xs text-ink/40">${phoneHint}</span></p>` : "";
  const pay = b.status === "Confirmed" || b.status === "Completed" ? `<span class="text-xs ${b.payment_status === "Paid" ? "text-green-dark" : "text-ink/50"}">Payment: ${esc(b.payment_status)}</span>` : "";
  const review = b.rating ? `<p class="text-xs mt-1 text-amber-600 break-words">${stars(b.rating)} ${b.review_comment ? "— " + esc(b.review_comment) : ""}</p>` : "";

  const btn = (act, label, cls = "border border-ink/15") => `<button data-act="${act}" data-id="${b.booking_id}" class="text-xs font-medium rounded-lg px-3 py-1.5 ${cls}">${label}</button>`;
  const actions = [];
  if (isC && b.status === "Pending") actions.push(btn("accept", "Accept", "bg-green text-white"), btn("reject", "Decline"));
  if (!isC && b.status === "Pending") actions.push(btn("cancel", "Cancel request"));
  if (b.status === "Confirmed") {
    actions.push(btn("cancel", "Cancel booking"));
    if (isC && b.payment_status === "Unpaid") actions.push(btn("paid", "Payment received"));
    actions.push(btn("sos", "🚨 SOS", "bg-red-600 text-white"));
  }
  if (b.status === "Completed") {
    if (isC && b.payment_status === "Unpaid") actions.push(btn("paid", "Payment received"));
    if (!isC && !b.rating) actions.push(btn("review", "Rate", "bg-green text-white"));
  }
  if (b.status === "Confirmed" || b.status === "Completed") actions.push(btn("report", "Report issue"));

  return `<div class="bg-white rounded-xl border border-green/10 p-4">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0"><p class="font-display font-semibold break-words">${esc(b.other_name)} <span class="text-xs font-normal text-ink/40">(${who})</span></p>
        <p class="text-xs text-ink/60 mt-0.5">${esc(b.booking_date)} · ${to12(b.start_time)} – ${to12(b.end_time)} · ₹${esc(b.total_amount)} ${pay}</p></div>
      <span class="shrink-0 text-[11px] font-semibold rounded-full px-2.5 py-1 ${STATUS_STYLE[b.status] || ""}">${esc(b.status)}</span>
    </div>${note}${phone}${review}
    ${actions.length ? `<div class="flex flex-wrap gap-2 mt-3">${actions.join("")}</div>` : ""}
  </div>`;
}

async function loadBookings() {
  const box = $("tab-bookings");
  try {
    bookings = await api(`/api/my/bookings?role=${role}`);
    let ratingBar = "";
    if (role === "companion") {
      try {
        const r = await api("/api/my/rating");
        ratingBar = `<div class="bg-white rounded-xl border border-green/10 p-4 mb-3 flex items-center gap-3">
          <span class="text-3xl font-display font-bold text-amber-500">${r.review_count ? Number(r.avg_rating).toFixed(1) : "—"}</span>
          <div class="min-w-0"><p class="text-amber-500 text-sm">${r.review_count ? stars(Math.round(r.avg_rating)) : "☆☆☆☆☆"}</p>
          <p class="text-xs text-ink/50">${r.review_count ? `${r.review_count} customer rating${r.review_count > 1 ? "s" : ""}` : "Abhi koi rating nahi mili"}</p></div></div>`;
      } catch { /* rating bar optional */ }
    }
    box.innerHTML = ratingBar + (bookings.length
      ? `<div class="space-y-3">${bookings.map(bookingCard).join("")}</div>`
      : `<p class="text-sm text-ink/50 py-8 text-center">Abhi koi booking nahi hai.</p>`);
  } catch (e) { if (e.message !== "auth") box.innerHTML = `<p class="text-sm text-red-600">${esc(e.message)}</p>`; }
}

$("tab-bookings").addEventListener("click", async (ev) => {
  const el = ev.target.closest("button[data-act]");
  if (!el) return;
  const id = Number(el.dataset.id), act = el.dataset.act;
  const b = bookings.find((x) => x.booking_id === id);
  try {
    if (["accept", "reject", "cancel"].includes(act)) {
      if (act !== "accept" && !confirm(act === "reject" ? "Is request ko decline karna hai?" : "Booking cancel karni hai?")) return;
      await post(`/api/bookings/${id}/action`, { role, action: act });
      toast(act === "accept" ? "Booking accept ho gayi" : act === "reject" ? "Request decline kar di" : "Booking cancel ho gayi");
      loadBookings();
    } else if (act === "paid") {
      await post(`/api/bookings/${id}/paid`, {});
      toast("Payment received mark ho gaya"); loadBookings();
    } else if (act === "review") {
      openModal("Rate " + b.other_name, `
        <label class="block text-xs font-medium text-ink/60 mb-1">Rating</label>
        <div id="rv-stars" class="flex items-center" role="radiogroup" aria-label="Rating">${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="star-btn" data-n="${n}" role="radio" aria-label="${n} star">★</button>`).join("")}</div>
        <input type="hidden" id="rv-rating" value="">
        <label class="block text-xs font-medium text-ink/60 mt-3 mb-1">Comment (optional)</label>
        <textarea id="rv-comment" maxlength="500" rows="3" class="w-full border border-ink/15 rounded-lg px-3 py-2"></textarea>`,
        async () => { if (!$("rv-rating").value) throw new Error("Pehle star rating chuno"); await post(`/api/bookings/${id}/review`, { rating: $("rv-rating").value, comment: $("rv-comment").value }); closeModal(); toast("Review submit ho gaya"); loadBookings(); });
      $("rv-stars").addEventListener("click", (e) => {
        const b = e.target.closest(".star-btn"); if (!b) return;
        $("rv-rating").value = b.dataset.n;
        $("rv-stars").querySelectorAll(".star-btn").forEach((x) => x.classList.toggle("on", Number(x.dataset.n) <= Number(b.dataset.n)));
      });
    } else if (act === "report") {
      openModal("Report an issue", `
        <label class="block text-xs font-medium text-ink/60 mb-1">Issue type</label>
        <select id="rp-type" class="w-full border border-ink/15 rounded-lg px-3 py-2">${["Harassment", "Unsafe behaviour", "No-show", "Payment issue", "Fake profile", "Other"].map((t) => `<option>${t}</option>`).join("")}</select>
        <label class="block text-xs font-medium text-ink/60 mt-3 mb-1">Kya hua?</label>
        <textarea id="rp-desc" maxlength="1000" rows="4" class="w-full border border-ink/15 rounded-lg px-3 py-2"></textarea>`,
        async () => { await post("/api/reports", { role, booking_id: id, issue_type: $("rp-type").value, description: $("rp-desc").value }); closeModal(); toast("Report admin team ko bhej di gayi"); });
    } else if (act === "sos") {
      if (!confirm("SOS alert bhejna hai? Ye admin team ko aapki location ke saath alert bhejta hai.")) return;
      toast("SOS bhej raha hoon...");
      const pos = await new Promise((resolve) => navigator.geolocation
        ? navigator.geolocation.getCurrentPosition((p) => resolve(p.coords), () => resolve(null), { timeout: 6000, enableHighAccuracy: true })
        : resolve(null));
      await post("/api/reports", { role, booking_id: id, sos: true, latitude: pos && pos.latitude, longitude: pos && pos.longitude });
      let emergency = "";
      if (role === "companion") {
        try { const p = await api("/api/profile?role=companion"); if (p.emergency_phone) emergency = `<p class="mt-2">Emergency contact (${esc(p.emergency_name || "")}): <a class="text-green-dark underline" href="tel:${esc(p.emergency_phone)}">${esc(p.emergency_phone)}</a></p>`; } catch (e) {}
      }
      openModal("🚨 SOS bhej diya gaya", `<p>Admin team ko alert mil gaya hai. <b>Abhi turant 112 par call karo</b> aur safe jagah par jao.</p>
        <p class="mt-3"><a href="tel:112" class="inline-block bg-red-600 text-white font-medium rounded-lg px-4 py-2">Call 112</a></p>${emergency}`, null);
    }
  } catch (e) { if (e.message !== "auth") toast(e.message, true); }
});

// ---------- notifications ----------
async function refreshBadge() {
  try {
    const d = await api(`/api/notifications?role=${role}`);
    const b = $("notif-badge");
    b.textContent = d.unread; b.classList.toggle("hidden", !d.unread);
    return d;
  } catch (e) {}
}
async function loadNotifications(markRead) {
  const d = await refreshBadge();
  if (!d) return;
  $("tab-notifications").innerHTML = d.items.length
    ? `<div class="space-y-2">${d.items.map((n) => `<div class="bg-white rounded-xl border ${n.is_read ? "border-green/10" : "border-green"} p-3 text-sm">${esc(n.message)}<p class="text-[11px] text-ink/40 mt-1">${esc(n.created_at)}</p></div>`).join("")}</div>`
    : `<p class="text-sm text-ink/50 py-8 text-center">Koi notification nahi.</p>`;
  if (markRead && d.unread) { await post("/api/notifications/read", { role }); $("notif-badge").classList.add("hidden"); }
}

// ---------- profile ----------
const field = (id, label, val, type = "text", extra = "") => `<div><label class="block text-xs font-medium text-ink/60 mb-1">${label}</label><input id="${id}" type="${type}" value="${esc(val)}" ${extra} class="w-full border border-ink/15 rounded-lg px-3 py-2 text-sm"></div>`;

async function loadProfile() {
  const box = $("tab-profile");
  try {
    profile = await api(`/api/profile?role=${role}`);
    const isC = role === "companion";
    let banner = "";
    if (isC && profile.status === "Inactive") banner = profile.background_check === "Failed"
      ? `<p class="text-sm bg-red-50 text-red-700 rounded-lg p-3 mb-4">Aapka verification approve nahi hua. Details check karke support se contact karo.</p>`
      : `<p class="text-sm bg-amber-50 text-amber-700 rounded-lg p-3 mb-4">Verification pending hai — approve hone ke baad hi aap customers ko dikhoge.</p>`;
    if (isC && ["Suspended", "Blacklisted"].includes(profile.status)) banner = `<p class="text-sm bg-red-50 text-red-700 rounded-lg p-3 mb-4">Aapka account ${esc(profile.status)} hai.</p>`;

    box.innerHTML = `${banner}<div class="bg-white rounded-xl border border-green/10 p-5 space-y-3">
      <p class="text-sm"><b>${esc(profile.full_name)}</b> <span class="text-ink/50">· ${esc(profile.email)}</span></p>
      ${isC ? `<p class="text-xs text-ink/50">ID proof (${esc(profile.id_proof_type)}): ${esc(profile.id_proof_number)} · Status: ${esc(profile.status)}</p>` : ""}
      ${field("pf-phone", "Phone", profile.phone, "tel")}
      ${isC ? `
        ${field("pf-service_type", "Service type", profile.service_type)}
        ${field("pf-hourly_rate", "Hourly rate (₹)", profile.hourly_rate, "number", 'min="1"')}
        ${field("pf-service_radius_km", "Service radius (km)", profile.service_radius_km, "number", 'min="1" max="200"')}
        ${field("pf-languages", "Languages", profile.languages)}
        ${field("pf-skills", "Skills", profile.skills)}
        <div><label class="block text-xs font-medium text-ink/60 mb-1">Bio</label><textarea id="pf-bio" rows="3" maxlength="1000" class="w-full border border-ink/15 rounded-lg px-3 py-2 text-sm">${esc(profile.bio)}</textarea></div>
        ${field("pf-emergency_name", "Emergency contact name", profile.emergency_name)}
        ${field("pf-emergency_relation", "Relation", profile.emergency_relation)}
        ${field("pf-emergency_phone", "Emergency phone", profile.emergency_phone, "tel")}` : field("pf-full_name", "Full name", profile.full_name)}
      <p id="pf-msg" class="hidden text-xs"></p>
      <button id="pf-save" class="bg-green hover:bg-green-dark text-white text-sm font-medium rounded-lg px-5 py-2">Save changes</button>
    </div>
    <div class="mt-6 bg-white rounded-xl border border-red-200 p-5">
      <p class="font-display font-semibold text-sm mb-1">Account</p>
      <p class="text-xs text-ink/50 mb-3">Deactivate: account band, dobara Google sign-in se wapas aa sakte ho. Delete: personal data hamesha ke liye hat jata hai. (Pehle active bookings cancel/complete karo.)</p>
      <div class="flex gap-2"><button id="acc-deactivate" class="text-xs font-medium border border-ink/20 rounded-lg px-3 py-1.5">Deactivate account</button>
      <button id="acc-delete" class="text-xs font-medium bg-red-600 text-white rounded-lg px-3 py-1.5">Delete my data</button></div>
    </div>`;

    $("pf-save").addEventListener("click", async () => {
      const keys = isC ? ["phone", "service_type", "hourly_rate", "service_radius_km", "languages", "skills", "bio", "emergency_name", "emergency_relation", "emergency_phone"] : ["phone", "full_name"];
      const fields = {}; keys.forEach((k) => { fields[k] = $("pf-" + k).value; });
      const msg = $("pf-msg");
      try { await post("/api/profile/update", { role, fields }); msg.textContent = "Saved ✓"; msg.className = "text-xs text-green-dark"; }
      catch (e) { msg.textContent = e.message; msg.className = "text-xs text-red-600"; }
    });
    $("acc-deactivate").addEventListener("click", async () => {
      if (!confirm("Account deactivate karna hai?")) return;
      try { await post("/api/account/deactivate", { role }); location.href = "/"; } catch (e) { toast(e.message, true); }
    });
    $("acc-delete").addEventListener("click", () => openModal("Delete my data", `<p>Ye permanent hai. Confirm karne ke liye <b>DELETE</b> likho.</p><input id="del-confirm" class="mt-3 w-full border border-ink/15 rounded-lg px-3 py-2" placeholder="DELETE">`,
      async () => { await post("/api/account/delete", { role, confirm: $("del-confirm").value.trim() }); location.href = "/"; }, "Delete forever"));
  } catch (e) { if (e.message !== "auth") box.innerHTML = `<p class="text-sm text-red-600">${esc(e.message)}</p>`; }
}

// ---------- init ----------
(async () => {
  try {
    roles = (await api("/api/dashboard/me")).roles;
    role = roles.includes("companion") && !roles.includes("customer") ? "companion" : roles[0];
    const want = new URLSearchParams(location.search).get("role");
    if (roles.includes(want)) role = want;
    renderRoleSwitch(); setTab("bookings"); refreshBadge();
    pollTimer = setInterval(() => { if (!document.hidden && activeTab === "bookings") loadBookings(); refreshBadge(); }, 30000);
  } catch (e) { if (e.message !== "auth") { $("page-error").textContent = e.message; $("page-error").classList.remove("hidden"); } }
})();
