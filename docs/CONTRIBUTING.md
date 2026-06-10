# Contributing to DataForge

Thank you for your interest in contributing to DataForge! This guide will help you get started.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Requests](#pull-requests)
- [Issues](#issues)
- [Documentation](#documentation)

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- Git
- Docker (optional)

### Fork and Clone

```bash
# Fork the repository on GitHub, then clone
git clone https://github.com/your-username/dataforge-scraper.git
cd dataforge-scraper

# Add upstream remote
git remote add upstream https://github.com/your-org/dataforge-scraper.git
```

## Development Setup

### 1. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
# Backend dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Frontend dependencies
npm install

# Playwright browsers
playwright install chromium
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Verify Setup

```bash
# Run doctor check
make doctor

# Run tests
make test
npm run test
```

## Code Style

### Python

- Follow PEP 8
- Use ruff for formatting and linting
- Maximum line length: 130 characters
- Type hints required for public functions

```bash
# Check formatting
ruff format --check backend/

# Fix formatting
ruff format backend/

# Lint
ruff check backend/
```

### JavaScript

- Use Prettier for formatting
- Follow Airbnb style guide
- Use ES modules

```bash
# Check formatting
npm run lint:js

# Fix formatting
npm run lint:js -- --fix
```

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new extraction method
fix: resolve rate limiting issue
docs: update API documentation
style: format code with prettier
refactor: simplify error handling
test: add unit tests for circuit breaker
chore: update dependencies
```

## Testing

### Running Tests

```bash
# Backend tests
make test

# Frontend tests
npm run test

# With coverage
make test-coverage

# Specific test file
pytest backend/tests/test_specific.py -v
```

### Writing Tests

- Write tests for new features
- Maintain or improve coverage
- Use descriptive test names
- Mock external dependencies

```python
# Example test
def test_circuit_breaker_opens_after_failures():
    """Test that circuit breaker opens after threshold failures."""
    breaker = CircuitBreaker(failure_threshold=3)

    # Simulate failures
    for _ in range(3):
        with pytest.raises(Exception):
            with breaker:
                raise Exception("Test failure")

    # Verify circuit is open
    assert breaker.state == CircuitState.OPEN
```

### Test Markers

```python
@pytest.mark.unit  # Fast, no external dependencies
@pytest.mark.api  # API contract tests
@pytest.mark.integration  # Requires external services
@pytest.mark.slow  # Takes > 5 seconds
```

## Pull Requests

### Before Submitting

1. **Update documentation** if behavior changed
2. **Add tests** for new functionality
3. **Run all checks**:
   ```bash
   make lint-all
   make test
   npm run test
   ```
4. **Update CHANGELOG.md** with your changes

### PR Template

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

### Review Process

1. Automated checks must pass
2. At least one maintainer approval
3. No unresolved conversations
4. Squash and merge

## Issues

### Bug Reports

Use the bug report template:

- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Environment details
- Logs (if applicable)

### Feature Requests

- Use case description
- Proposed solution
- Alternatives considered
- Impact assessment

### Good First Issues

Look for issues labeled `good-first-issue` for beginner-friendly tasks.

## Documentation

### Types

- **API docs**: Auto-generated from code
- **User guides**: How-to articles in `docs/`
- **Developer docs**: Architecture and design docs
- **Code comments**: Docstrings and inline comments

### Writing Docs

- Use Markdown
- Include code examples
- Keep it concise
- Update when behavior changes

### Building Docs

```bash
# Generate API docs
make api-docs

# Verify docs match code
python3 scripts/verify_docs_match_code.py
```

## Architecture

### Backend Structure

```
backend/
├── app/
│   ├── routers/      # API endpoints
│   ├── services/     # Business logic
│   ├── utils/        # Utility functions
│   └── config/       # Configuration
├── tests/            # Test files
└── benchmarks/       # Performance tests
```

### Frontend Structure

```
frontend/
├── js/               # JavaScript modules
├── styles.css        # Styles
├── index.html        # Main HTML
└── tests/            # Frontend tests
```

## Getting Help

- **GitHub Discussions**: Ask questions
- **Discord**: Real-time chat
- **Documentation**: Check `docs/` directory

## Code of Conduct

- Be respectful
- Welcome newcomers
- Focus on constructive feedback
- Help others learn

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
