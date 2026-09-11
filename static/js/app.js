let currentUser = null;      // { customer_id, name }
let currentLocation = null;  // { lat, lng }
let selectedCompanion = null;
let pendingCredential = null; // Google token, phone-modal confirm hone tak yahan hold hota hai

// ---------------- GOOGLE SIGN-IN ----------------
window.onload = () => {
  google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: handleGoogleCredential
  });
  google.accounts.id.renderButton(document.getElementById("google-btn"), { theme: "outline", size: "medium" });
};

function handleGoogleCredential(response) {
  pendingCredential = response.credential;
  document.getElementById("phone-input").value = "";
  document.getElementById("phone-error").classList.add("hidden");
  document.getElementById("phone-modal").classList.remove("hidden");
  document.getElementById("phone-modal").classList.add("flex");
  document.getElementById("phone-input").focus();
}

document.getElementById("cancel-phone").addEventListener("click", () => {
  document.getElementById("phone-modal").classList.add("hidden");
  pendingCredential = null;
});

document.getElementById("confirm-phone").addEventListener("click", async () => {
  const phone = document.getElementById("phone-input").value.trim();
  const errorEl = document.getElementById("phone-error");
  const btn = document.getElementById("confirm-phone");

  if (!phone) {
    errorEl.textContent = "Please enter your phone number.";
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
        latitude: currentLocation ? currentLocation.lat : null,
        longitude: currentLocation ? currentLocation.lng : null
      })
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      errorEl.textContent = data.error || "Something went wrong, please try again.";
      errorEl.classList.remove("hidden");
      return;
    }

    currentUser = data;
    document.getElementById("phone-modal").classList.add("hidden");
    document.getElementById("google-btn").classList.add("hidden");
    document.getElementById("user-chip").classList.remove("hidden");
    document.getElementById("user-chip").classList.add("flex");
    document.getElementById("user-name").textContent = data.name;

  } catch (err) {
    errorEl.textContent = "Network error — please try again.";
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Continue";
  }
});

// ---------------- LOCATE + SEARCH ----------------
document.getElementById("locate-btn").addEventListener("click", () => {
  const statusEl = document.getElementById("location-status");
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

  const grid = document.getElementById("companion-grid");
  const heading = document.getElementById("results-heading");
  const empty = document.getElementById("empty-state");
  grid.innerHTML = "";

  if (data.error) { alert(data.error); return; }

  if (data.length === 0) {
    heading.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  heading.classList.remove("hidden");
  heading.classList.add("flex");
  document.getElementById("results-count").textContent = `${data.length} found`;

  data.forEach((c, i) => {
    const verified = c.background_check === "Passed";
    const busy = c.current_status === "Busy";
    const card = document.createElement("div");
    card.className = "card-enter bg-white rounded-2xl border border-green/10 p-5 flex flex-col";
    card.style.animationDelay = `${i * 60}ms`;
    const initial = (c.full_name || "?").trim().charAt(0).toUpperCase();
    const photoHtml = c.has_photo
      ? `<img src="/api/companions/${c.companion_id}/photo" data-full-photo alt="${c.full_name}"
           class="companion-photo w-11 h-11 rounded-full object-cover border border-green/10 cursor-pointer hover:opacity-85 hover:ring-2 hover:ring-green/40 transition">`
      : `<div class="w-11 h-11 rounded-full bg-green/10 flex items-center justify-center text-green-dark font-display font-semibold text-sm">${initial}</div>`;
    card.innerHTML = `
      <div class="flex items-start justify-between mb-3">
        <div class="flex items-center gap-3">
          ${photoHtml}
          <div>
            <p class="font-display font-semibold text-lg leading-none">${c.full_name}</p>
            <p class="text-xs text-ink/50 mt-1">${c.city} &middot; ${c.distance_km} km away</p>
          </div>
        </div>
        ${verified ? `
        <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-green-dark bg-green-light/25 rounded-full px-2.5 py-1 border border-green/25">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" fill="#1E8449"/><path d="M8.5 12l2.3 2.3L15.5 9.5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Verified
        </span>` : `<span class="text-[10px] text-ink/40">Pending check</span>`}
      </div>
      <p class="text-sm text-ink/70 flex-1">${c.service_type || "Companion service"} &middot; skilled in ${c.skills || "self-defense"}</p>
      <p class="mt-3">
        <span class="inline-flex items-center gap-1.5 text-[11px] font-semibold rounded-full px-2.5 py-1
          ${busy ? "bg-amber-100 text-amber-700" : "bg-green-light/20 text-green-dark"}">
          <span class="w-1.5 h-1.5 rounded-full ${busy ? "bg-amber-500" : "bg-green"}"></span>
          ${busy ? "Busy right now" : "Available now"}
        </span>
      </p>
      <div class="flex items-center justify-between mt-4 pt-4 border-t border-ink/5">
        <span class="font-display font-semibold text-green-dark">₹${c.hourly_rate}<span class="text-xs font-body font-normal text-ink/40">/hr</span></span>
        <button data-id="${c.companion_id}" data-name="${c.full_name}" data-rate="${c.hourly_rate}" data-distance="${c.distance_km}"
          class="book-btn text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors
            ${busy ? "bg-ink/30 cursor-not-allowed" : "bg-green hover:bg-green-dark"}"
          ${busy ? "disabled title=\"Currently busy in a booking\"" : ""}>
          ${busy ? "Busy" : "Book"}
        </button>
      </div>
    `;
    grid.appendChild(card);
  });

  document.querySelectorAll(".book-btn:not([disabled])").forEach(btn => {
    btn.addEventListener("click", () => openBookingModal(btn.dataset));
  });

  // Photo par tap karke bada/clear view (lightbox)
  document.querySelectorAll(".companion-photo").forEach(img => {
    img.addEventListener("click", () => {
      const lightbox = document.getElementById("photo-lightbox");
      const lightboxImg = document.getElementById("lightbox-img");
      lightboxImg.src = img.src;
      lightboxImg.alt = img.alt;
      lightbox.classList.remove("hidden");
      lightbox.classList.add("flex");
    });
  });
}

document.getElementById("photo-lightbox").addEventListener("click", () => {
  const lightbox = document.getElementById("photo-lightbox");
  lightbox.classList.add("hidden");
  lightbox.classList.remove("flex");
});

// ---------------- TOAST ----------------
// alert() ke bajaye ye use karo - kai mobile/webview browsers alert()/confirm() ko
// silently block ya suppress kar dete hain, jisse user ko koi feedback hi nahi milta.
let toastTimer = null;
function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `fixed bottom-5 left-1/2 -translate-x-1/2 z-[80] max-w-sm w-[calc(100%-2rem)] rounded-xl shadow-lg px-4 py-3 text-sm font-medium text-white ${
    type === "error" ? "bg-red-600" : "bg-green-dark"
  }`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 5000);
}

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

// 24-hour "HH:MM" ko readable 12-hour AM/PM mein convert karta hai
function to12Hour(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${period}`;
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
    const startInput = document.getElementById("booking-start");
    const endInput = document.getElementById("booking-end");
    // Agar shift ka start abhi ke time se pehle beet chuka hai, to abhi se shuru karo
    const currentTime = nowHHMM();
    startInput.value = shift.start < currentTime ? currentTime : shift.start;
    endInput.value = shift.end;
  });
});

function openBookingModal(data) {
  if (!currentUser) { alert("Please sign in with Google first."); return; }
  selectedCompanion = data;
  document.getElementById("modal-name").textContent = data.name;
  document.getElementById("modal-rate").textContent = data.rate;
  document.getElementById("modal-distance").textContent = data.distance;
  document.getElementById("booking-error").classList.add("hidden");
  document.querySelectorAll(".shift-btn").forEach(b => b.classList.remove("bg-green/10", "border-green/40", "text-green-dark"));

  // Start time ke liye "min" abhi ke time se pehle set nahi ho sakta (aaj hi ke andar)
  const startInput = document.getElementById("booking-start");
  startInput.min = nowHHMM();
  startInput.value = "";
  document.getElementById("booking-end").value = "";

  document.getElementById("booking-modal").classList.remove("hidden");
  document.getElementById("booking-modal").classList.add("flex");
}

document.getElementById("cancel-booking").addEventListener("click", () => {
  document.getElementById("booking-modal").classList.add("hidden");
});

document.getElementById("confirm-booking").addEventListener("click", async () => {
  const start = document.getElementById("booking-start").value;
  const end = document.getElementById("booking-end").value;
  const errorEl = document.getElementById("booking-error");
  const confirmBtn = document.getElementById("confirm-booking");

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
        customer_id: currentUser.customer_id,
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

    if (!res.ok || result.error) {
      errorEl.textContent = result.error || "Booking failed. Please try again.";
      errorEl.classList.remove("hidden");
      return;
    }

    document.getElementById("booking-modal").classList.add("hidden");
    document.getElementById("booking-modal").classList.remove("flex");
    showToast(`Booking confirmed for today (${shiftLabel(start)} shift), ${to12Hour(start)} – ${to12Hour(end)}! Total: ₹${result.total_amount}`);
    loadNearbyCompanions();

  } catch (err) {
    errorEl.textContent = err.message || "Network error — please check your connection and try again.";
    errorEl.classList.remove("hidden");
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Confirm booking";
  }
});
