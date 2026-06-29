# Tutorial 5: Anti-Bot and Proxy Configuration

Bypass common anti-bot measures responsibly with DataForge's evasion features.

## Proxy Configuration

Configure proxies to distribute requests across multiple IPs:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Proxy extraction",
    "urls": ["https://example.com"],
    "proxy": {
      "type": "http",
      "url": "http://user:pass@proxy.example.com:8080",
      "rotate": true,
      "pool": [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080",
        "socks5://proxy3.example.com:1080"
      ]
    }
  }'
```

### Proxy Types

| Type | Description |
|------|-------------|
| `http` | Standard HTTP proxy |
| `https` | HTTPS proxy with TLS |
| `socks5` | SOCKS5 proxy (supports UDP) |
| `direct` | No proxy (default) |

## Anti-Bot Evasion

DataForge's anti-bot engine automatically detects and evades common protections:

```json
{
  "anti_bot": {
    "stealth_mode": "auto",
    "fingerprint_rotation": true,
    "viewport_rotation": true,
    "human_timing": true
  }
}
```

### Evasion Features

- **Browser fingerprint randomization** — WebGL, canvas, audio context
- **Viewport rotation** — Random common screen sizes
- **Human-like behavior** — Mouse movements, scroll patterns, random delays
- **Header randomization** — Realistic Accept, Accept-Language, User-Agent
- **Cookie management** — Session persistence across requests

## User-Agent Customization

```json
{
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
```

## Rate Limiting

Control request frequency to avoid overwhelming targets:

```json
{
  "rate_limit": {
    "requests_per_second": 2,
    "concurrency": 1,
    "domain_cooldown_ms": 1000
  }
}
```

## Best Practices

1. **Use proxies ethically** — Respect robots.txt and terms of service
2. **Start slow** — Begin with low request rates and increase gradually
3. **Monitor blocks** — Check job error logs for anti-bot triggers
4. **Rotate responsibly** — Use enough proxies to distribute load, not to bypass limits
5. **Cache results** — Avoid re-extracting unchanged pages
