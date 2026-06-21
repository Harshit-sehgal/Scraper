/* ═══════════════════════════════════════════
   DataForge — Recycle Bin Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import {
  restoreJob,
  hardDeleteJob,
  clearRecycleBin,
  handleRecycleSelectAll,
  handleRecycleSelectItem,
  batchRestore,
  batchHardDelete,
  refreshRecycleBin,
} from "./recycle.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="recycle-list"></div>
    <div id="kpi-recycle">0</div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("recycle module exports", () => {
  it("exports restoreJob as a function", () => {
    expect(typeof restoreJob).toBe("function");
  });

  it("exports hardDeleteJob as a function", () => {
    expect(typeof hardDeleteJob).toBe("function");
  });

  it("exports clearRecycleBin as a function", () => {
    expect(typeof clearRecycleBin).toBe("function");
  });

  it("exports refreshRecycleBin as a function", () => {
    expect(typeof refreshRecycleBin).toBe("function");
  });

  it("exports handleRecycleSelectAll as a function", () => {
    expect(typeof handleRecycleSelectAll).toBe("function");
  });

  it("exports handleRecycleSelectItem as a function", () => {
    expect(typeof handleRecycleSelectItem).toBe("function");
  });

  it("exports batchRestore as a function", () => {
    expect(typeof batchRestore).toBe("function");
  });

  it("exports batchHardDelete as a function", () => {
    expect(typeof batchHardDelete).toBe("function");
  });
});

describe("handleRecycleSelectAll", () => {
  it("returns undefined when called", () => {
    const result = handleRecycleSelectAll(true);
    expect(result).toBeUndefined();
  });

  it("can be called with false to deselect all", () => {
    const result = handleRecycleSelectAll(false);
    expect(result).toBeUndefined();
  });
});

describe("handleRecycleSelectItem", () => {
  it("returns undefined when called with a valid id", () => {
    const result = handleRecycleSelectItem("job-1", true);
    expect(result).toBeUndefined();
  });

  it("can be called to deselect an item", () => {
    const result = handleRecycleSelectItem("job-1", false);
    expect(result).toBeUndefined();
  });
});

describe("batchRestore", () => {
  it("returns a promise", () => {
    const result = batchRestore();
    expect(result).toBeInstanceOf(Promise);
  });
});

describe("batchHardDelete", () => {
  it("returns a promise", () => {
    const result = batchHardDelete();
    expect(result).toBeInstanceOf(Promise);
  });
});
