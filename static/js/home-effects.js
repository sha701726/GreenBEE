// Purely decorative. Does not touch any booking/search/auth functionality.
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
