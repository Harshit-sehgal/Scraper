import { request } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const baseURL = process.env.DATAFORGE_BASE_URL || "http://localhost:8000";
const apiKey =
  process.env.DATAFORGE_E2E_API_KEY || process.env.DATAFORGE_OPERATOR_API_KEY || process.env.DATAFORGE_API_KEY || "";
const storageStatePath = resolve("frontend/e2e/.auth/storage-state.json");

export default async function globalSetup() {
  if (!apiKey) return;

  const api = await request.newContext({ baseURL });
  const appShell = await api.get("/app/");
  if (!appShell.ok()) {
    await api.dispose();
    throw new Error(`E2E app shell is not reachable at ${baseURL}/app/`);
  }

  const response = await api.post("/api/session", {
    headers: { "X-API-Key": apiKey },
  });
  if (!response.ok()) {
    await api.dispose();
    throw new Error(`E2E session setup failed with HTTP ${response.status()}`);
  }

  await mkdir(dirname(storageStatePath), { recursive: true });
  await api.storageState({ path: storageStatePath });
  await api.dispose();
}
