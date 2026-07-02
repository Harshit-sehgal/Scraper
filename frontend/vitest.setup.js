/** Vitest setup file — resets timer state, DOM, and module stubs per test-file.
 *
 * Without this, the full ``npm test`` (all 36 files, 458 tests) can
 * hang intermittently because jsdom leaves setInterval/setTimeout
 * handles open across files. ``vi.useRealTimers()`` after each test
 * in each file forces Vitest to drain any remaining fake-timer queue
 * before the next file starts.
 *
 * Modules scanned for timers (all use setInterval or setTimeout):
 *   - ``health-pill.js``, ``recent-activity.js``, ``system-info.js``,
 *     ``jobs.js``, ``app.js``
 *
 * This does NOT affect individual ``npm run test -- <file>`` (those
 * run one file per process), so the aggregate suite is the only
 * surface where accumulated jsdom state becomes a problem.
 */

import { afterEach, vi } from "vitest";

afterEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
});
