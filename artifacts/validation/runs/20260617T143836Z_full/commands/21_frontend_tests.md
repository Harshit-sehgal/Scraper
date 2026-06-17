# frontend_tests

- status: failed
- command: `npm run test`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T14:43:48.143386+00:00
- end_time: 2026-06-17T14:43:50.375063+00:00
- duration_seconds: 2.23
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text

> dataforge-frontend@0.1.0 test
> vitest run --config frontend/vitest.config.js


[1m[30m[46m RUN [49m[39m[22m [36mv4.1.8 [39m[90m/home/harshit/Documents/Work/Money/scraper[39m

 [32m✓[39m frontend/js/domain-health.test.js [2m([22m[2m17 tests[22m[2m)[22m[32m 70[2mms[22m[39m
 [32m✓[39m frontend/js/utils.test.js [2m([22m[2m48 tests[22m[2m)[22m[32m 53[2mms[22m[39m
 [32m✓[39m frontend/js/telemetry.test.js [2m([22m[2m10 tests[22m[2m)[22m[32m 39[2mms[22m[39m
 [32m✓[39m frontend/js/rate-limits.test.js [2m([22m[2m13 tests[22m[2m)[22m[32m 58[2mms[22m[39m
 [32m✓[39m frontend/js/governance.test.js [2m([22m[2m14 tests[22m[2m)[22m[32m 69[2mms[22m[39m
 [32m✓[39m frontend/js/jobs.test.js [2m([22m[2m18 tests[22m[2m)[22m[32m 53[2mms[22m[39m
 [32m✓[39m frontend/js/recycle.test.js [2m([22m[2m11 tests[22m[2m)[22m[32m 60[2mms[22m[39m
 [32m✓[39m frontend/js/results.test.js [2m([22m[2m17 tests[22m[2m)[22m[32m 64[2mms[22m[39m
 [32m✓[39m frontend/js/billing.test.js [2m([22m[2m3 tests[22m[2m)[22m[32m 115[2mms[22m[39m
 [32m✓[39m frontend/js/workflows.test.js [2m([22m[2m1 test[22m[2m)[22m[32m 55[2mms[22m[39m
 [32m✓[39m frontend/js/dashboard.test.js [2m([22m[2m2 tests[22m[2m)[22m[32m 18[2mms[22m[39m
 [32m✓[39m frontend/js/health-pill.test.js [2m([22m[2m3 tests[22m[2m)[22m[32m 57[2mms[22m[39m
 [32m✓[39m frontend/js/system-info.test.js [2m([22m[2m1 test[22m[2m)[22m[32m 23[2mms[22m[39m
 [32m✓[39m frontend/js/cognition.test.js [2m([22m[2m19 tests[22m[2m)[22m[32m 147[2mms[22m[39m
 [31m❯[39m frontend/js/analyzer.test.js [2m([22m[2m26 tests[22m[2m | [22m[31m1 failed[39m[2m)[22m[32m 132[2mms[22m[39m
     [32m✓[39m returns null / empty array before any analysis[32m 24[2mms[22m[39m
     [32m✓[39m resets state and hides panels[32m 7[2mms[22m[39m
     [32m✓[39m unchecks all when select=false[32m 15[2mms[22m[39m
     [32m✓[39m checks all when select=true[32m 7[2mms[22m[39m
     [32m✓[39m works with empty field list[32m 5[2mms[22m[39m
     [32m✓[39m renders page structure with confidence[32m 16[2mms[22m[39m
     [32m✓[39m renders high anti-bot risk in red[32m 6[2mms[22m[39m
     [32m✓[39m renders medium anti-bot risk in yellow/amber[32m 3[2mms[22m[39m
     [32m✓[39m renders low anti-bot risk in green[32m 3[2mms[22m[39m
     [32m✓[39m handles missing fields gracefully[32m 2[2mms[22m[39m
     [32m✓[39m renders fields with name, type, example, confidence[32m 6[2mms[22m[39m
     [32m✓[39m shows empty state when no fields[32m 8[2mms[22m[39m
     [32m✓[39m truncates long example values to 60 chars[32m 3[2mms[22m[39m
     [32m✓[39m updates field count[32m 3[2mms[22m[39m
     [32m✓[39m renders direct state[32m 2[2mms[22m[39m
[31m     [31m×[31m renders recovered state with user message[39m[32m 6[2mms[22m[39m
     [32m✓[39m renders session-expired state[32m 1[2mms[22m[39m
     [32m✓[39m renders empty response banner[32m 1[2mms[22m[39m
     [32m✓[39m renders session-bound banner[32m 1[2mms[22m[39m
     [32m✓[39m renders canonical URL when different from input[32m 1[2mms[22m[39m
     [32m✓[39m renders empty check suggestions[32m 1[2mms[22m[39m
     [32m✓[39m handles missing data gracefully[32m 1[2mms[22m[39m
     [32m✓[39m renders normal URL direct scrape recommendation[32m 2[2mms[22m[39m
     [32m✓[39m renders session URL workflow choices without raw token values[32m 2[2mms[22m[39m
     [32m✓[39m renders blocked URL state with disabled action[32m 1[2mms[22m[39m
     [32m✓[39m renders a workflow replay draft handoff with redacted original URL[32m 2[2mms[22m[39m
 [32m✓[39m frontend/js/api.test.js [2m([22m[2m20 tests[22m[2m)[22m[32m 63[2mms[22m[39m
 [32m✓[39m frontend/js/views.test.js [2m([22m[2m23 tests[22m[2m)[22m[32m 147[2mms[22m[39m
 [32m✓[39m frontend/js/predictions.test.js [2m([22m[2m26 tests[22m[2m)[22m[32m 222[2mms[22m[39m
 [32m✓[39m frontend/js/form.test.js [2m([22m[2m16 tests[22m[2m)[22m[32m 101[2mms[22m[39m
 [32m✓[39m frontend/js/recent-activity.test.js [2m([22m[2m1 test[22m[2m)[22m[32m 13[2mms[22m[39m

[2m Test Files [22m [1m[31m1 failed[39m[22m[2m | [22m[1m[32m19 passed[39m[22m[90m (20)[39m
[2m      Tests [22m [1m[31m1 failed[39m[22m[2m | [22m[1m[32m288 passed[39m[22m[90m (289)[39m
[2m   Start at [22m 20:13:48
[2m   Duration [22m 1.81s[2m (transform 1.70s, setup 0ms, import 2.37s, tests 1.56s, environment 17.90s)[22m


```

## stderr

```text

[31m⎯⎯⎯⎯⎯⎯⎯[39m[1m[41m Failed Tests 1 [49m[22m[31m⎯⎯⎯⎯⎯⎯⎯[39m

[41m[1m FAIL [22m[49m frontend/js/analyzer.test.js[2m > [22mrenderAcquisitionBanner()[2m > [22mrenders recovered state with user message
[31m[1mReferenceError[22m: sadj is not defined[39m
[36m [2m❯[22m renderAcquisitionBanner frontend/js/analyzer.js:[2m419:22[22m[39m
    [90m417|[39m     small.textContent = "Recovered fresh results via search form submi…
    [90m418|[39m     frag[33m.[39m[34mappendChild[39m(line)[33m;[39m
    [90m419|[39m     frag[33m.[39m[34mappendChild[39m(sadj)[33m;[39m
    [90m   |[39m                      [31m^[39m
    [90m420|[39m   }
    [90m421|[39m   [35mif[39m (isSessionBound) {
[90m [2m❯[22m frontend/js/analyzer.test.js:[2m230:28[22m[39m

[31m[2m⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯[22m[39m


```
