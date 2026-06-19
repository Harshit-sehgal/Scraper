# frontend_lint_css

- status: failed
- command: `npm run lint:css`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-18T23:38:24.196153+00:00
- end_time: 2026-06-18T23:38:24.724337+00:00
- duration_seconds: 0.53
- exit_code: 2
- timeout_seconds: 120
- required: true
- redaction_applied: false

## stdout

```text

> dataforge-frontend@0.1.0 lint:css
> stylelint 'frontend/**/*.css' --ignore-pattern 'frontend/dist/**'


```

## stderr

```text

frontend/styles/views.css
  1121:1  ✖  Expected empty line before rule  rule-empty-line-before
  1124:1  ✖  Expected empty line before rule  rule-empty-line-before
  1127:1  ✖  Expected empty line before rule  rule-empty-line-before
  1130:1  ✖  Expected empty line before rule  rule-empty-line-before
  1133:1  ✖  Expected empty line before rule  rule-empty-line-before
  1136:1  ✖  Expected empty line before rule  rule-empty-line-before
  1139:1  ✖  Expected empty line before rule  rule-empty-line-before
  1142:1  ✖  Expected empty line before rule  rule-empty-line-before
  1145:1  ✖  Expected empty line before rule  rule-empty-line-before
  1148:1  ✖  Expected empty line before rule  rule-empty-line-before
  1151:1  ✖  Expected empty line before rule  rule-empty-line-before
  1154:1  ✖  Expected empty line before rule  rule-empty-line-before
  1161:1  ✖  Expected empty line before rule  rule-empty-line-before
  1164:1  ✖  Expected empty line before rule  rule-empty-line-before
  1167:1  ✖  Expected empty line before rule  rule-empty-line-before

✖ 15 problems (15 errors, 0 warnings)
  15 errors potentially fixable with the "--fix" option.


```
