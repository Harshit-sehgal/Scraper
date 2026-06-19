# frontend_lint_js

- status: failed
- command: `npm run lint:js`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-18T23:30:51.417088+00:00
- end_time: 2026-06-18T23:30:52.393431+00:00
- duration_seconds: 0.98
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
[warn] frontend/js/icons.js
[warn] frontend/landing/index.html
[warn] frontend/styles/fonts.css
[warn] frontend/styles/tokens.css
[warn] frontend/styles/views.css
[warn] Code style issues found in 6 files. Run Prettier with --write to fix.

```
