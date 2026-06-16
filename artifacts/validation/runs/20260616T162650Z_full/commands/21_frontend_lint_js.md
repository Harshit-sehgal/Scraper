# frontend_lint_js

- status: failed
- command: `npm run lint:js`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T16:31:55.292716+00:00
- end_time: 2026-06-16T16:31:56.147018+00:00
- duration_seconds: 0.85
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
[warn] frontend/e2e/form.spec.js
[warn] frontend/e2e/global-setup.mjs
[warn] frontend/playwright.config.mjs
[warn] Code style issues found in 3 files. Run Prettier with --write to fix.

```
