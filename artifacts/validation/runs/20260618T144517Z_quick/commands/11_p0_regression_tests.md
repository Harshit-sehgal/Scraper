# p0_regression_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-18T14:45:21.600594+00:00
- end_time: 2026-06-18T14:45:34.465681+00:00
- duration_seconds: 12.87
- exit_code: 1
- timeout_seconds: 180
- required: true
- redaction_applied: false

## stdout

```text
.................................FFF..................................   [100%]
=================================== FAILURES ===================================
_ test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/cancel] _

client = <tests.conftest.LocalASGIClient object at 0x762451879820>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x762451919c70>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-329/test_project_scoped_write_key_4')
mutation_path = '/api/jobs/{job_id}/cancel'

    @pytest.mark.parametrize(
        "mutation_path",
        [
            "/api/jobs/{job_id}/cancel",
            "/api/jobs/{job_id}/backfill-metadata",
            "/api/jobs/{job_id}/reclean",
        ],
    )
    def test_project_scoped_write_key_cannot_mutate_another_orgs_job(
        client, monkeypatch, tmp_path, mutation_path: str,
    ) -> None:
        """R-001/R-002/R-003: a persistent SaaS WRITE key from Org A MUST NOT
        be able to cancel / backfill / reclean a job owned by Org B. Before
        the fix these mutation routes used ``require_role`` only (no
        owner/org/project check), so a project-scoped WRITE key (OPERATOR)
        could overwrite another tenant's results via reclean.
        """
        import app.main as main_mod
        from app.saas import ApiKeyScope, ApiKeyService, SignupService, reset_identity_store
        from app.saas.identity_store import SQLiteIdentityStore

        _configure_keys(monkeypatch)
        reset_identity_store(SQLiteIdentityStore(storage_path=tmp_path / "identity.db"))
        signup = SignupService()
        keys = ApiKeyService()
        org_a = signup.signup("alice@example.com", "hunter2", org_name="OrgA", project_name="ProjA")
        org_b = signup.signup("bob@example.com", "hunter2", org_name="OrgB", project_name="ProjB")
        write_key_a = keys.issue(
            project_id=org_a.project.id,
            user_id=org_a.user.id,
            name="write-a",
            scope=ApiKeyScope.WRITE,
        )
        try:
            # Seed a completed job owned by org B.
            job_b = _seed_job("mut-job-b", owner_key="user-b-key")
            job_b.org_id = org_b.organization.id
            job_b.project_id = org_b.project.id
            job_b.created_by = org_b.user.id  # type: ignore[attr-defined]
            # reclean needs results + schema_fields; backfill needs source_url.
            from app.models import FieldType, SchemaField

>           job_b.schema_fields = [SchemaField(name="company", field_type=FieldType.TEXT)]
                                                                          ^^^^^^^^^^^^^^
E           AttributeError: type object 'FieldType' has no attribute 'TEXT'

backend/tests/test_p0_auth_tenant.py:667: AttributeError
_ test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/backfill-metadata] _

client = <tests.conftest.LocalASGIClient object at 0x762451878b90>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x76245187bec0>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-329/test_project_scoped_write_key_5')
mutation_path = '/api/jobs/{job_id}/backfill-metadata'

    @pytest.mark.parametrize(
        "mutation_path",
        [
            "/api/jobs/{job_id}/cancel",
            "/api/jobs/{job_id}/backfill-metadata",
            "/api/jobs/{job_id}/reclean",
        ],
    )
    def test_project_scoped_write_key_cannot_mutate_another_orgs_job(
        client, monkeypatch, tmp_path, mutation_path: str,
    ) -> None:
        """R-001/R-002/R-003: a persistent SaaS WRITE key from Org A MUST NOT
        be able to cancel / backfill / reclean a job owned by Org B. Before
        the fix these mutation routes used ``require_role`` only (no
        owner/org/project check), so a project-scoped WRITE key (OPERATOR)
        could overwrite another tenant's results via reclean.
        """
        import app.main as main_mod
        from app.saas import ApiKeyScope, ApiKeyService, SignupService, reset_identity_store
        from app.saas.identity_store import SQLiteIdentityStore

        _configure_keys(monkeypatch)
        reset_identity_store(SQLiteIdentityStore(storage_path=tmp_path / "identity.db"))
        signup = SignupService()
        keys = ApiKeyService()
        org_a = signup.signup("alice@example.com", "hunter2", org_name="OrgA", project_name="ProjA")
        org_b = signup.signup("bob@example.com", "hunter2", org_name="OrgB", project_name="ProjB")
        write_key_a = keys.issue(
            project_id=org_a.project.id,
            user_id=org_a.user.id,
            name="write-a",
            scope=ApiKeyScope.WRITE,
        )
        try:
            # Seed a completed job owned by org B.
            job_b = _seed_job("mut-job-b", owner_key="user-b-key")
            job_b.org_id = org_b.organization.id
            job_b.project_id = org_b.project.id
            job_b.created_by = org_b.user.id  # type: ignore[attr-defined]
            # reclean needs results + schema_fields; backfill needs source_url.
            from app.models import FieldType, SchemaField

>           job_b.schema_fields = [SchemaField(name="company", field_type=FieldType.TEXT)]
                                                                          ^^^^^^^^^^^^^^
E           AttributeError: type object 'FieldType' has no attribute 'TEXT'

backend/tests/test_p0_auth_tenant.py:667: AttributeError
_ test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/reclean] _

client = <tests.conftest.LocalASGIClient object at 0x7624519bd5b0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7624519bf7a0>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-329/test_project_scoped_write_key_6')
mutation_path = '/api/jobs/{job_id}/reclean'

    @pytest.mark.parametrize(
        "mutation_path",
        [
            "/api/jobs/{job_id}/cancel",
            "/api/jobs/{job_id}/backfill-metadata",
            "/api/jobs/{job_id}/reclean",
        ],
    )
    def test_project_scoped_write_key_cannot_mutate_another_orgs_job(
        client, monkeypatch, tmp_path, mutation_path: str,
    ) -> None:
        """R-001/R-002/R-003: a persistent SaaS WRITE key from Org A MUST NOT
        be able to cancel / backfill / reclean a job owned by Org B. Before
        the fix these mutation routes used ``require_role`` only (no
        owner/org/project check), so a project-scoped WRITE key (OPERATOR)
        could overwrite another tenant's results via reclean.
        """
        import app.main as main_mod
        from app.saas import ApiKeyScope, ApiKeyService, SignupService, reset_identity_store
        from app.saas.identity_store import SQLiteIdentityStore

        _configure_keys(monkeypatch)
        reset_identity_store(SQLiteIdentityStore(storage_path=tmp_path / "identity.db"))
        signup = SignupService()
        keys = ApiKeyService()
        org_a = signup.signup("alice@example.com", "hunter2", org_name="OrgA", project_name="ProjA")
        org_b = signup.signup("bob@example.com", "hunter2", org_name="OrgB", project_name="ProjB")
        write_key_a = keys.issue(
            project_id=org_a.project.id,
            user_id=org_a.user.id,
            name="write-a",
            scope=ApiKeyScope.WRITE,
        )
        try:
            # Seed a completed job owned by org B.
            job_b = _seed_job("mut-job-b", owner_key="user-b-key")
            job_b.org_id = org_b.organization.id
            job_b.project_id = org_b.project.id
            job_b.created_by = org_b.user.id  # type: ignore[attr-defined]
            # reclean needs results + schema_fields; backfill needs source_url.
            from app.models import FieldType, SchemaField

>           job_b.schema_fields = [SchemaField(name="company", field_type=FieldType.TEXT)]
                                                                          ^^^^^^^^^^^^^^
E           AttributeError: type object 'FieldType' has no attribute 'TEXT'

backend/tests/test_p0_auth_tenant.py:667: AttributeError
=========================== short test summary info ============================
FAILED backend/tests/test_p0_auth_tenant.py::test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/cancel]
FAILED backend/tests/test_p0_auth_tenant.py::test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/backfill-metadata]
FAILED backend/tests/test_p0_auth_tenant.py::test_project_scoped_write_key_cannot_mutate_another_orgs_job[/api/jobs/{job_id}/reclean]

```

## stderr

```text

```
