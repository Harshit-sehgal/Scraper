/* ─── Landing page bootstrap ──────────────────────────
   Dataforge — scroll reveals, nav scroll transition,
   mobile menu toggle, icon hydration.                */

import { hydrateIcons, startIconObserver } from "/js/icons.js";
import { initTheme } from "/js/utils.js";

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  hydrateIcons();
  startIconObserver();

  // ─── Smooth-scroll anchor links ───

  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        // Close mobile menu if open
        closeMobileMenu();
      }
    });
  });

  // ─── Navbar scroll transition ───

  const nav = document.getElementById("landing-nav");
  if (nav) {
    const onScroll = () => {
      nav.classList.toggle("scrolled", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ─── Scroll-triggered reveal animations ───

  const revealEls = document.querySelectorAll(".reveal");

  if (revealEls.length && "IntersectionObserver" in window) {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced) {
      // Show everything immediately if user prefers reduced motion
      revealEls.forEach((el) => el.classList.add("visible"));
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
      );

      revealEls.forEach((el) => observer.observe(el));
    }
  } else {
    // Fallback: show everything
    revealEls.forEach((el) => el.classList.add("visible"));
  }

  // ─── Mobile menu toggle ───

  const menuToggle = document.getElementById("mobile-menu-toggle");
  const navLinks = document.getElementById("nav-links");

  function closeMobileMenu() {
    if (menuToggle && navLinks) {
      menuToggle.classList.remove("open");
      menuToggle.setAttribute("aria-expanded", "false");
      navLinks.classList.remove("open");
    }
  }

  if (menuToggle && navLinks) {
    menuToggle.addEventListener("click", () => {
      const isOpen = navLinks.classList.toggle("open");
      menuToggle.classList.toggle("open", isOpen);
      menuToggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  // Close menu when clicking a nav link (mobile)
  if (navLinks) {
    navLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeMobileMenu);
    });
  }
});
