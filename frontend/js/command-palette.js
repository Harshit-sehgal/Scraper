/* ═══════════════════════════════════════════
   DataForge — Command Palette (Ctrl+K)
   Notion-style quick navigation
   ═══════════════════════════════════════════ */

import { switchView } from "./views.js";
import { hydrateIcons } from "./icons.js";

const COMMANDS = [
  { id: "nav-jobs", label: "Go to Jobs", view: "jobs", category: "Navigation" },
  { id: "nav-new", label: "Create New Job", view: "new", category: "Navigation" },
  { id: "nav-dashboard", label: "Go to Dashboard", view: "dashboard", category: "Navigation" },
  { id: "nav-api-keys", label: "Go to API Keys", view: "api-keys", category: "Navigation" },
  { id: "nav-settings", label: "Go to Settings", view: "settings", category: "Navigation" },
  { id: "nav-workflows", label: "Go to Workflows", view: "workflows", category: "Navigation" },
  { id: "nav-auth-profiles", label: "Go to Auth Profiles", view: "auth-profiles", category: "Navigation" },
  { id: "nav-billing", label: "Go to Billing", view: "billing", category: "Navigation" },
  { id: "nav-audit", label: "Go to Audit Log", view: "audit", category: "Navigation" },
  { id: "nav-retention", label: "Go to Data Retention", view: "retention", category: "Navigation" },
  { id: "nav-recycle", label: "Go to Recycle Bin", view: "recycle", category: "Navigation" },
];

let selectedIndex = 0;

function getOverlay() {
  return document.getElementById("command-palette-overlay");
}

function getInput() {
  return document.getElementById("command-palette-input");
}

function getResults() {
  return document.getElementById("command-palette-results");
}

function filterCommands(query) {
  if (!query.trim()) return COMMANDS;
  const q = query.toLowerCase();
  return COMMANDS.filter((c) => c.label.toLowerCase().includes(q) || c.category.toLowerCase().includes(q));
}

function renderResults(commands) {
  const results = getResults();
  if (!results) return;

  if (!commands.length) {
    results.innerHTML = '<div class="command-palette-hint">No results found</div>';
    return;
  }

  selectedIndex = Math.min(selectedIndex, commands.length - 1);
  selectedIndex = Math.max(0, selectedIndex);

  let currentCategory = "";
  let html = "";

  commands.forEach((cmd, i) => {
    if (cmd.category !== currentCategory) {
      currentCategory = cmd.category;
      html += `<div class="command-palette-category">${currentCategory}</div>`;
    }
    const isSelected = i === selectedIndex;
    html += `<button
      type="button"
      class="command-palette-item${isSelected ? " selected" : ""}"
      data-command-id="${cmd.id}"
      data-view="${cmd.view || ""}"
    >
      <span data-icon="arrowRight" aria-hidden="true" class="command-palette-item-icon"></span>
      <span class="command-palette-item-label">${cmd.label}</span>
    </button>`;
  });

  results.innerHTML = html;

  // Hydrate icons in results
  requestAnimationFrame(() => hydrateIcons());

  // Attach click handlers
  results.querySelectorAll(".command-palette-item").forEach((item) => {
    item.addEventListener("click", () => {
      const view = item.getAttribute("data-view");
      if (view) {
        switchView(view);
        closeCommandPalette();
      }
    });
  });
}

export function openCommandPalette() {
  const overlay = getOverlay();
  const input = getInput();
  if (!overlay || !input) return;

  selectedIndex = 0;
  input.value = "";
  overlay.classList.remove("hidden");
  renderResults(COMMANDS);
  setTimeout(() => input.focus(), 50);
}

export function closeCommandPalette() {
  const overlay = getOverlay();
  if (overlay) overlay.classList.add("hidden");
}

function handleInput() {
  const input = getInput();
  if (!input) return;
  const query = input.value;
  const filtered = filterCommands(query);
  selectedIndex = 0;
  renderResults(filtered);
}

function handleKeydown(e) {
  const input = getInput();
  if (!input) return;

  const filtered = filterCommands(input.value);

  if (e.key === "ArrowDown") {
    e.preventDefault();
    selectedIndex = (selectedIndex + 1) % Math.max(1, filtered.length);
    renderResults(filtered);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    selectedIndex = (selectedIndex - 1 + Math.max(1, filtered.length)) % Math.max(1, filtered.length);
    renderResults(filtered);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (filtered[selectedIndex]) {
      switchView(filtered[selectedIndex].view);
      closeCommandPalette();
    }
  } else if (e.key === "Escape") {
    e.preventDefault();
    closeCommandPalette();
  }
}

// Initialize event listeners
document.addEventListener("DOMContentLoaded", () => {
  const input = getInput();
  if (input) {
    input.addEventListener("input", handleInput);
    input.addEventListener("keydown", handleKeydown);
  }

  // Close on backdrop click
  const overlay = getOverlay();
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeCommandPalette();
    });
  }
});
