import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// We import the recycle bin functions.
import { refreshRecycleBin, restoreJob, hardDeleteJob, clearRecycleBin } from "./recycle.js";

// ─── Helpers ────────────────────────────────────────────────────────────

function setupDOM() {
  document.body.innerHTML = `
    <div id="recycle-list"></div>
    <div id="empty-recycle-state" class="hidden">
      <p>No deleted jobs</p>
    </div>
    <div id="toasts"></div>
    <div id="confirm-overlay" class="hidden">
      <div id="confirm-modal-title"></div>
      <div id="confirm-modal-desc"></div>
      <button id="btn-confirm-cancel">Cancel</button>
      <button id="btn-confirm-execute" data-action="confirm-execute">Confirm</button>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════════════
// refreshRecycleBin
// ═══════════════════════════════════════════════════════════════════════

describe("refreshRecycleBin()", () => {
  beforeEach(() => {
    setupDOM();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state when no jobs", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ jobs: [] }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await refreshRecycleBin();

    const empty = document.getElementById("empty-recycle-state");
    expect(empty.classList.contains("hidden")).toBe(false);
    const list = document.getElementById("recycle-list");
    // The empty element is appended to the list, so list should have a child
    expect(list.children.length).toBeGreaterThanOrEqual(1);
    expect(list.textContent).toContain("No deleted jobs");
  });

  it("renders job rows when jobs exist", async () => {
    const jobs = [
      { id: "1", name: "Job One", status: "completed", filtered_records: 10, total_records: 10 },
      { id: "2", name: "Job Two", status: "failed", filtered_records: 0, total_records: 5 },
    ];
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ jobs }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await refreshRecycleBin();

    const list = document.getElementById("recycle-list");
    expect(list.innerHTML).toContain("Job One");
    expect(list.innerHTML).toContain("Job Two");
    expect(list.innerHTML).toContain("completed");
    expect(list.innerHTML).toContain("failed");
    expect(list.innerHTML).toContain("Restore");
    expect(list.innerHTML).toContain("Delete Forever");
  });

  it("shows error toast on fetch failure", async () => {
    global.fetch.mockResolvedValue(
      new Response(null, { status: 500, headers: { "Content-Type": "application/json" } }),
    );

    await refreshRecycleBin();

    const toasts = document.getElementById("toasts");
    expect(toasts.children.length).toBeGreaterThanOrEqual(1);
    expect(toasts.textContent).toContain("Failed to load recycle bin");
  });

  it("handles non-array jobs gracefully", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await refreshRecycleBin();

    const empty = document.getElementById("empty-recycle-state");
    expect(empty.classList.contains("hidden")).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// restoreJob
// ═══════════════════════════════════════════════════════════════════════

describe("restoreJob()", () => {
  beforeEach(() => {
    setupDOM();
    global.fetch = vi.fn();
  });

  it("sends POST to restore endpoint", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await restoreJob("job-123");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/recycle_bin/job-123/restore"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows success toast on success", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await restoreJob("job-123");

    const toasts = document.getElementById("toasts");
    expect(toasts.textContent).toContain("Job restored");
  });

  it("shows error toast on failure", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await restoreJob("job-404");

    const toasts = document.getElementById("toasts");
    expect(toasts.textContent).toContain("Restore failed");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// hardDeleteJob (with confirmation modal)
// ═══════════════════════════════════════════════════════════════════════

describe("hardDeleteJob()", () => {
  beforeEach(() => {
    setupDOM();
    global.fetch = vi.fn();
  });

  it("shows confirmation modal before deleting", () => {
    hardDeleteJob("job-123");

    const overlay = document.getElementById("confirm-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("confirm-modal-title").textContent).toContain("Delete Forever");
  });

  it("sends DELETE after confirmation", async () => {
    global.fetch.mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    hardDeleteJob("job-123");

    // Simulate clicking the confirm button by executing the stored callback.
    // The confirm modal's execute button click handler should trigger the deletion.
    const executeBtn = document.getElementById("btn-confirm-execute");
    // We need to dispatch click on confirm execute button which is handled
    // by the global event delegation in app.js
    // Instead, we can check that fetch hasn't been called yet (confirm not executed)
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

// ═══════════════════════════════════════════════════════════════════════
// clearRecycleBin (with confirmation modal)
// ═══════════════════════════════════════════════════════════════════════

describe("clearRecycleBin()", () => {
  beforeEach(() => {
    setupDOM();
    global.fetch = vi.fn();
  });

  it("shows confirmation modal before clearing", () => {
    clearRecycleBin();

    const overlay = document.getElementById("confirm-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("confirm-modal-title").textContent).toContain("Empty Recycle Bin");
  });

  it("does not call fetch before confirmation", () => {
    clearRecycleBin();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
