# frontend_lint_css

- status: failed
- command: `npm run lint:css`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-18T23:30:52.393846+00:00
- end_time: 2026-06-18T23:30:52.932163+00:00
- duration_seconds: 0.54
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

frontend/styles.css
   7:9  ✖  Expected "url("./styles/tokens.css")" to be ""./styles/tokens.css""          import-notation
   8:9  ✖  Expected "url("./styles/fonts.css")" to be ""./styles/fonts.css""            import-notation
   9:9  ✖  Expected "url("./styles/base.css")" to be ""./styles/base.css""              import-notation
  10:9  ✖  Expected "url("./styles/icons.css")" to be ""./styles/icons.css""            import-notation
  11:9  ✖  Expected "url("./styles/components.css")" to be ""./styles/components.css""  import-notation
  12:9  ✖  Expected "url("./styles/layout.css")" to be ""./styles/layout.css""          import-notation
  13:9  ✖  Expected "url("./styles/views.css")" to be ""./styles/views.css""            import-notation

frontend/styles/base.css
   22:19  ✖  Expected "optimizeLegibility" to be "optimizelegibility"  value-keyword-case
   77:1   ✖  Expected empty line before rule                           rule-empty-line-before
   80:1   ✖  Expected empty line before rule                           rule-empty-line-before
   83:1   ✖  Expected empty line before rule                           rule-empty-line-before
   86:1   ✖  Expected empty line before rule                           rule-empty-line-before
   89:1   ✖  Expected empty line before rule                           rule-empty-line-before
  166:1   ✖  Expected empty line before rule                           rule-empty-line-before
  169:1   ✖  Expected empty line before rule                           rule-empty-line-before
  172:1   ✖  Expected empty line before rule                           rule-empty-line-before
  175:1   ✖  Expected empty line before rule                           rule-empty-line-before
  178:1   ✖  Expected empty line before rule                           rule-empty-line-before
  181:1   ✖  Expected empty line before rule                           rule-empty-line-before
  184:1   ✖  Expected empty line before rule                           rule-empty-line-before
  187:1   ✖  Expected empty line before rule                           rule-empty-line-before
  190:1   ✖  Expected empty line before rule                           rule-empty-line-before
  193:1   ✖  Expected empty line before rule                           rule-empty-line-before
  196:1   ✖  Expected empty line before rule                           rule-empty-line-before
  200:1   ✖  Expected empty line before rule                           rule-empty-line-before
  209:1   ✖  Expected empty line before rule                           rule-empty-line-before

frontend/styles/components.css
   60:1   ✖  Expected empty line before rule                           rule-empty-line-before
   65:1   ✖  Expected empty line before rule                           rule-empty-line-before
   70:1   ✖  Expected empty line before rule                           rule-empty-line-before
   79:1   ✖  Expected empty line before rule                           rule-empty-line-before
   89:1   ✖  Expected empty line before rule                           rule-empty-line-before
  100:1   ✖  Expected empty line before rule                           rule-empty-line-before
  104:1   ✖  Expected empty line before rule                           rule-empty-line-before
  159:10  ✖  Expected "currentColor" to be "currentcolor"              value-keyword-case
  181:3   ✖  Unexpected vendor-prefixed property "-webkit-appearance"  property-no-vendor-prefix
  235:1   ✖  Expected empty line before rule                           rule-empty-line-before
  238:1   ✖  Expected empty line before rule                           rule-empty-line-before
  322:15  ✖  Expected "currentColor" to be "currentcolor"              value-keyword-case
  614:1   ✖  Expected empty line before rule                           rule-empty-line-before
  617:1   ✖  Expected empty line before rule                           rule-empty-line-before
  620:1   ✖  Expected empty line before rule                           rule-empty-line-before
  696:1   ✖  Expected empty line before rule                           rule-empty-line-before
  701:1   ✖  Expected empty line before rule                           rule-empty-line-before
  712:15  ✖  Expected "currentColor" to be "currentcolor"              value-keyword-case
  736:1   ✖  Expected empty line before rule                           rule-empty-line-before

frontend/styles/fonts.css
  6:16  ✖  Unexpected quotes around "Inter"  font-family-name-quotes

frontend/styles/icons.css
  10:11  ✖  Expected "currentColor" to be "currentcolor"  value-keyword-case
  21:1   ✖  Expected empty line before rule               rule-empty-line-before
  25:1   ✖  Expected empty line before rule               rule-empty-line-before
  29:1   ✖  Expected empty line before rule               rule-empty-line-before
  40:1   ✖  Expected empty line before rule               rule-empty-line-before

frontend/styles/layout.css
   86:1  ✖  Expected empty line before rule  rule-empty-line-before
  658:3  ✖  Expected empty line before rule  rule-empty-line-before
  661:3  ✖  Expected empty line before rule  rule-empty-line-before
  670:3  ✖  Expected empty line before rule  rule-empty-line-before
  673:3  ✖  Expected empty line before rule  rule-empty-line-before

frontend/styles/tokens.css
    8:9   ✖  Expected "#ffffff" to be "#fff"                           color-hex-length
   23:18  ✖  Expected "#ffffff" to be "#fff"                           color-hex-length
   53:40  ✖  Expected "BlinkMacSystemFont" to be "blinkmacsystemfont"  value-keyword-case
   53:72  ✖  Expected "Roboto" to be "roboto"                          value-keyword-case
   54:30  ✖  Expected "SFMono-Regular" to be "sfmono-regular"          value-keyword-case
   54:64  ✖  Expected "Menlo" to be "menlo"                            value-keyword-case
   54:71  ✖  Expected "Consolas" to be "consolas"                      value-keyword-case
  118:3   ✖  Unexpected empty line before custom property              custom-property-empty-line-before
  125:3   ✖  Unexpected empty line before custom property              custom-property-empty-line-before
  127:19  ✖  Expected "#ffffff" to be "#fff"                           color-hex-length
  129:3   ✖  Unexpected empty line before custom property              custom-property-empty-line-before

frontend/styles/views.css
  1142:21  ✖  Expected "currentColor" to be "currentcolor"  value-keyword-case

✖ 68 problems (68 errors, 0 warnings)
  68 errors potentially fixable with the "--fix" option.


```
