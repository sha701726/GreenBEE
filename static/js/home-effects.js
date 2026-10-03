// Purely decorative (hero slider + How-it-works reveal). Booking/search/auth se koi lena-dena nahi.
// Reveals the "How it works" connector line + step nodes once, when scrolled
// into view. This is the ONE deliberate scroll animation on the page - the
// hero's stagger-in (pure CSS, see style.css) is the other.
(() => {
  const stepsSection = document.getElementById("steps");
  if (!stepsSection) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const line = document.getElementById("steps-line");
  const nodes = document.querySelectorAll(".step-node");

  function reveal() {
    if (line) line.classList.add("drawn");
    nodes.forEach(n => n.classList.add("in-view"));
  }

  if (reduceMotion || typeof IntersectionObserver === "undefined") {
    reveal();
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        reveal();
        observer.disconnect();
      }
    });
  }, { threshold: 0.35 });

  observer.observe(stepsSection);

  // Safety net: never leave the steps invisible if the observer somehow
  // doesn't fire (e.g. unusual viewport/layout timing).
  setTimeout(() => { reveal(); observer.disconnect(); }, 3000);
})();

// ---- Hero slider: har 12 sec mein auto-change, swipe (touch/mouse) aur dots se manual ----
// Sirf active (aur agli) slide ki image load hoti hai - baaki display:none rehti hain (data bachta hai).
(() => {
  const hero = $("hero");
  if (!hero) return;
  const frame = hero.querySelector(".hero-frame");
  const slides = hero.querySelectorAll(".hero-slide");
  const dots = hero.querySelectorAll(".hero-dot");
  if (slides.length < 2) return;

  const INTERVAL_MS = 12000, FADE_MS = 1000, SWIPE_PX = 50;
  const at = (i) => (i + slides.length) % slides.length;
  let cur = 0, timer = null, startX = null, startY = 0;

  const preload = (i) => { slides[at(i)].querySelector("img").loading = "eager"; };

  function go(i) {
    const prev = slides[cur], next = slides[at(i)];
    if (prev === next) return;
    cur = at(i);
    next.classList.add("show");
    void next.offsetWidth;                       // display badalne ke baad reflow, taaki fade chale
    next.classList.add("on");
    prev.classList.remove("on");
    setTimeout(() => { if (prev !== slides[cur]) prev.classList.remove("show"); }, FADE_MS + 50);
    dots.forEach((d, n) => d.classList.toggle("on", n === cur));
    preload(cur + 1);
    play();                                      // manual change par 12 sec ka timer dobara shuru
  }
  function play() {
    clearInterval(timer);
    if (!document.hidden) timer = setInterval(() => go(cur + 1), INTERVAL_MS);
  }

  dots.forEach((d, i) => d.addEventListener("click", () => { preload(i); go(i); }));
  document.addEventListener("visibilitychange", play);

  frame.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    startX = e.clientX; startY = e.clientY;
  });
  frame.addEventListener("pointerup", (e) => {
    if (startX === null) return;
    const dx = e.clientX - startX, dy = e.clientY - startY;
    startX = null;
    if (Math.abs(dx) >= SWIPE_PX && Math.abs(dx) > Math.abs(dy)) { const to = cur + (dx < 0 ? 1 : -1); preload(to); go(to); }
  });
  frame.addEventListener("pointercancel", () => { startX = null; });
  preload(1);
  play();
})();
