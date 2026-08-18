/* ─── Landing page bootstrap ──────────────────────────
   DataForge — scroll reveals, nav scroll transition,
   mobile menu toggle, icon hydration.                */

import { hydrateIcons, startIconObserver } from "/app/js/icons.js?v=5";
import { initTheme } from "/app/js/utils.js?v=5";

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

  // ─── Self-service signup (POST /api/saas/signup) ───

  const signupForm = document.getElementById("signup-form");
  if (signupForm) {
    const errorEl = document.getElementById("signup-error");
    const submitBtn = document.getElementById("signup-submit");

    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (errorEl) errorEl.style.display = "none";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Creating account…";
      }

      const formData = new FormData(signupForm);
      const payload = {
        email: String(formData.get("email") || "").trim(),
        password: String(formData.get("password") || ""),
        display_name: String(formData.get("display_name") || "").trim(),
        org_name: String(formData.get("org_name") || "").trim() || null,
      };

      try {
        const resp = await fetch("/api/saas/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
          throw new Error(detail || `Signup failed (HTTP ${resp.status})`);
        }
        window.location.href = "/app/";
      } catch (err) {
        if (errorEl) {
          errorEl.textContent = err instanceof Error ? err.message : "Signup failed. Please try again.";
          errorEl.style.display = "block";
        }
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Create account";
        }
      }
    });
  }
});
