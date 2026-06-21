/* ═══════════════════════════════════════════
   DataForge — Settings Page
   ═══════════════════════════════════════════ */

import { API } from "./api.js";
import { toast } from "./utils.js";

const THEME_KEY = "dataforge_theme_v1";

export function refreshSettingsPage() {
  // API URL
  const apiUrl = document.getElementById("settings-api-url");
  if (apiUrl) {
    apiUrl.textContent = API;
  }

  // Theme mode
  const saved = localStorage.getItem(THEME_KEY);
  const currentMode = saved || "system";
  const toggles = document.querySelectorAll("#settings-theme-toggle .toggle");
  toggles.forEach((t) => {
    t.classList.toggle("active", t.dataset.mode === currentMode);
  });
}

export function setThemeMode(mode) {
  if (mode === "system") {
    localStorage.removeItem(THEME_KEY);
    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (isDark) {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    toast("Theme: System", "info");
  } else if (mode === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    try {
      localStorage.setItem(THEME_KEY, "dark");
    } catch {
      // localStorage not available
    }
    toast("Theme: Dark", "info");
  } else {
    document.documentElement.removeAttribute("data-theme");
    try {
      localStorage.setItem(THEME_KEY, "light");
    } catch {
      // localStorage not available
    }
    toast("Theme: Light", "info");
  }

  // Update the theme toggle icon in topbar
  const btn = document.getElementById("btn-theme-toggle");
  if (btn) {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const iconSpan = btn.querySelector("[data-icon]");
    if (iconSpan) {
      iconSpan.setAttribute("data-icon", isDark ? "sun" : "moon");
    }
  }

  refreshSettingsPage();
}
