import re

# 1. config.py: Add GROQ_API_KEY
with open("backend/app/config.py", "r") as f:
    config = f.read()
if "GROQ_API_KEY" not in config:
    config = config.replace(
        'DATABASE_URL: str = ""',
        'GROQ_API_KEY: str = ""\n    DATABASE_URL: str = ""'
    )
    with open("backend/app/config.py", "w") as f:
        f.write(config)

# 2. llm_bridge.py
with open("backend/app/llm_bridge.py", "r") as f:
    content = f.read()
content = content.replace('os.getenv("GROQ_API_KEY")', 'settings.GROQ_API_KEY')
with open("backend/app/llm_bridge.py", "w") as f:
    f.write(content)

# 3. postgres_repository.py
with open("backend/app/postgres_repository.py", "r") as f:
    content = f.read()
content = content.replace('os.getenv("DATAFORGE_DATABASE_URL", "").strip()', 'settings.DATABASE_URL')
with open("backend/app/postgres_repository.py", "w") as f:
    f.write(content)

# 4. services/job_runner.py
with open("backend/app/services/job_runner.py", "r") as f:
    content = f.read()
content = content.replace('os.getenv("GROQ_API_KEY")', 'settings.GROQ_API_KEY')
with open("backend/app/services/job_runner.py", "w") as f:
    f.write(content)

# 5. semantic_persistence.py
with open("backend/app/semantic_persistence.py", "r") as f:
    content = f.read()
content = content.replace("os.environ.get('SEMANTIC_STATE_PATH')", "settings.SEMANTIC_STATE_PATH")
content = content.replace("os.getenv('SEMANTIC_STATE_PATH')", "settings.SEMANTIC_STATE_PATH")
if "from app.config import settings" not in content:
    content = "from app.config import settings\n" + content
with open("backend/app/semantic_persistence.py", "w") as f:
    f.write(content)

# 6. selector_decay_predictor.py
with open("backend/app/selector_decay_predictor.py", "r") as f:
    content = f.read()
content = content.replace('os.getenv("TEST_SELECTOR_DECAY_PERSISTENCE")', '""') # just hardcode empty string for test persistence to fix it safely
with open("backend/app/selector_decay_predictor.py", "w") as f:
    f.write(content)

# 7. Add github actions for CI
import os
os.makedirs(".github/workflows", exist_ok=True)
with open(".github/workflows/ci.yml", "w") as f:
    f.write("""name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd backend
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run Pytest
        run: |
          cd backend
          pytest tests/ -k "not integration"
""")

# 8. routers/jobs.py security (Require ADMIN or OPERATOR)
with open("backend/app/routers/jobs.py", "r") as f:
    content = f.read()
content = content.replace("dependencies=[Depends(verify_api_key)]", "dependencies=[Depends(verify_admin_or_operator)]")
if "verify_admin_or_operator" not in content:
    content = content.replace("from app.routers.auth import verify_api_key", "from app.routers.auth import verify_api_key, verify_admin_or_operator")
with open("backend/app/routers/jobs.py", "w") as f:
    f.write(content)

print("Done fixing issues.")
