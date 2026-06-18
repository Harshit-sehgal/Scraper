# backend_full_tests

- status: failed
- command: `/tmp/dataforge-ci-venv/bin/python -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-18T15:50:33.099427+00:00
- end_time: 2026-06-18T15:54:53.000584+00:00
- duration_seconds: 259.90
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
......................................................FFFFFFF.F....FF..F [  5%]
FFFF.FFF..........................................ss.................... [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
.................................................s...................... [ 19%]
........................................................................ [ 20%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
.............................ssssssss................................... [ 32%]
........................................................................ [ 34%]
......................s.................s............................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
...............................................s..............s.s....... [ 45%]
...................................................................F.... [ 47%]
........................................................................ [ 49%]
........................ssssssssssssssssssssss.......................... [ 51%]
.ss..................................................................... [ 53%]
....ss.................................................................. [ 55%]
........................................................................ [ 57%]
........................................................................ [ 58%]
...................sssssssssssss...................................s.... [ 60%]
........................................................................ [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
.......................................ss............................... [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
............sssssss..................................................... [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
...........s...................ss..sssssssssssssssssss.................. [ 96%]
........................................................................ [ 98%]
............................................                             [100%]
=================================== FAILURES ===================================
_____________________ TestLogFunctions.test_log_auth_event _____________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b34fb0>
temp_log_dir = PosixPath('/tmp/tmpamc89k5f')

    def test_log_auth_event(self, temp_log_dir) -> None:
        log_auth_event(
            actor="127.0.0.1",
            action="api_key_auth",
            resource="/api/jobs",
            outcome="failure",
            details={"reason": "invalid_key"},
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:114: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.893368, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"reason": "invalid_key"}}
_____________________ TestLogFunctions.test_log_rbac_event _____________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b345f0>
temp_log_dir = PosixPath('/tmp/tmp1kr2ybqp')

    def test_log_rbac_event(self, temp_log_dir) -> None:
        log_rbac_event(
            actor="operator-1",
            action="delete_job",
            resource="job:456",
            role="operator",
            outcome="denied",
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:128: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:191 {"timestamp": 1781797857.9356024, "iso_time": "2026-06-18T15:50:57Z", "event_type": "rbac", "actor": "operator-1", "action": "delete_job", "resource": "job:456", "outcome": "denied", "details": {"role": "operator"}}
____________________ TestLogFunctions.test_log_admin_action ____________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b35280>
temp_log_dir = PosixPath('/tmp/tmp_t1tvv6l')

    def test_log_admin_action(self, temp_log_dir) -> None:
        log_admin_action(
            actor="admin-1",
            action="purge_jobs",
            resource="system",
            details={"job_count": 42},
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:141: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:217 {"timestamp": 1781797857.945664, "iso_time": "2026-06-18T15:50:57Z", "event_type": "admin", "actor": "admin-1", "action": "purge_jobs", "resource": "system", "outcome": "success", "details": {"job_count": 42}}
____________________ TestLogFunctions.test_log_data_access _____________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b347a0>
temp_log_dir = PosixPath('/tmp/tmpjhydlxqb')

    def test_log_data_access(self, temp_log_dir) -> None:
        log_data_access(
            actor="user-1",
            action="export_csv",
            resource="job:789",
            details={"format": "csv"},
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:154: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:255 {"timestamp": 1781797857.9554596, "iso_time": "2026-06-18T15:50:57Z", "event_type": "data_access", "actor": "user-1", "action": "export_csv", "resource": "job:789", "outcome": "success", "details": {"format": "csv"}}
_____________________ TestLogFunctions.test_log_job_event ______________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b36d50>
temp_log_dir = PosixPath('/tmp/tmpnt4z31zt')

    def test_log_job_event(self, temp_log_dir) -> None:
        log_job_event(
            actor="admin-1",
            action="created",
            job_id="job-abc-123",
            outcome="success",
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:166: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:293 {"timestamp": 1781797857.9674933, "iso_time": "2026-06-18T15:50:57Z", "event_type": "job", "actor": "admin-1", "action": "created", "resource": "job:job-abc-123", "outcome": "success", "details": {}}
____________________ TestLogFunctions.test_log_system_event ____________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b357c0>
temp_log_dir = PosixPath('/tmp/tmp5l0xbfr5')

    def test_log_system_event(self, temp_log_dir) -> None:
        log_system_event(
            action="startup",
            resource="scheduler",
            outcome="success",
        )
        events = get_recent_events(count=10)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:178: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:319 {"timestamp": 1781797857.978031, "iso_time": "2026-06-18T15:50:57Z", "event_type": "system", "actor": "system", "action": "startup", "resource": "scheduler", "outcome": "success", "details": {}}
________________ TestLogFunctions.test_multiple_events_ordered _________________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b79400>
temp_log_dir = PosixPath('/tmp/tmp1gtub4kr')

    def test_multiple_events_ordered(self, temp_log_dir) -> None:
        for i in range(5):
            log_auth_event(
                actor=f"user-{i}",
                action="login",
                resource="/api/jobs",
            )
        events = get_recent_events(count=10)
>       assert len(events) >= 5
E       assert 0 >= 5
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:191: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.987979, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "user-0", "action": "login", "resource": "/api/jobs", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.9880717, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "user-1", "action": "login", "resource": "/api/jobs", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.9880986, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "user-2", "action": "login", "resource": "/api/jobs", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.9881177, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "user-3", "action": "login", "resource": "/api/jobs", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797857.988134, "iso_time": "2026-06-18T15:50:57Z", "event_type": "auth", "actor": "user-4", "action": "login", "resource": "/api/jobs", "outcome": "success", "details": {}}
___________ TestLogFunctions.test_get_recent_events_limit_and_order ____________

self = <tests.test_audit_logger.TestLogFunctions object at 0x793315b78500>
temp_log_dir = PosixPath('/tmp/tmpjy29r3pd')

    def test_get_recent_events_limit_and_order(self, temp_log_dir) -> None:
        for i in range(10):
            log_auth_event(
                actor=f"user-{i}",
                action="login",
                resource="/api",
            )
        events = get_recent_events(count=3)
>       assert len(events) == 3
E       assert 0 == 3
E        +  where 0 = len([])

backend/tests/test_audit_logger.py:208: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0049636, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-0", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0050519, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-1", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0050745, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-2", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.005092, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-3", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051079, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-4", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051227, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-5", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051353, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-6", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051494, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-7", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051618, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-8", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0051727, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-9", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
_____________________ TestLogFileIO.test_log_file_created ______________________

self = <tests.test_audit_logger.TestLogFileIO object at 0x793315b78740>
temp_log_dir = PosixPath('/tmp/tmp6qf81zm3')

    def test_log_file_created(self, temp_log_dir) -> None:
        log_system_event(action="test_startup")
        log_path = temp_log_dir / "test_audit.log"
>       assert log_path.exists(), f"Audit log file should exist at {log_path}"
E       AssertionError: Audit log file should exist at /tmp/tmp6qf81zm3/test_audit.log
E       assert False
E        +  where False = exists()
E        +    where exists = PosixPath('/tmp/tmp6qf81zm3/test_audit.log').exists

backend/tests/test_audit_logger.py:251: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:319 {"timestamp": 1781797858.0405962, "iso_time": "2026-06-18T15:50:58Z", "event_type": "system", "actor": "system", "action": "test_startup", "resource": "", "outcome": "success", "details": {}}
_____________________ TestLogFileIO.test_log_file_rotation _____________________

self = <tests.test_audit_logger.TestLogFileIO object at 0x793315b78c50>
temp_log_dir = PosixPath('/tmp/tmpbf780nj2')

    def test_log_file_rotation(self, temp_log_dir) -> None:
        """Verify that the log file contains properly formatted lines."""
        for i in range(20):
            log_auth_event(actor=f"user-{i}", action="login", resource="/api")
        log_path = temp_log_dir / "test_audit.log"
>       assert log_path.exists()
E       AssertionError: assert False
E        +  where False = exists()
E        +    where exists = PosixPath('/tmp/tmpbf780nj2/test_audit.log').exists

backend/tests/test_audit_logger.py:260: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0508618, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-0", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0509548, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-1", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.050984, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-2", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0510044, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-3", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0510218, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-4", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0510385, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-5", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0510519, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-6", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.051066, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-7", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.051081, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-8", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0510974, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-9", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511122, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-10", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511272, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-11", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511405, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-12", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511549, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-13", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511687, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-14", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511823, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-15", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0511959, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-16", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0512114, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-17", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.051226, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-18", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0512397, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "user-19", "action": "login", "resource": "/api", "outcome": "success", "details": {}}
________ TestAuthFailureLogging.test_invalid_api_key_logs_auth_failure _________

self = <tests.test_audit_logger_integration.TestAuthFailureLogging object at 0x793315b7ad20>
client = <tests.conftest.LocalASGIClient object at 0x79331442b200>
_setup_log_dir = PosixPath('/tmp/tmp34ulwcdh')

    def test_invalid_api_key_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Invalid API key should log an auth failure event."""
        response = client.get("/api/jobs", headers={"X-API-Key": "invalid_key"})
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
>       assert len(events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:90: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0758667, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": false}}
________ TestAuthFailureLogging.test_missing_api_key_logs_auth_failure _________

self = <tests.test_audit_logger_integration.TestAuthFailureLogging object at 0x793315b7a120>
client = <tests.conftest.LocalASGIClient object at 0x79330d872e70>
_setup_log_dir = PosixPath('/tmp/tmp49go2v9q')

    def test_missing_api_key_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Missing API key header should log an auth failure event."""
        response = client.get("/api/jobs")
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
        failure_events = [e for e in events if e["outcome"] == "failure"]
>       assert len(failure_events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:103: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.0885866, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": false}}
______ TestAuthFailureLogging.test_invalid_bearer_token_logs_auth_failure ______

self = <tests.test_audit_logger_integration.TestAuthFailureLogging object at 0x793315b79c40>
client = <tests.conftest.LocalASGIClient object at 0x79330d866450>
_setup_log_dir = PosixPath('/tmp/tmp9pwd0qe7')

    def test_invalid_bearer_token_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Invalid Bearer token should log an auth failure event."""
        response = client.get(
            "/api/jobs",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
        failure_events = [e for e in events if e["outcome"] == "failure"]
>       assert len(failure_events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:115: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1019175, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": true}}
_____________ TestAuthFailureLogging.test_auth_failure_has_details _____________

self = <tests.test_audit_logger_integration.TestAuthFailureLogging object at 0x793315b78e00>
client = <tests.conftest.LocalASGIClient object at 0x79330d866a80>
_setup_log_dir = PosixPath('/tmp/tmpj015mwnp')

    def test_auth_failure_has_details(self, client, _setup_log_dir) -> None:
        """Auth failure events should include method and path details."""
        client.post("/api/jobs", headers={"X-API-Key": "bad"})

        events = _read_audit_log(_setup_log_dir)
        failures = [e for e in events if e["outcome"] == "failure"]
>       assert len(failures) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:123: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1139503, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "POST", "has_bearer": false}}
___________ TestAuthFailureLogging.test_multiple_failures_all_logged ___________

self = <tests.test_audit_logger_integration.TestAuthFailureLogging object at 0x793315b7ae70>
client = <tests.conftest.LocalASGIClient object at 0x79330d864830>
_setup_log_dir = PosixPath('/tmp/tmp0m9j1t7l')

    def test_multiple_failures_all_logged(self, client, _setup_log_dir) -> None:
        """Multiple consecutive auth failures should each be logged."""
        for _ in range(3):
            client.get("/api/jobs", headers={"X-API-Key": "bad"})

        events = _read_audit_log(_setup_log_dir)
        failures = [e for e in events if e["outcome"] == "failure"]
>       assert len(failures) >= 3
E       assert 0 >= 3
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:135: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1258419, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": false}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1269853, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": false}}
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1280174, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "127.0.0.1", "action": "api_key_auth", "resource": "/api/jobs", "outcome": "failure", "details": {"method": "GET", "has_bearer": false}}
__________ TestAuthSuccessLogging.test_post_request_logs_auth_success __________

self = <tests.test_audit_logger_integration.TestAuthSuccessLogging object at 0x793315b7bb00>
client = <tests.conftest.LocalASGIClient object at 0x79330f1165a0>
_setup_log_dir = PosixPath('/tmp/tmpl429h7ql')

    def test_post_request_logs_auth_success(self, client, _setup_log_dir) -> None:
        """POST requests with valid key should log auth success."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-API-Key": "test_operator_key"},
        )
        # May get 422 (validation) but should NOT get 403 (auth)
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
>       assert len(success_events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:163: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1502368, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "operator:fdd6a5f0e55710c2:127.0.0.1", "action": "api_auth", "resource": "/api/discover", "outcome": "success", "details": {"role": "operator", "method": "POST", "source": "api_key"}}
___________ TestAuthSuccessLogging.test_admin_key_logs_correct_role ____________

self = <tests.test_audit_logger_integration.TestAuthSuccessLogging object at 0x793315b384d0>
client = <tests.conftest.LocalASGIClient object at 0x793316a7adb0>
_setup_log_dir = PosixPath('/tmp/tmp6fb0bl8e')

    def test_admin_key_logs_correct_role(self, client, _setup_log_dir) -> None:
        """Admin key used in POST should log 'admin' role."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-Admin-Key": "test_admin_key"},
        )
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
>       assert len(success_events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:177: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1648583, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "admin:9e7e96bd34d22262:127.0.0.1", "action": "api_auth", "resource": "/api/discover", "outcome": "success", "details": {"role": "admin", "method": "POST", "source": "api_key"}}
__________ TestAuthSuccessLogging.test_operator_key_logs_correct_role __________

self = <tests.test_audit_logger_integration.TestAuthSuccessLogging object at 0x793315b38da0>
client = <tests.conftest.LocalASGIClient object at 0x793314496c30>
_setup_log_dir = PosixPath('/tmp/tmp4ng9o8ao')

    def test_operator_key_logs_correct_role(self, client, _setup_log_dir) -> None:
        """Operator key used in POST should log 'operator' role."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-API-Key": "test_operator_key"},
        )
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
        # Filter for operator role events
        operator_events = [e for e in success_events if e.get("details", {}).get("role") == "operator"]
>       assert len(operator_events) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

backend/tests/test_audit_logger_integration.py:194: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:161 {"timestamp": 1781797858.1793664, "iso_time": "2026-06-18T15:50:58Z", "event_type": "auth", "actor": "operator:fdd6a5f0e55710c2:127.0.0.1", "action": "api_auth", "resource": "/api/discover", "outcome": "success", "details": {"role": "operator", "method": "POST", "source": "api_key"}}
_________________________ test_accept_emits_audit_log __________________________

saas_client = (<httpx.AsyncClient object at 0x79330e425430>, <app.saas.identity_store.SQLiteIdentityStore object at 0x79330d5ac9b0>, {'value': 'u4'}, PosixPath('/tmp/pytest-of-harshit/pytest-356/test_accept_emits_audit_log0'))

    @pytest.mark.asyncio
    async def test_accept_emits_audit_log(saas_client) -> None:
        client, store, user_ref, tmp_path = saas_client
        user_ref["value"] = "u4"
        _create_user(store, "u4")
        resp = await client.post(
            "/api/saas/aup/accept",
            json={"aup_version": CURRENT_AUP_VERSION},
        )
        assert resp.status_code == 200
        # Force the rotation handler to flush.
        from app.audit_logger import log_system_event

        log_system_event("test_event")
        log_path = tmp_path / "audit.log"
>       assert log_path.exists()
E       AssertionError: assert False
E        +  where False = exists()
E        +    where exists = PosixPath('/tmp/pytest-of-harshit/pytest-356/test_accept_emits_audit_log0/audit.log').exists

backend/tests/test_p1_compliance_aup.py:190: AssertionError
------------------------------ Captured log call -------------------------------
INFO     audit:audit_logger.py:293 {"timestamp": 1781797966.383438, "iso_time": "2026-06-18T15:52:46Z", "event_type": "job", "actor": "u4", "action": "aup_accept", "resource": "job:aup", "outcome": "success", "details": {"aup_version": "2026-06-11-v1", "previous": null}}
INFO     audit:audit_logger.py:319 {"timestamp": 1781797966.3837852, "iso_time": "2026-06-18T15:52:46Z", "event_type": "system", "actor": "system", "action": "test_event", "resource": "", "outcome": "success", "details": {}}
=========================== short test summary info ============================
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_auth_event
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_rbac_event
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_admin_action
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_data_access
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_job_event
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_log_system_event
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_multiple_events_ordered
FAILED backend/tests/test_audit_logger.py::TestLogFunctions::test_get_recent_events_limit_and_order
FAILED backend/tests/test_audit_logger.py::TestLogFileIO::test_log_file_created
FAILED backend/tests/test_audit_logger.py::TestLogFileIO::test_log_file_rotation
FAILED backend/tests/test_audit_logger_integration.py::TestAuthFailureLogging::test_invalid_api_key_logs_auth_failure
FAILED backend/tests/test_audit_logger_integration.py::TestAuthFailureLogging::test_missing_api_key_logs_auth_failure
FAILED backend/tests/test_audit_logger_integration.py::TestAuthFailureLogging::test_invalid_bearer_token_logs_auth_failure
FAILED backend/tests/test_audit_logger_integration.py::TestAuthFailureLogging::test_auth_failure_has_details
FAILED backend/tests/test_audit_logger_integration.py::TestAuthFailureLogging::test_multiple_failures_all_logged
FAILED backend/tests/test_audit_logger_integration.py::TestAuthSuccessLogging::test_post_request_logs_auth_success
FAILED backend/tests/test_audit_logger_integration.py::TestAuthSuccessLogging::test_admin_key_logs_correct_role
FAILED backend/tests/test_audit_logger_integration.py::TestAuthSuccessLogging::test_operator_key_logs_correct_role
FAILED backend/tests/test_p1_compliance_aup.py::test_accept_emits_audit_log

```

## stderr

```text

```
