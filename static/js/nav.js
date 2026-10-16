// Navbar behaviour (index page):
//  1) "#about", "#services" jaise links par click karne par smooth scroll hota hai
//     lekin URL mein "#..." add NAHI hota (preventDefault + history touch nahi karte).
//     Header offset CSS ke scroll-padding-top se handle hota hai (style.css).
//  2) Mobile/tablet par hamburger menu open/close.
(() => {
  const menuBtn = document.getElementById("menu-btn");
  const menu = document.getElementById("mobile-menu");

  function setMenu(open) {
    if (!menu || !menuBtn) return;
    menu.classList.toggle("hidden", !open);
    menuBtn.setAttribute("aria-expanded", String(open));
    menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }

  if (menuBtn && menu) {
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      setMenu(menu.classList.contains("hidden"));
    });

    // Menu ke bahar click / Escape / desktop size par jaane par menu band
    document.addEventListener("click", (e) => {
      if (!menu.classList.contains("hidden") && !menu.contains(e.target)) setMenu(false);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });
    window.matchMedia("(min-width: 1024px)").addEventListener("change", (e) => { if (e.matches) setMenu(false); });
  }

  // In-page links: scroll karo, par URL mein hash mat daalo
  document.addEventListener("click", (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;

    const id = link.getAttribute("href").slice(1);
    const target = id ? document.getElementById(id) : null;
    if (!target) return;

    e.preventDefault();
    setMenu(false);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });

    // Keyboard/screen-reader users ke liye focus bhi target par le jao ("Skip to content" link ke liye zaroori)
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  // Agar koi purana "#about" wala link kholkar aaya ho to address bar se hash hata do
  if (window.location.hash) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
})();
