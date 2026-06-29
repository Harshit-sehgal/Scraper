/**
 * Tests for DataForge JS SDK.
 *
 * Usage:
 *   node test_js_sdk.mjs
 *
 * Requires Node.js 18+ (native fetch).
 */
import { DataForge } from './frontend/js/dataforge-sdk.js';

let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    passed++;
    console.log(`  PASS: ${label}`);
  } else {
    failed++;
    console.error(`  FAIL: ${label}`);
  }
}

async function run() {
  // ── Constructor ───────────────────────────────────────────────────────
  console.log('\nConstructor:');
  try {
    new DataForge({ apiKey: '' });
    console.error('  FAIL: should throw on empty apiKey');
    failed++;
  } catch {
    passed++;
    console.log('  PASS: throws on empty apiKey');
  }

  const client = new DataForge({ apiKey: 'test-key' });
  assert(client.apiKey === 'test-key', 'sets apiKey');
  assert(client.baseUrl === 'http://localhost:8000', 'default baseUrl');

  const client2 = new DataForge({ apiKey: 'k', baseUrl: 'https://api.dataforge.dev' });
  assert(client2.baseUrl === 'https://api.dataforge.dev', 'custom baseUrl');

  const client3 = new DataForge({ apiKey: 'k', baseUrl: 'http://localhost:8000/' });
  assert(client3.baseUrl === 'http://localhost:8000', 'strips trailing slash');

  // ── Method presence ──────────────────────────────────────────────────
  console.log('\nMethod presence:');
  for (const m of ['extract', 'preview', 'getJob', 'cancelJob', 'listJobs', 'deleteJob', 'getUsage']) {
    assert(typeof client[m] === 'function', `${m} is a function`);
  }

  // ── Mock request building ────────────────────────────────────────────
  console.log('\nRequest building:');
  const calls = [];
  client._request = async (method, path, body) => {
    calls.push({ method, path, body });
    return { ok: true };
  };

  await client.extract('https://example.com', { schemaFields: [{ name: 'title', field_type: 'string' }], headers: { 'Accept-Language': 'en-US' } });
  assert(calls.length === 1, 'extract makes one call');
  assert(calls[0].method === 'POST', 'extract uses POST');
  assert(calls[0].path === '/api/jobs', 'extract path');
  assert(calls[0].body.urls[0] === 'https://example.com', 'extract urls');
  assert(calls[0].body.headers['Accept-Language'] === 'en-US', 'extract headers');
  calls.length = 0;

  await client.preview('https://example.com');
  assert(calls[0].path === '/api/scraper/preview', 'preview path');
  calls.length = 0;

  await client.getJob('job-123');
  assert(calls[0].path === '/api/jobs/job-123', 'getJob path');
  assert(calls[0].method === 'GET', 'getJob GET');
  calls.length = 0;

  await client.cancelJob('job-123');
  assert(calls[0].path === '/api/jobs/job-123/cancel', 'cancelJob path');
  assert(calls[0].method === 'POST', 'cancelJob POST');
  calls.length = 0;

  await client.listJobs(10, 5);
  assert(calls[0].path === '/api/jobs?limit=10&offset=5', 'listJobs path with params');
  calls.length = 0;

  await client.deleteJob('job-123');
  assert(calls[0].method === 'DELETE', 'deleteJob DELETE');
  assert(calls[0].path === '/api/jobs/job-123', 'deleteJob path');
  calls.length = 0;

  await client.getUsage();
  assert(calls[0].path === '/api/saas/usage', 'getUsage path');

  // ── Result ───────────────────────────────────────────────────────────
  console.log(`\n${'='.repeat(40)}`);
  const total = passed + failed;
  console.log(`Total: ${total}  Passed: ${passed}  Failed: ${failed}`);
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((err) => {
  console.error('Unexpected error:', err);
  process.exit(1);
});
