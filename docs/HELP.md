# Help & Support

## Getting Help

### Documentation

| Document | Description |
|----------|-------------|
| [Quickstart Guide](QUICKSTART.md) | Get up and running in 5 minutes |
| [API Documentation](API.md) | Complete API reference |
| [Extraction Quality](EXTRACTION_QUALITY.md) | Quality metrics and benchmarking |
| [Security Headers](SECURITY_HEADERS.md) | Security configuration |
| [Monitoring](MONITORING.md) | Observability and alerting |
| [Billing](BILLING.md) | Usage tracking and quotas |

### Self-Help

1. **Check the logs**
   ```bash
   # Docker
   docker compose logs -f

   # Direct
   tail -f logs/dataforge.log
   ```

2. **Run health checks**
   ```bash
   curl http://localhost:8000/ready
   make doctor
   ```

3. **Check API status**
   ```bash
   curl http://localhost:8000/api/system/status \
     -H "X-API-Key: your-api-key"
   ```

### Community Support

- **GitHub Discussions:** https://github.com/your-org/dataforge-scraper/discussions
- **Stack Overflow:** Tag questions with `dataforge`
- **Discord:** Join our community server

### Professional Support

- **Email:** support@dataforge.io
- **Priority Support:** Available for Pro and Enterprise plans
- **Consulting:** Custom integration and development services

## Common Issues

### Authentication

**Problem:** Getting 401 Unauthorized

**Solution:**
```bash
# Check if API key is set
echo $X_API_KEY

# Test authentication
curl http://localhost:8000/health

# For development, you can disable auth
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=true
```

### Rate Limiting

**Problem:** Getting 429 Too Many Requests

**Solution:**
```bash
# Check rate limit headers
curl -I http://localhost:8000/api/jobs \
  -H "X-API-Key: your-api-key"

# Increase limits in .env
DATAFORGE_RATE_LIMIT_GLOBAL=1200
DATAFORGE_RATE_LIMIT_PER_IP=200
```

### Job Failures

**Problem:** Jobs failing or stuck

**Solution:**
```bash
# Check job events
curl http://localhost:8000/api/jobs/$JOB_ID/events \
  -H "X-API-Key: your-api-key"

# Check worker status
curl http://localhost:8000/api/system/status \
  -H "X-API-Key: your-api-key"

# Restart worker
docker compose restart dataforge
```

### Database Issues

**Problem:** Database connection errors

**Solution:**
```bash
# Check database status
curl http://localhost:8000/api/system/storage/status \
  -H "X-API-Key: your-api-key"

# For SQLite, check file permissions
ls -la data/

# For PostgreSQL, check connection
psql $DATABASE_URL -c "SELECT 1"
```

### Memory Issues

**Problem:** High memory usage

**Solution:**
```bash
# Check memory usage
curl http://localhost:8000/api/system/status \
  -H "X-API-Key: your-api-key"

# Monitor with Prometheus
curl http://localhost:9090/api/v1/query?query=process_resident_memory_bytes

# Restart if needed
docker compose restart dataforge
```

## Feature Requests

We welcome feature requests! Please:

1. **Check existing issues** - Your feature might already be requested
2. **Create a new issue** - Use the "Feature Request" template
3. **Provide details** - Describe the use case and expected behavior
4. **Vote on issues** - Help us prioritize by adding 👍 reactions

## Bug Reports

Found a bug? Please:

1. **Reproduce the issue** - Ensure it's reproducible
2. **Check logs** - Include relevant log output
3. **Provide environment details** - OS, Python version, etc.
4. **Create a minimal example** - Steps to reproduce the issue

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '...'
3. See error

**Expected behavior**
What you expected to happen.

**Environment:**
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.12.0]
- DataForge version: [e.g., 0.1.0]

**Logs**
```
[Paste relevant logs here]
```

**Additional context**
Add any other context about the problem here.
```

## Contributing

Want to contribute? See our [Contributing Guide](CONTRIBUTING.md).

### Development Setup

```bash
# Clone the repo
git clone https://github.com/your-org/dataforge-scraper.git
cd dataforge-scraper

# Install dependencies
pip install -r backend/requirements-dev.txt
npm install

# Run tests
make test
npm run test

# Run linting
make lint
npm run lint
```

### Code Style

- **Python:** Follow PEP 8, use ruff for formatting
- **JavaScript:** Use Prettier for formatting
- **Commits:** Use conventional commits format

### Pull Requests

1. Create a feature branch
2. Make your changes
3. Add tests
4. Update documentation
5. Submit a pull request

## Security Issues

Found a security vulnerability? Please:

1. **Do NOT create a public issue**
2. **Email security@dataforge.io** with details
3. **Allow time for a fix** before public disclosure

See our [Security Policy](SECURITY.md) for more details.

## License

DataForge is open source under the MIT License. See [LICENSE](LICENSE) for details.
