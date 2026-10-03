let currentUser = null;      // { customer_id, name }
let currentLocation = null;  // { lat, lng }
let selectedCompanion = null;
let pendingCredential = null; // Google token, phone-modal confirm hone tak yahan hold hota hai

// ---------------- GOOGLE SIGN-IN ----------------
window.onload = () => {
  restoreSession();  // pehle se logged-in hai to login/signup dobara nahi maangna

  google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: handleGoogleCredential
  });
  // Chhoti screen (phone) par header mein jagah kam hoti hai - sirf icon wala compact Google button
  const compact = window.matchMedia("(max-width: 639px)").matches;
  google.accounts.id.renderButton(
    $("google-btn"),
    compact ? { type: "icon", shape: "circle", theme: "outline", size: "medium" }
            : { theme: "outline", size: "medium" }
  );
};

// Sign-in/signup ke waqt location maangta hai (browser permission prompt)
function requestSigninLocation() {
  const statusEl = $("signin-location-status");
  if (!navigator.geolocation) {
    statusEl.textContent = "Geolocation is not supported by this browser.";
    return;
  }
  statusEl.textContent = "Locating...";
  navigator.geolocation.getCurrentPosition((pos) => {
    currentLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    statusEl.textContent = `Location set (${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)})`;
  }, () => {
    currentLocation = null;
    statusEl.textContent = "Location denied — browser settings mein allow karke retry karo.";
  }, { enableHighAccuracy: true, timeout: 15000 });
}

$("signin-locate-btn").addEventListener("click", requestSigninLocation);

// Google se credential milte hi pehle server se role check hota hai (Companion / Customer / New)
async function handleGoogleCredential(response) {
  pendingCredential = response.credential;
  currentLocation = null;  // har sign-in par fresh location
  showToast("Checking your account...");

  try {
    const pos = await getPosition();
    currentLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
  } catch (err) {
    currentLocation = null;  // denied - existing user ko server location error dega, new user role choose kar sakta hai
  }

  try {
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        credential: pendingCredential,
        latitude: currentLocation ? currentLocation.lat : null,
        longitude: currentLocation ? currentLocation.lng : null
      })
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || "Something went wrong, please try again.", "error");
      pendingCredential = null;
      return;
    }

    if (data.role === "companion") {
      // Companion already registered - location server par update ho chuki hai, seedha status page
      window.location.href = `/companion/status/${data.companion_id}`;
    } else if (data.role === "customer") {
      showSignedInUI(data);
      lastLocationPush = Date.now();
      startLocationUpdates();
      loadNearbyCompanions();
    } else {
      openRoleModal();  // new user - Companion ya Customer choose karwao
    }
  } catch (err) {
    showToast("Network error — please try again.", "error");
    pendingCredential = null;
  }
}

// ---------------- NEW USER: ROLE CHOICE ----------------
function openRoleModal() {
  show($("role-modal"))
}

function closeRoleModal() {
  hide($("role-modal"))
}

$("role-companion-btn").addEventListener("click", () => {
  window.location.href = "/join";  // existing companion registration
});

$("role-customer-btn").addEventListener("click", () => {
  closeRoleModal();
  // Purana customer flow: phone modal -> /api/auth/google (phone ke saath)
  $("phone-input").value = "";
  $("phone-error").classList.add("hidden");
  if (currentLocation) {
    $("signin-location-status").textContent =
      `Location set (${currentLocation.lat.toFixed(3)}, ${currentLocation.lng.toFixed(3)})`;
  } else {
    requestSigninLocation();
  }
  show($("phone-modal"))
  $("phone-input").focus();
});

$("role-cancel-btn").addEventListener("click", () => {
  closeRoleModal();
  pendingCredential = null;
});

$("cancel-phone").addEventListener("click", () => {
  $("phone-modal").classList.add("hidden");
  pendingCredential = null;
});

$("confirm-phone").addEventListener("click", async () => {
  const phone = $("phone-input").value.trim();
  const errorEl = $("phone-error");
  const btn = $("confirm-phone");

  if (!phone) {
    errorEl.textContent = "Please enter your phone number.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (!currentLocation) {
    errorEl.textContent = "Please allow location access to continue.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (!$("customer-consent").checked) {
    errorEl.textContent = "Please confirm you are 18+ and accept the Terms & Privacy Policy.";
    errorEl.classList.remove("hidden");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Signing in...";
  errorEl.classList.add("hidden");

  try {
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        credential: pendingCredential,
        phone,
        city: "",
        consent: true,
        latitude: currentLocation.lat,
        longitude: currentLocation.lng
      })
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      errorEl.textContent = data.error || "Something went wrong, please try again.";
      errorEl.classList.remove("hidden");
      return;
    }

    $("phone-modal").classList.add("hidden");
    showSignedInUI(data);
    lastLocationPush = Date.now();  // sign-in par location already save ho chuki hai
    startLocationUpdates();
    loadNearbyCompanions();  // location mil chuki hai, seedha nearby dikha do

  } catch (err) {
    errorEl.textContent = "Network error — please try again.";
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Continue";
  }
});

// ---------------- SESSION (persistent login) ----------------
function showSignedInUI(data) {
  currentUser = data;
  $("google-btn").classList.add("hidden");
  show($("user-chip"))
  $("user-name").textContent = data.name;
  $("mobile-logout-btn").classList.remove("hidden");
  $("mobile-dashboard-link").classList.remove("hidden");
}

function showSignedOutUI() {
  stopLocationUpdates();
  currentUser = null;
  currentLocation = null;
  $("google-btn").classList.remove("hidden");
  hide($("user-chip"))
  $("mobile-logout-btn").classList.add("hidden");
  $("mobile-dashboard-link").classList.add("hidden");
  $("companion-grid").innerHTML = "";
  $("results-heading").classList.add("hidden");
  $("empty-state").classList.add("hidden");
}

// Server session expire/invalid ho gaya - user ko wapas sign-in state mein le aao
function handleSessionExpired() {
  showSignedOutUI();
  showToast("Session expire ho gaya — please sign in again.", "error");
}

async function restoreSession() {
  try {
    const res = await fetch("/api/me");
    const data = await res.json();
    if (!data.logged_in) return;

    showSignedInUI(data);
    // Fresh location lo + DB mein save karo, phir nearby companions dikhao
    const ok = await pushLocation();
    if (ok) {
      loadNearbyCompanions();
    } else if (currentUser) {
      $("location-status").textContent =
        "Allow location access to see companions near you.";
    }
    startLocationUpdates();
  } catch (err) {
    // network/server issue - user normal sign-in button se aage badh sakta hai
  }
}

async function logoutCustomer() {
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "customer" })
    });
  } catch (err) { /* local UI phir bhi sign-out kar do */ }
  if (window.google && google.accounts && google.accounts.id) {
    google.accounts.id.disableAutoSelect();
  }
  showSignedOutUI();
}

$("logout-btn").addEventListener("click", logoutCustomer);
$("mobile-logout-btn").addEventListener("click", logoutCustomer);

// ---------------- LIVE LOCATION UPDATE (har 5 minute) ----------------
const LOCATION_UPDATE_MS = 5 * 60 * 1000;
let locationTimer = null;
let lastLocationPush = 0;

function getPosition() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
}

// Current location leke DB mein save karta hai. Success par true, warna false.
async function pushLocation() {
  if (!currentUser || !navigator.geolocation) return false;

  let pos;
  try {
    pos = await getPosition();
  } catch (err) {
    return false;  // permission denied / GPS unavailable - agli baar phir try hoga
  }
  currentLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };

  try {
    const res = await fetch("/api/customer/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: currentLocation.lat, longitude: currentLocation.lng })
    });
    if (res.status === 401) { handleSessionExpired(); return false; }
    if (!res.ok) return false;
    lastLocationPush = Date.now();
    return true;
  } catch (err) {
    return false;  // network error - agli baar retry
  }
}

function startLocationUpdates() {
  stopLocationUpdates();
  locationTimer = setInterval(pushLocation, LOCATION_UPDATE_MS);
}

function stopLocationUpdates() {
  if (locationTimer) clearInterval(locationTimer);
  locationTimer = null;
}

// Background tab mein browser timers slow kar deta hai - tab wapas khulne par
// agar 5 minute se zyada ho gaye hain to turant location refresh karo.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && currentUser &&
      Date.now() - lastLocationPush >= LOCATION_UPDATE_MS) {
    pushLocation();
  }
});

// ---------------- LOCATE + SEARCH ----------------
$("locate-btn").addEventListener("click", () => {
  const statusEl = $("location-status");
  statusEl.textContent = "Locating...";

  if (!navigator.geolocation) {
    statusEl.textContent = "Geolocation not supported.";
    return;
  }

  navigator.geolocation.getCurrentPosition(async (pos) => {
    currentLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    statusEl.textContent = "Location found.";
    await loadNearbyCompanions();
  }, () => {
    statusEl.textContent = "Location access denied.";
  });
});

async function loadNearbyCompanions() {
  // Search radius input UI se hata diya gaya hai - backend apna default (4km) use karta hai
  const res = await fetch(`/api/companions/nearby?lat=${currentLocation.lat}&lng=${currentLocation.lng}`);
  const data = await res.json();

  const grid = $("companion-grid");
  const heading = $("results-heading");
  const empty = $("empty-state");
  grid.innerHTML = "";

  if (data.error) { showToast(data.error, "error"); return; }

  if (data.length === 0) {
    heading.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  show(heading)
  $("results-count").textContent = `${data.length} found`;

  data.forEach((c, i) => {
    const verified = c.background_check === "Passed";
    const busy = c.current_status === "Busy";
    const dayStatus = c.day_status || "available";
    const canBook = dayStatus === "available";
    const card = document.createElement("div");
    card.className = "card-enter bg-white rounded-2xl border border-green/10 p-4 sm:p-5 flex flex-col min-w-0";
    card.style.animationDelay = `${i * 60}ms`;
    const initial = (c.full_name || "?").trim().charAt(0).toUpperCase();
    const photoHtml = c.has_photo
      ? `<img src="/api/companions/${c.companion_id}/photo" data-full-photo alt="${esc(c.full_name)}"
           class="companion-photo w-11 h-11 shrink-0 rounded-full object-cover border border-green/10 cursor-pointer hover:opacity-85 hover:ring-2 hover:ring-green/40 transition">`
      : `<div class="w-11 h-11 shrink-0 rounded-full bg-green/10 flex items-center justify-center text-green-dark font-display font-semibold text-sm">${esc(initial)}</div>`;
    const ratingHtml = c.review_count
      ? `<button type="button" class="reviews-btn inline-flex items-center gap-1 text-xs font-medium text-amber-600 hover:underline" data-id="${c.companion_id}" data-name="${esc(c.full_name)}">
           ${starRow(c.avg_rating)} <span>${Number(c.avg_rating).toFixed(1)}</span> <span class="text-ink/40 font-normal">(${Number(c.review_count)})</span></button>`
      : `<span class="text-xs text-ink/40">New &middot; no ratings yet</span>`;
    card.innerHTML = `
      <div class="flex items-start justify-between gap-2 mb-3">
        <div class="flex items-center gap-3 min-w-0">
          ${photoHtml}
          <div class="min-w-0">
            <p class="font-display font-semibold text-lg leading-tight truncate">${esc(c.full_name)}</p>
            <p class="text-xs text-ink/50 mt-1 truncate">${esc(c.city)} &middot; ${c.distance_km} km away</p>
            <div class="mt-1">${ratingHtml}</div>
          </div>
        </div>
        ${verified ? `
        <span class="shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold text-green-dark bg-green-light/25 rounded-full px-2.5 py-1 border border-green/25">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" fill="#1E8449"/><path d="M8.5 12l2.3 2.3L15.5 9.5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Verified
        </span>` : `<span class="shrink-0 text-[10px] text-ink/40">Pending check</span>`}
      </div>
      ${c.service_type || c.skills ? `<p class="text-sm text-ink/70">${[c.service_type, c.skills && `skilled in ${c.skills}`].filter(Boolean).map(esc).join(" &middot; ")}</p>` : ""}
      <div class="mt-3 flex-1">
        <p class="text-[11px] uppercase tracking-wide text-ink/40 mb-1.5">Free today</p>
        ${canBook ? "" : `<p class="mb-2 text-xs font-semibold rounded-lg px-3 py-2 ${dayStatus === "booked" ? "bg-amber-50 text-amber-700 border border-amber-200" : "bg-ink/5 text-ink/60"}">
          ${dayStatus === "booked" ? "Fully booked for today" : "Today's shifts are over"}</p>`}
        <div class="flex flex-wrap gap-1.5">${windowChips(c.free_windows)}</div>
        ${canBook && busy ? `<p class="mt-2 text-[11px] text-amber-700">Abhi ek booking me hai — baad ka slot book kar sakte ho.</p>` : ""}
      </div>
      <div class="flex items-center justify-between gap-3 mt-4 pt-4 border-t border-ink/5">
        <span class="font-display font-semibold text-green-dark">₹${c.hourly_rate}<span class="text-xs font-body font-normal text-ink/40">/hr</span></span>
        <button data-id="${c.companion_id}" data-name="${esc(c.full_name)}" data-rate="${c.hourly_rate}" data-distance="${c.distance_km}" data-shifts="${esc(JSON.stringify(c.shifts || {}))}"
          class="book-btn text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors
            ${canBook ? "bg-green hover:bg-green-dark" : "bg-ink/30 cursor-not-allowed"}"
          ${canBook ? "" : "disabled"}>
          ${canBook ? "Book" : dayStatus === "booked" ? "Fully booked" : "Closed today"}
        </button>
      </div>
    `;
    grid.appendChild(card);
  });

  document.querySelectorAll(".reviews-btn").forEach(btn => {
    btn.addEventListener("click", () => openReviews(btn.dataset.id, btn.dataset.name));
  });

  document.querySelectorAll(".book-btn:not([disabled])").forEach(btn => {
    btn.addEventListener("click", () => openBookingModal(btn.dataset));
  });

  // Photo par tap karke bada/clear view (lightbox)
  document.querySelectorAll(".companion-photo").forEach(img => {
    img.addEventListener("click", () => {
      const lightbox = $("photo-lightbox");
      const lightboxImg = $("lightbox-img");
      lightboxImg.src = img.src;
      lightboxImg.alt = img.alt;
      show(lightbox)
    });
  });
}

$("photo-lightbox").addEventListener("click", () => {
  const lightbox = $("photo-lightbox");
  hide(lightbox)
});

// ---------------- RATING / SHIFT HELPERS ----------------
function starRow(avg) {
  const n = Math.round(Number(avg) || 0);
  return `<span aria-label="${n} out of 5" class="tracking-tight">${"★".repeat(n)}<span class="text-ink/20">${"★".repeat(5 - n)}</span></span>`;
}

// Companion ke aaj ke asli khaali time-slots (server ne booking table se nikale)
function windowChips(windows) {
  if (!windows || !windows.length) return `<span class="text-xs text-ink/40">No free slot left today</span>`;
  return windows.map(([a, b]) => `<span class="inline-flex items-center text-[11px] font-medium border rounded-full px-2.5 py-1 bg-green-light/20 text-green-dark border-green/25">${to12Hour(a)} – ${to12Hour(b)}</span>`).join("");
}

async function openReviews(companionId, name) {
  const modal = $("reviews-modal");
  $("reviews-title").textContent = name;
  $("reviews-summary").textContent = "Loading...";
  $("reviews-list").innerHTML = "";
  show(modal)
  try {
    const res = await fetch(`/api/companions/${companionId}/reviews`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed");
    $("reviews-summary").innerHTML = data.review_count
      ? `<span class="text-amber-600">${starRow(data.avg_rating)}</span> <b>${Number(data.avg_rating).toFixed(1)}</b> &middot; ${data.review_count} rating${data.review_count > 1 ? "s" : ""}`
      : "Abhi koi rating nahi hai.";
    $("reviews-list").innerHTML = data.reviews.map((r) => `
      <div class="border border-ink/10 rounded-xl p-3">
        <div class="flex items-center justify-between text-xs"><span class="font-medium">${esc(r.name)}</span><span class="text-ink/40">${esc(r.date)}</span></div>
        <p class="text-amber-500 text-sm mt-0.5">${"★".repeat(r.rating)}<span class="text-ink/20">${"★".repeat(5 - r.rating)}</span></p>
        ${r.comment ? `<p class="text-sm text-ink/70 mt-1 break-words">${esc(r.comment)}</p>` : ""}
      </div>`).join("");
  } catch (e) {
    $("reviews-summary").textContent = "Reviews load nahi ho paaye.";
  }
}
function closeReviews() {
  const m = $("reviews-modal");
  hide(m)
}
$("reviews-close").addEventListener("click", closeReviews);
$("reviews-modal").addEventListener("click", (e) => { if (e.target.id === "reviews-modal") closeReviews(); });

function showBookingSent(result, start, end) {
  $("success-summary").textContent =
    `Aaj, ${to12Hour(start)} – ${to12Hour(end)} (${shiftLabel(start)} shift) · Total ₹${result.total_amount}`;
  $("success-name").textContent = result.companion_name || "";
  const a = $("success-phone");
  a.textContent = result.companion_phone || "";
  a.href = result.companion_phone ? `tel:${result.companion_phone}` : "#";
  const m = $("success-modal");
  show(m)
}
$("success-close").addEventListener("click", () => {
  const m = $("success-modal");
  hide(m)
});

// ---------------- BOOKING MODAL ----------------
// Bookings ab sirf AAJ ke liye hain, isliye date field hata di gayi hai -
// server bhi hamesha aaj ki hi date use karta hai.
// "Morning"/"Evening" sirf quick-pick shortcuts hain jo start/end time prefill
// karte hain - actual booking hamesha specific start_time/end_time se hi banti hai.
const SHIFT_TIMES = {
  morning: { start: "06:00", end: "14:00" },
  evening: { start: "14:00", end: "22:00" }
};

function nowHHMM() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

// Ek "HH:MM" time Morning shift (before 2 PM) mein aata hai ya Evening mein
function shiftLabel(hhmm) {
  const hour = parseInt(hhmm.split(":")[0], 10);
  return hour < 14 ? "Morning" : "Evening";
}

document.querySelectorAll(".shift-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".shift-btn").forEach(b => b.classList.remove("bg-green/10", "border-green/40", "text-green-dark"));
    btn.classList.add("bg-green/10", "border-green/40", "text-green-dark");

    const shift = SHIFT_TIMES[btn.dataset.shift];
    const startInput = $("booking-start");
    const endInput = $("booking-end");
    // Agar shift ka start abhi ke time se pehle beet chuka hai, to abhi se shuru karo
    const currentTime = nowHHMM();
    startInput.value = shift.start < currentTime ? currentTime : shift.start;
    endInput.value = shift.end;
  });
});

function openBookingModal(data) {
  if (!currentUser) { showToast("Please sign in with Google first.", "error"); return; }
  selectedCompanion = data;
  let shifts = {};
  try { shifts = JSON.parse(data.shifts || "{}"); } catch { shifts = {}; }
  document.querySelectorAll(".shift-btn").forEach(b => {
    const st = shifts[b.dataset.shift] || "available";
    b.disabled = st !== "available";
    b.title = st === "booked" ? "Is shift me companion booked hai" : st === "ended" ? "Ye shift khatam ho chuki hai" : "";
  });
  $("modal-name").textContent = data.name;
  $("modal-rate").textContent = data.rate;
  $("modal-distance").textContent = data.distance;
  $("booking-error").classList.add("hidden");
  document.querySelectorAll(".shift-btn").forEach(b => b.classList.remove("bg-green/10", "border-green/40", "text-green-dark"));

  // Start time ke liye "min" abhi ke time se pehle set nahi ho sakta (aaj hi ke andar)
  const startInput = $("booking-start");
  startInput.min = nowHHMM();
  startInput.value = "";
  $("booking-end").value = "";

  show($("booking-modal"))
}

$("cancel-booking").addEventListener("click", () => {
  $("booking-modal").classList.add("hidden");
});

$("confirm-booking").addEventListener("click", async () => {
  const start = $("booking-start").value;
  const end = $("booking-end").value;
  const errorEl = $("booking-error");
  const confirmBtn = $("confirm-booking");

  if (!start || !end) {
    errorEl.textContent = "Please fill start and end time.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (end <= start) {
    errorEl.textContent = "End time, start time ke baad hona chahiye.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (start < nowHHMM()) {
    errorEl.textContent = "Ye start time already beet chuka hai — aage ka time chuno.";
    errorEl.classList.remove("hidden");
    return;
  }

  errorEl.classList.add("hidden");
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Booking...";

  try {
    const res = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        companion_id: selectedCompanion.id,
        start_time: start + ":00",
        end_time: end + ":00"
      })
    });

    let result;
    try {
      result = await res.json();
    } catch {
      // Server se JSON ki jagah kuch aur aaya (jaise HTML error page) - user ko blank screen
      // dikhne ke bajaye clear message milna chahiye
      throw new Error("Server se unexpected response mila. Please try again.");
    }

    if (res.status === 401) {
      hide($("booking-modal"))
      handleSessionExpired();
      return;
    }

    if (!res.ok || result.error) {
      errorEl.textContent = result.error || "Booking failed. Please try again.";
      errorEl.classList.remove("hidden");
      return;
    }

    hide($("booking-modal"))
    showBookingSent(result, start, end);
    loadNearbyCompanions();

  } catch (err) {
    errorEl.textContent = err.message || "Network error — please check your connection and try again.";
    errorEl.classList.remove("hidden");
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Confirm booking";
  }
});
