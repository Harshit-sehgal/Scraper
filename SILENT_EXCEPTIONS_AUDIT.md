# Silent Exceptions Audit & Remediation Guide

This document acts as a comprehensive SRE audit log of the **72 silent exception handlers** detected in the `backend/app` codebase. It categorizes them and provides the official remediation plan to systematically resolve them without breaking fallbacks.

## Categorization & Remediation Standards

To prevent blind replacements that could break intentional fallback paths, every handler has been analyzed and classified into one of three distinct categories:

### Category 1: Replace Swallowing with Observability (Logging)
* **Description**: Swallowed errors on critical operations (e.g. storage actions, file I/O, external network actions) where unexpected failure will hide real bugs.
* **Remediation**: Capture the exception as `except Exception as exc:` and write a `logger.warning` or `logger.error` statement with `exc_info=True` or a message.
* **Example**:
  ```python
  except OSError as exc:
      logger.warning("Failed to save state to disk: %s", exc, exc_info=True)
  ```

### Category 2: Keep Fallback but Add Descriptive Comments
* **Description**: Fully intentional and benign logic flows (e.g., trying to load optional configuration, cleaning up active/inactive assets during termination, expected parsing errors) where a fail-silent flow is the correct business logic.
* **Remediation**: Keep the silent flow, but add a descriptive comment detailing *why* the exception is swallowed.
* **Example**:
  ```python
  except (ImportError, AttributeError):
      # Settings might not be initialized yet; fallback to env/development defaults
      pass
  ```

### Category 3: Convert to Specific / Typed Exceptions
* **Description**: Catching overly broad exceptions (`except Exception`) where only specific known failure modes (e.g., `KeyError`, `ValueError`, `JSONDecodeError`) are expected.
* **Remediation**: Change the exception class to the specific subclass and document/log unexpected errors separately.
* **Example**:
  ```python
  except ValueError:
      # Handled expected missing values
      pass
  ```

---

## High-Priority Silent Exception Inventory

Here is the prioritized checklist of high-risk blocks that should be hardened next:

### 1. Database & Persistence Layer (High Risk)
- [x] `backend/app/postgres_repository.py:54` — *Resolved* (improved with specific imports and comments)
- [ ] `backend/app/storage_interface.py:125` — Broad fallback returning `None`.
- [ ] `backend/app/storage_interface.py:331` — Silent `pass` on general repository write failures.
- [ ] `backend/app/job_store.py:469` — Silent `pass` on state persistence failures.
- [ ] `backend/app/utils/job_results_store.py:50` — Silent `pass` on writing job execution results to disk.
- [ ] `backend/app/semantic_persistence.py:49` — Silent `pass` on state flushing disk issues.

### 2. Lifespan & Process Lifecycle (Medium Risk)
- [x] `backend/app/main.py:211` — *Resolved* (added warning logs)
- [x] `backend/app/main.py:218` — *Resolved* (added warning logs)
- [x] `backend/app/main.py:224` — *Resolved* (added warning logs)
- [ ] `backend/app/worker_queue_postgres.py:39` — Silent `pass` during pool closing.
- [ ] `backend/app/worker_queue_postgres.py:114` — Silent `pass` during background worker shutdown.

### 3. Asynchronous & Queue Systems (Medium Risk)
- [ ] `backend/app/worker_queue.py:231` — Silent `pass` on task scheduling failure.
- [ ] `backend/app/worker_queue.py:466` — Silent `pass` on general dequeue failures.
- [ ] `backend/app/worker_queue.py:700` — Silent `pass` inside the event execution loop.
- [ ] `backend/app/graph_update_scheduler.py:109` — Silent `pass` on scheduling graph updates.

### 4. Machine Learning & Evolutionary Models (Low Risk)
- [ ] `backend/app/strategy_evolution.py:281` — Silent `pass` in evolutionary selection.
- [ ] `backend/app/strategy_evolution.py:303` — Silent `pass` in strategy mutation.
- [ ] `backend/app/selector_memory.py:339` — Silent `return None` on cache query miss.
- [ ] `backend/app/replay_buffer.py:421` — Silent `pass` on state buffer updates.

---

## Remediation Workflow

When modifying a silent exception handler:
1. Locate the file and line.
2. Run the specific unit test for that module to establish a baseline:
   ```bash
   PYTHONPATH=backend .venv/bin/pytest backend/tests/test_[module_name].py
   ```
3. Apply the category-specific remediation.
4. Run the tests again to ensure no regressions were introduced.
5. Perform a code quality check via Pyflakes.
