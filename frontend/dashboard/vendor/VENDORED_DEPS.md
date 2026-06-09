# Vendored Dependencies — Update Guide

## Current Versions

| Library | File | Version | Source |
|---------|------|---------|--------|
| Chart.js | `chart.min.js` | 4.5.1 | https://www.chartjs.org |
| Tailwind CSS | `tailwind.min.js` | 3.x (standalone CLI build) | https://tailwindcss.com |

## Update Process

1. **Check latest versions** on the official websites above.
2. **Download** the new version:
   - Chart.js: `https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js`
   - Tailwind: `https://github.com/tailwindlabs/tailwindcss/releases` (standalone CLI build)
3. **Verify integrity** by comparing the file hash against the official release checksum.
4. **Update files** by overwriting the `.min.js` files in this directory.
5. **Update this README** with the new version numbers.
6. **Test** by loading `frontend/dashboard/index.html` and verifying the dashboard renders correctly.
