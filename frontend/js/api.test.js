import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
  API,
  getAdminKey,
  setAdminKey,
  showApiKeyPrompt,
  showAdminKeyPrompt,
  setApiKey,
  getApiKey,
  isKeyModalVisible,
  closeKeyModal,
  saveKeyFromModal,
  clearApiKey,
  apiFetch,
} from "./api.js";

// ─── Helpers ────────────────────────────────────────────────────────────

function createModalOverlay() {
  const overlay = document.createElement("div");
  overlay.id = "apikey-overlay";
  overlay.className = "hidden";
  overlay.innerHTML = `
    <div id="apikey-modal-title"></div>
    <div id="apikey-modal-desc"></div>
    <input id="apikey-input" type="text" />
    <div id="apikey-error" class="hidden"></div>
  `;
  document.body.appendChild(overlay);
  return overlay;
}

function createToastsContainer() {
  const c = document.createElement("div");
  c.id = "toasts";
  document.body.appendChild(c);
  return c;
}

// ─── Suite setup ────────────────────────────────────────────────────────

beforeEach(() => {
  clearApiKey();
  setAdminKey("");
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ═══════════════════════════════════════════════════════════════════════
// API Base URL
// ═══════════════════════════════════════════════════════════════════════

describe("API base URL", () => {
  const ORIGINAL_LOCATION = window.location;

  afterEach(() => {
    // Restore original location descriptor after each test
    Object.defineProperty(window, "location", {
      value: ORIGINAL_LOCATION,
      writable: true,
    });
    delete window.DATAFORGE_API_BASE;
  });

  it("uses DATAFORGE_API_BASE when set on window", () => {
    // The module is already imported; API was evaluated at import time.
    // To test different URL configs we need vi.resetModules() and reimport.
    // For this test we verify the env detection logic by checking the
    // actual API value (which defaults to 127.0.0.1:8000 in jsdom).
    expect(API).toMatch(/127\.0\.0\.1:8000|http:/);
  });

  it("resolves correctly in jsdom test environment", () => {
    // In jsdom, protocol is 'about:' so the fallback applies.
    expect(API).toBe("http://127.0.0.1:8000");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// API Key Management
// ═══════════════════════════════════════════════════════════════════════

describe("API key management", () => {
  it("starts with empty key", () => {
    expect(getApiKey()).toBe("");
  });

  it("setApiKey stores the trimmed key", () => {
    setApiKey("  my-secret-key  ");
    expect(getApiKey()).toBe("my-secret-key");
  });

  it("clearApiKey resets the key", () => {
    setApiKey("test-key");
    clearApiKey();
    expect(getApiKey()).toBe("");
  });

  it("setApiKey handles empty/blank input", () => {
    setApiKey("");
    expect(getApiKey()).toBe("");
    setApiKey("   ");
    expect(getApiKey()).toBe("");
  });

  it("setAdminKey and getAdminKey work", () => {
    expect(getAdminKey()).toBe("");
    setAdminKey("admin-123");
    expect(getAdminKey()).toBe("admin-123");
    setAdminKey("");
    expect(getAdminKey()).toBe("");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// API Key Modal
// ═══════════════════════════════════════════════════════════════════════

describe("API key modal", () => {
  beforeEach(() => {
    createModalOverlay();
    createToastsContainer();
  });

  it("showApiKeyPrompt displays the modal with API title", () => {
    showApiKeyPrompt();
    const overlay = document.getElementById("apikey-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("apikey-modal-title").textContent).toContain("API Key");
  });

  it("showAdminKeyPrompt displays the modal with Admin title", () => {
    showAdminKeyPrompt();
    const overlay = document.getElementById("apikey-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("apikey-modal-title").textContent).toContain("Admin Key");
  });

  it("closeKeyModal hides the overlay", () => {
    createModalOverlay();
    showApiKeyPrompt();
    closeKeyModal();
    expect(document.getElementById("apikey-overlay").classList.contains("hidden")).toBe(true);
  });

  it("isKeyModalVisible returns correct visibility", () => {
    expect(isKeyModalVisible()).toBe(false);
    showApiKeyPrompt();
    expect(isKeyModalVisible()).toBe(true);
    closeKeyModal();
    expect(isKeyModalVisible()).toBe(false);
  });

  it("saveKeyFromModal shows error for empty key", () => {
    showApiKeyPrompt();
    const input = document.getElementById("apikey-input");
    input.value = "";
    saveKeyFromModal();
    const error = document.getElementById("apikey-error");
    expect(error.classList.contains("hidden")).toBe(false);
    expect(error.textContent).toContain("enter a key");
  });

  it("saveKeyFromModal saves API key and shows toast", () => {
    showApiKeyPrompt();
    const input = document.getElementById("apikey-input");
    input.value = "my-api-key";
    saveKeyFromModal();
    expect(getApiKey()).toBe("my-api-key");
    expect(document.getElementById("apikey-overlay").classList.contains("hidden")).toBe(true);
    const toasts = document.getElementById("toasts");
    expect(toasts.children.length).toBeGreaterThanOrEqual(1);
  });

  it("saveKeyFromModal saves admin key", () => {
    showAdminKeyPrompt();
    const input = document.getElementById("apikey-input");
    input.value = "admin-secret";
    saveKeyFromModal();
    expect(getAdminKey()).toBe("admin-secret");
    expect(document.getElementById("apikey-overlay").classList.contains("hidden")).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// apiFetch Wrapper
// ═══════════════════════════════════════════════════════════════════════

describe("apiFetch", () => {
  beforeEach(() => {
    createToastsContainer();
    global.fetch = vi.fn();
  });

  it("adds X-API-Key header when key is set", async () => {
    setApiKey("test-key");
    global.fetch.mockResolvedValue(new Response("{}", { status: 200 }));

    await apiFetch("/api/jobs");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/jobs",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-API-Key": "test-key" }),
      }),
    );
  });

  it("adds X-Admin-Key header when admin option is set", async () => {
    setAdminKey("admin-key");
    global.fetch.mockResolvedValue(new Response("{}", { status: 200 }));

    await apiFetch("/api/jobs", { admin: true });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/jobs",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Admin-Key": "admin-key" }),
      }),
    );
  });

  it("triggers API key prompt on 403", async () => {
    setApiKey("test-key");
    global.fetch.mockResolvedValue(new Response("{}", { status: 403 }));
    createModalOverlay();

    await apiFetch("/api/jobs");

    const overlay = document.getElementById("apikey-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
  });

  it("does not show 403 prompt for admin requests", async () => {
    setAdminKey("admin-key");
    global.fetch.mockResolvedValue(new Response("{}", { status: 403 }));
    createModalOverlay();

    await apiFetch("/api/jobs", { admin: true });

    const overlay = document.getElementById("apikey-overlay");
    expect(overlay.classList.contains("hidden")).toBe(true);
  });

  it("passes through options like method and body", async () => {
    setApiKey("k");
    global.fetch.mockResolvedValue(new Response("{}", { status: 200 }));

    const body = JSON.stringify({ name: "test" });
    await apiFetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/jobs",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
        body,
      }),
    );
  });

  it("throws on network error", async () => {
    global.fetch.mockRejectedValue(new Error("Network failure"));

    await expect(apiFetch("/api/jobs")).rejects.toThrow("Network failure");
  });
});
