let googleCredential = null;

// ---------------- GOOGLE SIGN-IN ----------------
window.onload = () => {
  google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: handleGoogleCredential
  });
  google.accounts.id.renderButton(document.getElementById("google-btn"), { theme: "outline", size: "medium" });
};

function handleGoogleCredential(response) {
  googleCredential = response.credential;

  // decode just the email for display - server independently verifies the real token
  const payload = JSON.parse(atob(response.credential.split(".")[1]));

  document.getElementById("google-btn").classList.add("hidden");
  document.getElementById("verified-email-text").textContent = payload.email;
  document.getElementById("verified-email-chip").classList.remove("hidden");
  document.getElementById("verified-email-chip").classList.add("inline-flex");
}

// ---------------- PHOTO PREVIEW ----------------
document.getElementById("photo-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  const preview = document.getElementById("photo-preview");
  if (!file) {
    preview.classList.add("hidden");
    return;
  }
  preview.src = URL.createObjectURL(file);
  preview.classList.remove("hidden");
});

// ---------------- LOCATION ----------------
document.getElementById("detect-location-btn").addEventListener("click", () => {
  const statusEl = document.getElementById("location-status");
  statusEl.textContent = "Locating...";

  if (!navigator.geolocation) {
    statusEl.textContent = "Geolocation not supported by this browser.";
    return;
  }

  navigator.geolocation.getCurrentPosition((pos) => {
    document.getElementById("latitude-input").value = pos.coords.latitude;
    document.getElementById("longitude-input").value = pos.coords.longitude;
    statusEl.textContent = `Location set (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`;
  }, () => {
    statusEl.textContent = "Location access denied.";
  });
});

// ---------------- FORM SUBMIT ----------------
document.getElementById("companion-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const form = e.target;
  const messageEl = document.getElementById("form-message");
  const submitBtn = form.querySelector("button[type=submit]");

  if (!googleCredential) {
    messageEl.textContent = "Please verify your email with Google first.";
    messageEl.className = "text-sm text-red-600";
    messageEl.classList.remove("hidden");
    return;
  }

  if (!document.getElementById("latitude-input").value) {
    messageEl.textContent = "Please detect your location first.";
    messageEl.className = "text-sm text-red-600";
    messageEl.classList.remove("hidden");
    return;
  }

  if (!form.querySelector('input[name="consent"]').checked) {
    messageEl.textContent = "Please confirm you are 18+ and accept the Terms & Privacy Policy.";
    messageEl.className = "text-sm text-red-600";
    messageEl.classList.remove("hidden");
    return;
  }

  const formData = new FormData(form);
  formData.set("credential", googleCredential);

  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting...";
  messageEl.classList.add("hidden");

  try {
    // FormData seedha bhejo (multipart/form-data) - JSON.stringify() File ko
    // serialize nahi kar sakta, isliye Content-Type header bhi manually set nahi karte
    // (browser khud sahi multipart boundary set karega).
    const res = await fetch("/api/companions", {
      method: "POST",
      body: formData
    });
    const result = await res.json();

    if (!res.ok) {
      messageEl.textContent = result.error || "Something went wrong, try again.";
      messageEl.className = "text-sm text-red-600";
      messageEl.classList.remove("hidden");
      return;
    }

    messageEl.textContent = "✅ Registered! Our team will verify your profile before it goes live. ";
    messageEl.className = "text-sm text-green-dark font-medium";
    // Server ne session bana diya hai - seedha apne availability page par ja sakte hain
    const statusLink = document.createElement("a");
    statusLink.href = `/companion/status/${result.companion_id}`;
    statusLink.textContent = "Go to my availability page →";
    statusLink.className = "underline";
    messageEl.appendChild(statusLink);
    messageEl.classList.remove("hidden");
    form.reset();
    document.getElementById("location-status").textContent = "";
    document.getElementById("photo-preview").classList.add("hidden");

  } catch (err) {
    messageEl.textContent = "Network error — please check your connection and try again.";
    messageEl.className = "text-sm text-red-600";
    messageEl.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit registration";
  }
});
