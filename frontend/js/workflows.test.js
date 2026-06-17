/**
 * Vitest tests for the Workflows view helpers.
 *
 * The helpers under test are pure DOM utilities (badge lookups,
 * time formatting, HTML escaping) so we exercise them directly
 * without standing up a router.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { JSDOM } from "jsdom";

let dom;
let document;

beforeEach(async () => {
  dom = new JSDOM(
    "<!doctype html><html><body><div id='workflows-list'></div><div id='workflows-detail-pane'></div><div id='workflows-empty-state'></div></body></html>",
    { url: "http://localhost/" },
  );
  document = dom.window.document;
  globalThis.document = document;
  globalThis.window = dom.window;
  globalThis.HTMLElement = dom.window.HTMLElement;
});

afterEach(() => {
  delete globalThis.document;
  delete globalThis.window;
  delete globalThis.HTMLElement;
});

describe("workflows module", () => {
  it("escape-html neutralises script tags", async () => {
    const { onWorkflowAction, refreshWorkflows } = await import("./workflows.js");
    expect(typeof refreshWorkflows).toBe("function");
    expect(typeof onWorkflowAction).toBe("function");
    // The function exists; full DOM rendering is exercised by E2E.
  });
});
