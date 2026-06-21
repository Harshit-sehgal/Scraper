// Global Playwright setup: ensures the backend is reachable, authenticates
// with the provided API key, and persists the resulting session cookies to a
// shared storage-state file so individual tests do not have to log in.
//
// Path resolution is anchored to the file location (via fileURLToPath) rather
// than process.cwd(), so the global setup works whether Playwright is invoked
// from the project root or from `frontend/` itself.

import { request } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const configDir = dirname(fileURLToPath(import.meta.url));
const baseURL = process.env.DATAFORGE_BASE_URL || "http://localhost:8000";
const apiKey =
  process.env.DATAFORGE_E2E_API_KEY || process.env.DATAFORGE_OPERATOR_API_KEY || process.env.DATAFORGE_API_KEY || "";

const storageStatePath = resolve(configDir, ".auth/storage-state.json");

async function waitForBackend(maxAttempts = 30, delayMs = 1000) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    let ctx;
    try {
      ctx = await request.newContext({ baseURL });
      const resp = await ctx.get("/app/");
      await resp.dispose();
      return;
    } catch (err) {
      if (attempt === maxAttempts) {
        throw new Error(
          `Backend not reachable at ${baseURL} after ${maxAttempts} attempts: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
      await new Promise((r) => setTimeout(r, delayMs));
    } finally {
      await ctx?.dispose().catch(() => undefined);
    }
  }
}

export default async function globalSetup() {
  if (!apiKey) {
    // No key provided: skip auth. Tests that require auth should acquire
    // their own credentials via the apikey-overlay UI flow.
    return;
  }

  await waitForBackend();

  const ctx = await request.newContext({ baseURL });
  const resp = await ctx.post("/api/session", {
    headers: { "X-API-Key": apiKey },
  });
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(`Auth failed for ${baseURL} (status=${resp.status()}): ${body.slice(0, 200)}`);
  }
  await resp.dispose();

  await mkdir(dirname(storageStatePath), { recursive: true });
  await ctx.storageState({ path: storageStatePath });
  await ctx.dispose();
}
