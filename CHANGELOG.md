# Changelog

All notable changes to DataForge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Circuit breaker pattern for fault tolerance (`backend/app/utils/circuit_breaker.py`)
- Retry logic with exponential backoff (`backend/app/utils/retry.py`)
- Usage ledger and quota system (`backend/app/utils/usage_ledger.py`)
- Extraction quality metrics tracker (`backend/app/utils/extraction_metrics.py`)
- Error boundary and loading states utility (`frontend/js/error-boundary.js`)
- Security tests for input validation and auth (`backend/tests/test_security.py`)
- Coverage reporting with pytest-cov
- Flaky test detection script
- Documentation verification script

### Changed

- Updated score estimates to reflect improvements
- Improved error handling in frontend
- Enhanced security headers configuration

### Fixed

- Documentation mismatches between code and docs
- Frontend loading states and error handling
- Security headers in production

## [0.1.0] - 2026-06-10

### Added

- Initial release of DataForge
- FastAPI backend with Playwright web extraction
- Frontend dashboard with real-time updates
- PostgreSQL and SQLite support
- Rate limiting (dual-layer)
- Session authentication
- API key authentication
- Export functionality (CSV, JSON, Excel)
- Job management (create, cancel, delete)
- Recycle bin for soft deletes
- Worker queue for async jobs
- Circuit breaker pattern
- Retry logic with exponential backoff
- Usage ledger and quota system
- Extraction quality metrics
- Error boundary and loading states
- Security tests
- Comprehensive documentation

### Security

- CSP headers configured
- HSTS enabled in production
- Rate limiting implemented
- Input validation added
- SQL injection protection
- XSS protection

## [0.0.1] - 2026-05-01

### Added

- Project initialization
- Basic structure
- Initial documentation

[Unreleased]: https://github.com/your-org/dataforge-scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/dataforge-scraper/releases/tag/v0.1.0
[0.0.1]: https://github.com/your-org/dataforge-scraper/releases/tag/v0.0.1
