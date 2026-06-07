import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { esc, toast, setEngineStatus, setEnginePolling } from "./utils.js";

describe("esc()", () => {
  it("escapes HTML special characters", () => {
    const result = esc('<script>alert("xss")</script>');
    // jsdom encodes < > but not double quotes (they don't need
    // escaping in HTML text nodes per spec).
    expect(result).toContain("&lt;script&gt;");
    expect(result).toContain("&lt;/script&gt;");
    expect(result).not.toContain("<script>");
  });

  it("returns empty string for empty input", () => {
    expect(esc("")).toBe("");
  });

  it("handles plain strings unchanged", () => {
    expect(esc("hello world")).toBe("hello world");
  });

  it("escapes & symbol", () => {
    expect(esc("a & b")).toBe("a &amp; b");
  });
});

describe("toast()", () => {
  beforeEach(() => {
    // Create toasts container
    const container = document.createElement("div");
    container.id = "toasts";
    document.body.appendChild(container);
  });

  afterEach(() => {
    const container = document.getElementById("toasts");
    if (container) container.remove();
  });

  it("creates a toast element with correct type class", () => {
    const el = toast("Test message", "success");
    expect(el).toBeDefined();
    expect(el.className).toContain("toast");
    expect(el.className).toContain("success");
  });

  it("sets text content of the message", () => {
    const el = toast("Hello world", "info");
    const msgSpan = el.querySelector("span");
    expect(msgSpan.textContent).toBe("Hello world");
  });

  it("adds timer bar element", () => {
    const el = toast("Timed", "info", 5000);
    const timer = el.querySelector(".toast-timer");
    expect(timer).toBeDefined();
    expect(timer.style.animationDuration).toBe("5000ms");
  });

  it("returns undefined when container does not exist", () => {
    document.getElementById("toasts").remove();
    const el = toast("Nowhere");
    expect(el).toBeUndefined();
  });
});

describe("setEngineStatus()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="engine-status">
        <span class="dot"></span>
        <span id="engine-status-text"></span>
      </div>
    `;
  });

  it("updates the status text", () => {
    setEngineStatus("Running", false);
    const textEl = document.getElementById("engine-status-text");
    expect(textEl.textContent).toBe("Running");
  });

  it("toggles offline class", () => {
    setEngineStatus("Offline", true);
    const el = document.getElementById("engine-status");
    expect(el.classList.contains("offline")).toBe(true);
  });

  it("removes offline class when online", () => {
    setEngineStatus("Offline", true);
    setEngineStatus("Online", false);
    const el = document.getElementById("engine-status");
    expect(el.classList.contains("offline")).toBe(false);
  });
});

describe("setEnginePolling()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="engine-status">
        <span class="dot"></span>
        <span id="engine-status-text"></span>
      </div>
    `;
  });

  it("adds polling class when active", () => {
    setEnginePolling(true);
    const dot = document.querySelector("#engine-status .dot");
    expect(dot.classList.contains("polling")).toBe(true);
  });

  it("removes polling class when inactive", () => {
    setEnginePolling(true);
    setEnginePolling(false);
    const dot = document.querySelector("#engine-status .dot");
    expect(dot.classList.contains("polling")).toBe(false);
  });
});
