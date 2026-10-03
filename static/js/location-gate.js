// Location gate: website par jo bhi aaye, location permission dene tak site use nahi kar sakta.
// Sab pages par (base.html se) chalta hai. Permission milte hi overlay hat jaata hai.
// Note: browser permission zabardasti allow nahi karwa sakte - user deny kare to overlay
// ruka rehta hai aur "browser settings me allow karo" instructions dikhte hain.
(() => {
  const gate = document.getElementById("location-gate");
  if (!gate) return;

  const msgEl = document.getElementById("lg-msg");
  const helpEl = document.getElementById("lg-help");
  const btn = document.getElementById("lg-btn");
  let locked = true;
  let busy = false;
  const inerted = [];

  function lockPage() {
    document.documentElement.classList.add("lg-locked");
    gate.hidden = false;
    // Keyboard/screen-reader se peeche ka content access na ho
    Array.from(document.body.children).forEach((el) => {
      if (el === gate || el.tagName === "SCRIPT" || el.tagName === "NOSCRIPT") return;
      if (!el.inert) { el.inert = true; inerted.push(el); }
    });
  }

  function unlockPage() {
    locked = false;
    document.documentElement.classList.remove("lg-locked");
    gate.hidden = true;
    inerted.forEach((el) => { el.inert = false; });
    inerted.length = 0;
  }

  function show(message, help, btnLabel) {
    msgEl.textContent = message;
    helpEl.textContent = help || "";
    helpEl.hidden = !help;
    btn.textContent = btnLabel || "Allow location";
    btn.disabled = false;
    busy = false;
  }

  const DENIED_HELP =
    "Browser ke address bar me lock/location icon par click karo → Location ko \"Allow\" karo → " +
    "phir page reload karo ya neeche button dabao.";

  function requestLocation(force) {
    if (busy && force !== true) return;

    if (!window.isSecureContext) {
      show("Location sirf secure (HTTPS) connection par kaam karti hai.",
           "Site ko https:// ya localhost par kholo.", "Retry");
      return;
    }
    if (!navigator.geolocation) {
      show("Ye browser location support nahi karta.",
           "Kisi doosre browser (Chrome/Edge/Safari) me kholo.", "Retry");
      return;
    }

    busy = true;
    btn.disabled = true;
    btn.textContent = "Checking location...";

    navigator.geolocation.getCurrentPosition(
      () => { busy = false; unlockPage(); },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          show("Location access blocked hai. GreenBEE use karne ke liye location allow karna zaroori hai.",
               DENIED_HELP, "Try again");
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          show("Location detect nahi ho pa rahi.",
               "Device ki location/GPS on karo aur phir try karo.", "Try again");
        } else {
          show("Location milne me time lag gaya.",
               "Internet/GPS check karke phir try karo.", "Try again");
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
  }

  btn.addEventListener("click", () => requestLocation());

  lockPage();
  show("GreenBEE aapke aas-paas ke companions dikhane ke liye aapki location use karta hai. " +
       "Aage badhne ke liye location allow karna zaroori hai.", "", "Allow location");

  // Permission status badalte hi (jaise settings se allow karne par) apne aap re-check
  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions.query({ name: "geolocation" }).then((status) => {
      const react = () => {
        if (!locked) return;
        if (status.state === "granted") requestLocation(true);
        else if (status.state === "prompt") requestLocation();
        else show("Location access blocked hai. GreenBEE use karne ke liye location allow karna zaroori hai.",
                  DENIED_HELP, "Try again");
      };
      status.onchange = react;
      react();  // page load par: granted -> seedha unlock, prompt -> browser popup, denied -> instructions
    }).catch(() => requestLocation());
  } else {
    requestLocation();
  }
})();
