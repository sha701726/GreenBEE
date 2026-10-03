let tab = "companions", compFilter = "pending";

async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (res.status === 401 && path !== "/api/admin/login") { showLogin(); throw new Error("Login chahiye"); }
  if (!res.ok) throw new Error(data.error || "Something went wrong");
  return data;
}
const post = (p, b) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) });
function msg(text, err) { const m = $("msg"); m.textContent = text; m.className = `text-sm mb-3 ${err ? "text-red-600" : "text-green-dark"}`; clearTimeout(msg.t); msg.t = setTimeout(() => m.classList.add("hidden"), 4000); }

function showLogin() { $("login").classList.remove("hidden"); $("panel").classList.add("hidden"); $("logout").classList.add("hidden"); }
function showPanel() { $("login").classList.add("hidden"); $("panel").classList.remove("hidden"); $("logout").classList.remove("hidden"); loadStats(); setTab(tab); }

$("login-btn").addEventListener("click", async () => {
  try { await post("/api/admin/login", { key: $("key").value }); $("key").value = ""; $("login-error").classList.add("hidden"); showPanel(); }
  catch (e) { $("login-error").textContent = e.message; $("login-error").classList.remove("hidden"); }
});
$("key").addEventListener("keydown", (e) => { if (e.key === "Enter") $("login-btn").click(); });
$("logout").addEventListener("click", async () => { await post("/api/admin/logout"); showLogin(); });

async function loadStats() {
  const s = await api("/api/admin/stats");
  const items = [["Pending verification", s.pending_companions], ["Active companions", s.active_companions], ["Customers", s.customers],
    ["Open reports", s.open_reports], ["Open SOS", s.open_sos], ["Bookings today", s.bookings_today]];
  $("stats").innerHTML = items.map(([l, v]) => `<div class="bg-white rounded-xl border ${l === "Open SOS" && v ? "border-red-400 bg-red-50" : "border-green/10"} p-3"><p class="text-[11px] text-ink/50">${l}</p><p class="font-display font-bold text-xl">${v}</p></div>`).join("");
}

function setTab(t) {
  tab = t;
  document.querySelectorAll(".tab-btn").forEach((b) => { const on = b.dataset.tab === t; b.className = `tab-btn px-3 sm:px-4 py-2 font-medium shrink-0 border-b-2 ${on ? "border-green text-green-dark" : "border-transparent text-ink/50"}`; });
  ({ companions: loadCompanions, reports: loadReports, customers: loadCustomers, bookings: loadBookings })[t]().catch((e) => msg(e.message, true));
}
document.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

const btn = (attrs, label, cls = "border border-ink/15") => `<button ${attrs} class="text-xs font-medium rounded-lg px-3 py-1.5 ${cls}">${label}</button>`;

// ---- companions ----
async function loadCompanions() {
  const rows = await api(`/api/admin/companions${compFilter ? "?status=" + compFilter : ""}`);
  const opts = ["pending", "Active", "Inactive", "Suspended", "Blacklisted", "Deactivated", ""].map((o) => `<option value="${o}" ${o === compFilter ? "selected" : ""}>${o || "All"}</option>`).join("");
  $("content").innerHTML = `<div class="mb-3 text-sm">Filter: <select id="comp-filter" class="border border-ink/15 rounded-lg px-2 py-1">${opts}</select></div>
  <div class="space-y-3">${rows.map((c) => {
    const pending = c.status === "Inactive" && c.background_check === "Pending";
    const acts = [];
    if (pending || c.status === "Inactive") acts.push(btn(`data-a="approve" data-id="${c.companion_id}"`, "Approve", "bg-green text-white"));
    if (pending) acts.push(btn(`data-a="reject" data-id="${c.companion_id}"`, "Reject"));
    if (c.status === "Active") acts.push(btn(`data-a="suspend" data-id="${c.companion_id}"`, "Suspend"), btn(`data-a="blacklist" data-id="${c.companion_id}"`, "Blacklist", "bg-red-600 text-white"));
    if (["Suspended", "Blacklisted"].includes(c.status)) acts.push(btn(`data-a="reactivate" data-id="${c.companion_id}"`, "Reactivate", "bg-green text-white"));
    return `<div class="bg-white rounded-xl border border-green/10 p-3 sm:p-4 flex flex-col sm:flex-row gap-3 sm:gap-4">
      ${c.has_photo ? `<img src="/api/companions/${c.companion_id}/photo" class="w-16 h-16 rounded-lg object-cover shrink-0" alt="">` : ""}
      <div class="min-w-0 flex-1 text-sm">
        <p class="font-display font-semibold">#${c.companion_id} ${esc(c.full_name)} <span class="text-xs font-normal text-ink/50">${esc(c.gender)} · DOB ${esc(c.dob)} · ${esc(c.city)}</span></p>
        <p class="text-xs text-ink/60 mt-1">📞 ${esc(c.phone)} · ✉ ${esc(c.email)} · ₹${esc(c.hourly_rate)}/hr · ${esc(c.service_type)}</p>
        <p class="text-xs mt-1"><b>ID:</b> ${esc(c.id_proof_type)} — <span class="font-mono">${esc(c.id_proof_number)}</span> · <b>Emergency:</b> ${esc(c.emergency_name || "—")} ${esc(c.emergency_phone || "")}</p>
        <p class="text-xs mt-1">Status: <b>${esc(c.status)}</b> · Background check: <b>${esc(c.background_check)}</b>${c.verified_by ? ` (by ${esc(c.verified_by)} on ${esc(c.verified_date)})` : ""}</p>
        <div class="flex flex-wrap gap-2 mt-3">${acts.join("")}</div>
      </div></div>`;
  }).join("") || `<p class="text-sm text-ink/50 py-8 text-center">Koi companion nahi.</p>`}</div>`;
  $("comp-filter").addEventListener("change", (e) => { compFilter = e.target.value; loadCompanions(); });
}

// ---- reports ----
async function loadReports() {
  const rows = await api("/api/admin/reports");
  $("content").innerHTML = `<div class="space-y-3">${rows.map((r) => `
    <div class="bg-white rounded-xl border ${r.is_sos ? "border-red-400 bg-red-50" : "border-green/10"} p-4 text-sm">
      <p class="font-display font-semibold">${r.is_sos ? "🚨 SOS" : esc(r.issue_type)} <span class="text-xs font-normal text-ink/50">· report #${r.report_id} · booking #${r.booking_id} · by ${esc(r.reported_by)} · ${esc(r.created_at)}</span></p>
      <p class="text-xs mt-1">Companion #${r.companion_id} ${esc(r.companion_name)} (${esc(r.companion_phone)}) ↔ Customer #${r.customer_id} ${esc(r.customer_name)} (${esc(r.customer_phone)})</p>
      ${r.description ? `<p class="mt-2">${esc(r.description)}</p>` : ""}
      ${r.latitude != null ? `<p class="text-xs mt-1"><a class="text-green-dark underline" target="_blank" rel="noopener" href="https://maps.google.com/?q=${Number(r.latitude)},${Number(r.longitude)}">📍 Location on map</a></p>` : ""}
      <div class="flex flex-wrap items-center gap-2 mt-3">
        <select id="rs-${r.report_id}" class="border border-ink/15 rounded-lg px-2 py-1 text-xs">${["Open", "Under Review", "Resolved", "Dismissed"].map((s) => `<option ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}</select>
        <input id="ra-${r.report_id}" value="${esc(r.action_taken || "")}" placeholder="Action taken" class="border border-ink/15 rounded-lg px-2 py-1 text-xs flex-1 min-w-[10rem]">
        ${btn(`data-save="${r.report_id}"`, "Save", "bg-green text-white")}
        ${btn(`data-ca="suspend" data-id="${r.companion_id}"`, "Suspend companion")}
        ${btn(`data-cu="suspend" data-id="${r.customer_id}"`, "Suspend customer")}
      </div></div>`).join("") || `<p class="text-sm text-ink/50 py-8 text-center">Koi report nahi.</p>`}</div>`;
}

// ---- customers ----
async function loadCustomers() {
  const rows = await api("/api/admin/customers");
  $("content").innerHTML = `<div class="bg-white rounded-xl border border-green/10 overflow-x-auto"><table class="w-full text-sm"><thead class="text-left text-xs text-ink/50"><tr><th class="p-3">#</th><th>Name</th><th>Phone</th><th>Email</th><th>Status</th><th></th></tr></thead><tbody>
    ${rows.map((c) => `<tr class="border-t border-green/10"><td class="p-3">${c.customer_id}</td><td>${esc(c.full_name)}</td><td>${esc(c.phone)}</td><td>${esc(c.email)}</td><td>${esc(c.status)}</td>
      <td class="p-2">${c.status === "Active" ? btn(`data-cu="suspend" data-id="${c.customer_id}"`, "Suspend") : ["Suspended", "Blacklisted"].includes(c.status) ? btn(`data-cu="reactivate" data-id="${c.customer_id}"`, "Reactivate") : ""}</td></tr>`).join("")}
  </tbody></table></div>`;
}

// ---- bookings ----
async function loadBookings() {
  const rows = await api("/api/admin/bookings");
  $("content").innerHTML = `<div class="bg-white rounded-xl border border-green/10 overflow-x-auto"><table class="w-full text-sm"><thead class="text-left text-xs text-ink/50"><tr><th class="p-3">#</th><th>Date</th><th>Time</th><th>Companion</th><th>Customer</th><th>Amount</th><th>Commission</th><th>Payout</th><th>Payment</th><th>Status</th></tr></thead><tbody>
    ${rows.map((b) => `<tr class="border-t border-green/10"><td class="p-3">${b.booking_id}</td><td>${esc(b.booking_date)}</td><td>${esc(b.start_time)}-${esc(b.end_time)}</td><td>${esc(b.companion_name)}</td><td>${esc(b.customer_name)}</td><td>₹${esc(b.total_amount)}</td><td>${esc(b.commission_pct)}%</td><td>${b.payout_amount != null ? "₹" + esc(b.payout_amount) : "—"}</td><td>${esc(b.payment_status)}</td><td>${esc(b.status)}${b.cancelled_by ? " (" + esc(b.cancelled_by) + ")" : ""}${b.rating ? " · " + b.rating + "★" : ""}</td></tr>`).join("")}
  </tbody></table></div>`;
}

// ---- actions (delegation) ----
$("content").addEventListener("click", async (ev) => {
  const el = ev.target.closest("button");
  if (!el) return;
  try {
    if (el.dataset.a) {
      if (["suspend", "blacklist", "reject"].includes(el.dataset.a) && !confirm(`${el.dataset.a} karna hai? Active bookings cancel ho jayengi.`)) return;
      const r = await post(`/api/admin/companions/${el.dataset.id}/${el.dataset.a}`);
      msg(`Done (${r.cancelled_bookings} bookings cancelled)`); loadCompanions();
    } else if (el.dataset.ca) {
      if (!confirm("Companion ko suspend karna hai?")) return;
      await post(`/api/admin/companions/${el.dataset.id}/suspend`); msg("Companion suspended");
    } else if (el.dataset.cu) {
      if (el.dataset.cu === "suspend" && !confirm("Customer ko suspend karna hai?")) return;
      await post(`/api/admin/customers/${el.dataset.id}/${el.dataset.cu}`); msg("Done"); if (tab === "customers") loadCustomers();
    } else if (el.dataset.save) {
      const id = el.dataset.save;
      await post(`/api/admin/reports/${id}`, { status: $("rs-" + id).value, action_taken: $("ra-" + id).value }); msg("Report updated");
    } else return;
    loadStats();
  } catch (e) { msg(e.message, true); }
});

(async () => { try { await api("/api/admin/stats"); showPanel(); } catch (e) { showLogin(); } })();
