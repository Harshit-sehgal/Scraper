/* ─── Landing page bootstrap ────────────────────────── */

import { hydrateIcons, startIconObserver } from "/js/icons.js";
import { initTheme } from "/js/utils.js";

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  hydrateIcons();
  startIconObserver();

  // Smooth-scroll anchor links
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
});
