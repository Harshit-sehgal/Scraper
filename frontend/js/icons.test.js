import { describe, expect, test } from "vitest";

import { hydrateIcons } from "./icons.js";

describe("hydrateIcons", () => {
  test("converts Material Symbols ligatures to local SVG icons", () => {
    document.body.innerHTML = '<span class="material-symbols-outlined nav-icon">dashboard</span>';

    hydrateIcons();

    const icon = document.querySelector(".material-symbols-outlined");
    expect(icon?.dataset.materialIcon).toBe("dashboard");
    expect(icon?.querySelector("svg")).not.toBeNull();
    expect(icon?.textContent?.trim()).toBe("");
  });
});
