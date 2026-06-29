/**
 * DataForge — JavaScript/TypeScript SDK for the DataForge Scraper API.
 *
 * Usage:
 *   import { DataForge } from './dataforge-sdk.js';
 *   const client = new DataForge({ apiKey: 'df_key_...' });
 *   const job = await client.extract('https://example.com');
 */
export class DataForge {
  /**
   * @param {Object} opts
   * @param {string} opts.apiKey - DataForge API key
   * @param {string} [opts.baseUrl] - Base URL (default: http://localhost:8000)
   */
  constructor({ apiKey, baseUrl = "http://localhost:8000" }) {
    if (!apiKey) throw new Error("apiKey is required");
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async _request(method, path, body) {
    const url = `${this.baseUrl}${path}`;
    const headers = {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
    };
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async extract(url, options = {}) {
    const { schemaFields, name, ...rest } = options;
    const body = {
      name: name || `SDK extraction: ${url}`,
      mode: "manual",
      urls: [url],
      schema_fields: schemaFields || [],
      ...rest,
    };
    return this._request("POST", "/api/jobs", body);
  }

  async preview(url, options = {}) {
    const { schemaFields, name, ...rest } = options;
    const body = {
      name: name || `SDK preview: ${url}`,
      mode: "manual",
      urls: [url],
      schema_fields: schemaFields || [],
      ...rest,
    };
    return this._request("POST", "/api/scraper/preview", body);
  }

  async getJob(id) {
    return this._request("GET", `/api/jobs/${id}`);
  }

  async cancelJob(id) {
    return this._request("POST", `/api/jobs/${id}/cancel`);
  }

  async listJobs(limit = 20, offset = 0) {
    return this._request("GET", `/api/jobs?limit=${limit}&offset=${offset}`);
  }

  async deleteJob(id) {
    return this._request("DELETE", `/api/jobs/${id}`);
  }

  async getUsage() {
    return this._request("GET", "/api/saas/usage");
  }
}
