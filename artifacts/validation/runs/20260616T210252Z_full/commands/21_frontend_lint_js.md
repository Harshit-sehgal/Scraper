# frontend_lint_js

- status: failed
- command: `npm run lint:js`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T21:07:55.630775+00:00
- end_time: 2026-06-16T21:07:56.543477+00:00
- duration_seconds: 0.91
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text

> dataforge-frontend@0.1.0 lint:js
> prettier --check 'frontend/**/*.{js,css,html,mjs}' 'grafana/**/*.json' 'package.json' '.stylelintrc.json' '.prettierrc'

Checking formatting...

```

## stderr

```text
[warn] frontend/index.html
[warn] frontend/js/aup.js
[warn] frontend/js/workflows.js
[warn] frontend/js/workflows.test.js
[warn] frontend/styles.css
[warn] Code style issues found in 5 files. Run Prettier with --write to fix.

```
