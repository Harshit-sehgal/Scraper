# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-19T11:22:49.443362+00:00
- end_time: 2026-06-19T11:27:25.696325+00:00
- duration_seconds: 276.25
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
........................................................................ [  5%]
..................................................ss..........FFFFFFFFF. [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
..............................................s......................... [ 18%]
........................................................................ [ 20%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
..........................ssssssss...................................... [ 32%]
........................................................................ [ 34%]
...................s.................s.................................. [ 36%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
............................................s..............s.s.......... [ 45%]
........................................................................ [ 47%]
........................................................................ [ 49%]
.....................ssssssssssssssssssssss...........................ss [ 51%]
........................................................................ [ 53%]
.ss..................................................................... [ 55%]
........................................................................ [ 56%]
........................................................................ [ 58%]
................sssssssssssss...................................s....... [ 60%]
........................................................................ [ 62%]
....................................................................F... [ 64%]
........................................................................ [ 66%]
....................................ss.................................. [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
.........sssssss........................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
.............s...................ss..sssssssssssssssssss................ [ 96%]
........................................................................ [ 98%]
..............................................                           [100%]
=================================== FAILURES ===================================
_ test_get_customer_maps_paid_plan_id_to_correct_tier[P-STARTER-TEST123-starter] _

plan_id_env_value = 'P-STARTER-TEST123'
expected_tier = <PlanTierId.STARTER: 'starter'>

    @pytest.mark.parametrize(
        ("plan_id_env_value", "expected_tier"),
        [
            ("P-STARTER-TEST123", PlanTierId.STARTER),
            ("P-PRO-TEST123", PlanTierId.PRO),
            ("P-ENTERPRISE-TEST123", PlanTierId.ENTERPRISE),
        ],
    )
    def test_get_customer_maps_paid_plan_id_to_correct_tier(plan_id_env_value: str, expected_tier: PlanTierId) -> None:
        """A paid plan_id from PayPal MUST resolve to the matching PlanTierId,
        not silently collapse to FREE.
    
        Each tier's plan_id is sourced from the env var mapped in
        ``_PLAN_ID_ENV_BY_TIER`` (e.g. ``PAYPAL_PLAN_ID_STARTER``).
        """
        # The plan_id is decoupled from the internal tier via env-var lookup, so
        # we set ONLY the env var matching the expected tier; the helper still
        # returns the same string for any tier — the lookup is what differs.
        env_var_by_tier = {
            PlanTierId.STARTER: "PAYPAL_PLAN_ID_STARTER",
            PlanTierId.PRO: "PAYPAL_PLAN_ID_PRO",
            PlanTierId.ENTERPRISE: "PAYPAL_PLAN_ID_ENTERPRISE",
        }
        target_env = env_var_by_tier[expected_tier]
        fake_http = _fake_paypal_http(plan_id=plan_id_env_value)
    
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {target_env: plan_id_env_value, "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(client, "_client", new=fake_http.HttpClient()), patch.object(
            client, "_paypalhttp", new=fake_http
        ):
            info = client.get_customer("I-TEST")
    
>       assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
E       AssertionError: get_customer should return CustomerInfo when the provider returns a customer
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:89: AssertionError
____ test_get_customer_maps_paid_plan_id_to_correct_tier[P-PRO-TEST123-pro] ____

plan_id_env_value = 'P-PRO-TEST123', expected_tier = <PlanTierId.PRO: 'pro'>

    @pytest.mark.parametrize(
        ("plan_id_env_value", "expected_tier"),
        [
            ("P-STARTER-TEST123", PlanTierId.STARTER),
            ("P-PRO-TEST123", PlanTierId.PRO),
            ("P-ENTERPRISE-TEST123", PlanTierId.ENTERPRISE),
        ],
    )
    def test_get_customer_maps_paid_plan_id_to_correct_tier(plan_id_env_value: str, expected_tier: PlanTierId) -> None:
        """A paid plan_id from PayPal MUST resolve to the matching PlanTierId,
        not silently collapse to FREE.
    
        Each tier's plan_id is sourced from the env var mapped in
        ``_PLAN_ID_ENV_BY_TIER`` (e.g. ``PAYPAL_PLAN_ID_STARTER``).
        """
        # The plan_id is decoupled from the internal tier via env-var lookup, so
        # we set ONLY the env var matching the expected tier; the helper still
        # returns the same string for any tier — the lookup is what differs.
        env_var_by_tier = {
            PlanTierId.STARTER: "PAYPAL_PLAN_ID_STARTER",
            PlanTierId.PRO: "PAYPAL_PLAN_ID_PRO",
            PlanTierId.ENTERPRISE: "PAYPAL_PLAN_ID_ENTERPRISE",
        }
        target_env = env_var_by_tier[expected_tier]
        fake_http = _fake_paypal_http(plan_id=plan_id_env_value)
    
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {target_env: plan_id_env_value, "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(client, "_client", new=fake_http.HttpClient()), patch.object(
            client, "_paypalhttp", new=fake_http
        ):
            info = client.get_customer("I-TEST")
    
>       assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
E       AssertionError: get_customer should return CustomerInfo when the provider returns a customer
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:89: AssertionError
_ test_get_customer_maps_paid_plan_id_to_correct_tier[P-ENTERPRISE-TEST123-enterprise] _

plan_id_env_value = 'P-ENTERPRISE-TEST123'
expected_tier = <PlanTierId.ENTERPRISE: 'enterprise'>

    @pytest.mark.parametrize(
        ("plan_id_env_value", "expected_tier"),
        [
            ("P-STARTER-TEST123", PlanTierId.STARTER),
            ("P-PRO-TEST123", PlanTierId.PRO),
            ("P-ENTERPRISE-TEST123", PlanTierId.ENTERPRISE),
        ],
    )
    def test_get_customer_maps_paid_plan_id_to_correct_tier(plan_id_env_value: str, expected_tier: PlanTierId) -> None:
        """A paid plan_id from PayPal MUST resolve to the matching PlanTierId,
        not silently collapse to FREE.
    
        Each tier's plan_id is sourced from the env var mapped in
        ``_PLAN_ID_ENV_BY_TIER`` (e.g. ``PAYPAL_PLAN_ID_STARTER``).
        """
        # The plan_id is decoupled from the internal tier via env-var lookup, so
        # we set ONLY the env var matching the expected tier; the helper still
        # returns the same string for any tier — the lookup is what differs.
        env_var_by_tier = {
            PlanTierId.STARTER: "PAYPAL_PLAN_ID_STARTER",
            PlanTierId.PRO: "PAYPAL_PLAN_ID_PRO",
            PlanTierId.ENTERPRISE: "PAYPAL_PLAN_ID_ENTERPRISE",
        }
        target_env = env_var_by_tier[expected_tier]
        fake_http = _fake_paypal_http(plan_id=plan_id_env_value)
    
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {target_env: plan_id_env_value, "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(client, "_client", new=fake_http.HttpClient()), patch.object(
            client, "_paypalhttp", new=fake_http
        ):
            info = client.get_customer("I-TEST")
    
>       assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
E       AssertionError: get_customer should return CustomerInfo when the provider returns a customer
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:89: AssertionError
_____________ test_get_customer_unknown_plan_id_falls_back_to_free _____________

    def test_get_customer_unknown_plan_id_falls_back_to_free() -> None:
        """An unrecognized plan_id still falls back to FREE (safe default)."""
        fake_http = _fake_paypal_http(plan_id="P-PLATINUM-MAX-9999")
        client = PayPalClient()
        with patch.dict(os.environ, {}, clear=False), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            info = client.get_customer("I-UNKNOWN")
>       assert info is not None
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:104: AssertionError
__________ test_get_customer_maps_subscription_status[ACTIVE-active] ___________

sub_status = 'ACTIVE', expected_status = <SubscriptionStatus.ACTIVE: 'active'>

    @pytest.mark.parametrize(
        ("sub_status", "expected_status"),
        [
            ("ACTIVE", SubscriptionStatus.ACTIVE),
            ("SUSPENDED", SubscriptionStatus.PAST_DUE),
            ("CANCELLED", SubscriptionStatus.CANCELED),
            ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),  # unknown → defaults to ACTIVE
        ],
    )
    def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
        """Subscription status resolution must lowercase the PayPal status and
        match against ``SubscriptionStatus._value_`` strings — never collapse to
        a single sentinel."""
        fake_http = _fake_paypal_http(plan_id="P-PRO-TEST123", sub_status=sub_status)
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            info = client.get_customer("I-TEST")
>       assert info is not None
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:131: AssertionError
________ test_get_customer_maps_subscription_status[SUSPENDED-past_due] ________

sub_status = 'SUSPENDED'
expected_status = <SubscriptionStatus.PAST_DUE: 'past_due'>

    @pytest.mark.parametrize(
        ("sub_status", "expected_status"),
        [
            ("ACTIVE", SubscriptionStatus.ACTIVE),
            ("SUSPENDED", SubscriptionStatus.PAST_DUE),
            ("CANCELLED", SubscriptionStatus.CANCELED),
            ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),  # unknown → defaults to ACTIVE
        ],
    )
    def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
        """Subscription status resolution must lowercase the PayPal status and
        match against ``SubscriptionStatus._value_`` strings — never collapse to
        a single sentinel."""
        fake_http = _fake_paypal_http(plan_id="P-PRO-TEST123", sub_status=sub_status)
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            info = client.get_customer("I-TEST")
>       assert info is not None
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:131: AssertionError
________ test_get_customer_maps_subscription_status[CANCELLED-canceled] ________

sub_status = 'CANCELLED'
expected_status = <SubscriptionStatus.CANCELED: 'canceled'>

    @pytest.mark.parametrize(
        ("sub_status", "expected_status"),
        [
            ("ACTIVE", SubscriptionStatus.ACTIVE),
            ("SUSPENDED", SubscriptionStatus.PAST_DUE),
            ("CANCELLED", SubscriptionStatus.CANCELED),
            ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),  # unknown → defaults to ACTIVE
        ],
    )
    def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
        """Subscription status resolution must lowercase the PayPal status and
        match against ``SubscriptionStatus._value_`` strings — never collapse to
        a single sentinel."""
        fake_http = _fake_paypal_http(plan_id="P-PRO-TEST123", sub_status=sub_status)
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            info = client.get_customer("I-TEST")
>       assert info is not None
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:131: AssertionError
_____ test_get_customer_maps_subscription_status[APPROVAL_PENDING-active] ______

sub_status = 'APPROVAL_PENDING'
expected_status = <SubscriptionStatus.ACTIVE: 'active'>

    @pytest.mark.parametrize(
        ("sub_status", "expected_status"),
        [
            ("ACTIVE", SubscriptionStatus.ACTIVE),
            ("SUSPENDED", SubscriptionStatus.PAST_DUE),
            ("CANCELLED", SubscriptionStatus.CANCELED),
            ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),  # unknown → defaults to ACTIVE
        ],
    )
    def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
        """Subscription status resolution must lowercase the PayPal status and
        match against ``SubscriptionStatus._value_`` strings — never collapse to
        a single sentinel."""
        fake_http = _fake_paypal_http(plan_id="P-PRO-TEST123", sub_status=sub_status)
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            info = client.get_customer("I-TEST")
>       assert info is not None
E       assert None is not None

backend/tests/test_billing_tier_resolution.py:131: AssertionError
___________ test_get_customer_plan_tier_returns_pro_for_pro_customer ___________

    def test_get_customer_plan_tier_returns_pro_for_pro_customer() -> None:
        """End-to-end: get_customer_plan_tier must not collapse a pro customer to FREE."""
        fake_http = _fake_paypal_http(plan_id="P-PRO-TEST123")
        client = PayPalClient()
        with patch.dict(
            os.environ,
            {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
            clear=False,
        ), patch.object(
            client, "_client", new=fake_http.HttpClient()
        ), patch.object(client, "_paypalhttp", new=fake_http):
            tier = client.get_customer_plan_tier("I-TEST")
>       assert tier == PlanTierId.PRO
E       AssertionError: assert <PlanTierId.FREE: 'free'> == <PlanTierId.PRO: 'pro'>
E         
E         - pro
E         + free

backend/tests/test_billing_tier_resolution.py:147: AssertionError
______________ test_route_auth_matrix_has_no_user_level_mutations ______________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7c70a2cdd160>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-374/test_route_auth_matrix_has_no_0')

    def test_route_auth_matrix_has_no_user_level_mutations(monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
        monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))
    
        matrix = _load_module().build_matrix()
    
        # Endpoints that are intentionally unauthenticated mutation routes. Each
        # entry is a (method, path) pair that has a documented reason for being
        # open (e.g. browser-generated reports). The reason is enforced by the
        # body-size middleware (5 MB cap) and the global /api/* rate limiter.
        UNAUTHENTICATED_MUTATIONS = {
            ("POST", "/api/system/csp-violations"),  # browser CSP report, no key
            ("POST", "/api/session"),  # self-service auth — any authenticated user can create a session
            ("DELETE", "/api/session"),  # self-service auth — any authenticated user can clear their session
            ("POST", "/api/saas/signup"),  # self-service account creation
            ("POST", "/api/saas/aup/accept"),  # P1-COMPLIANCE-001: AUP acceptance (idempotent, any authenticated user)
            ("DELETE", "/api/user/data"),  # self-service data deletion — any authenticated user can delete their own data
            ("POST", "/api/billing/webhook"),  # billing webhook called by PayPal (no API key)
        }
    
        unsafe = [
            row
            for row in matrix
            if (
                row.path.startswith("/api/")
                and row.method != "GET"
                and row.access == "authenticated-user"
                and (row.method, row.path) not in UNAUTHENTICATED_MUTATIONS
            )
        ]
    
>       assert unsafe == []
E       AssertionError: assert [RouteAuthRow...)', notes='')] == []
E         
E         Left contains one more item: RouteAuthRow(method='POST', path='/api/billing/checkout', access='authenticated-user', enforcement='require_role([admin, operator, user])', notes='')
E         Use -v to get more diff

backend/tests/test_route_auth_matrix_generator.py:132: AssertionError
=========================== short test summary info ============================
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_paid_plan_id_to_correct_tier[P-STARTER-TEST123-starter]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_paid_plan_id_to_correct_tier[P-PRO-TEST123-pro]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_paid_plan_id_to_correct_tier[P-ENTERPRISE-TEST123-enterprise]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_unknown_plan_id_falls_back_to_free
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_subscription_status[ACTIVE-active]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_subscription_status[SUSPENDED-past_due]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_subscription_status[CANCELLED-canceled]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_maps_subscription_status[APPROVAL_PENDING-active]
FAILED backend/tests/test_billing_tier_resolution.py::test_get_customer_plan_tier_returns_pro_for_pro_customer
FAILED backend/tests/test_route_auth_matrix_generator.py::test_route_auth_matrix_has_no_user_level_mutations

```

## stderr

```text

```
