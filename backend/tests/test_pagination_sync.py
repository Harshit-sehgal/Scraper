"""Sync-paginate counterpart of the canonical-5-strategy contract test.

Mirrors the positive + negative pins from
``test_pagination_async.TestCanonicalFiveStrategyContract`` for the sync
``paginate()`` dispatcher in ``app.pagination_executor.py``.

Closes the bilateral half of the ``CAND-P2-PAGINATION-ALIAS-001`` contract:
after the rename (url_parameter → url_pattern) the contract MUST hold for
BOTH ``async_paginate`` (async, browser-driven) AND ``paginate`` (sync,
no-browser). The sync side now fails-closed on unknown strategy keys so
the contract is genuinely bilateral, not silently one-sided.
"""

from __future__ import annotations

import typing
from typing import Any

import pytest
from app.models import WorkflowPaginationConfig
from app.pagination_executor import (
    DEFAULT_PAGINATION_STRATEGY,
    LEGACY_PAGINATION_STRATEGIES,
    LEGACY_TO_CANONICAL_REPLACEMENT,
    PAGINATION_STRATEGIES,
    PaginationConfig,
    paginate,
)
from pydantic import ValidationError


class TestCanonicalFiveStrategyContract:
    """Bilateral mirror of
    ``test_pagination_async.TestCanonicalFiveStrategyContract`` for the
    sync ``paginate()`` dispatcher.

    Pins:

    * Canonical-5 strategies are recognized (no
      ``Unknown pagination strategy`` rejection).
    * Legacy ``url_parameter`` key is explicitly rejected with
      ``Unknown pagination strategy`` (closes the bilateral half of
      ``CAND-P2-PAGINATION-ALIAS-001``).
    * ``WorkflowPaginationConfig`` constant + ``PaginationConfig().strategy``
      default round-trip cleanly through the canonical-5 set and reject
      the legacy typo at config-build time (pydantic v1/v2 dual-life).
    """

    LEGACY_STRATEGY = "url_parameter"
    CANONICAL_STRATEGIES = (
        "next_button",
        "page_number",
        "url_pattern",
        "infinite_scroll",
        "load_more",
    )

    def test_sync_does_not_reject_canonical_strategy_as_unknown(self) -> None:
        """``paginate()`` MUST NOT return the ``Unknown pagination strategy``
        rejection pattern for any canonical-5 strategy.

        Other failure modes (``max_pages``, ``no_new_records``,
        ``max_records``, ``timeout``) are accepted here as long as the
        error message does not match the
        ``(stopped_reason == "error" AND "Unknown pagination strategy"
        in error)`` rejection pattern.

        Catches silent drift if any future refactor renames, drops, or
        misspells one of the canonical keys on the sync side.
        """
        for strategy in self.CANONICAL_STRATEGIES:
            config = PaginationConfig(
                strategy=strategy,
                max_pages=1,
                delay_between_pages=0,
            )
            result = paginate(config)
            is_unknown_strategy_rejection = result.stopped_reason == "error" and "Unknown pagination strategy" in (
                result.error or ""
            )
            assert not is_unknown_strategy_rejection, (
                f"paginate() must not reject canonical "
                f"strategy={strategy!r} as 'Unknown pagination strategy'; "
                f"got result.error={result.error!r}, "
                f"result.stopped_reason={result.stopped_reason!r}"
            )

    def test_sync_rejects_legacy_url_parameter_key(self) -> None:
        """Bilateral regression pin: after the
        ``CAND-P2-PAGINATION-ALIAS-001`` rename, ``paginate()`` MUST
        explicitly reject the legacy ``url_parameter`` key.

        Mirrors
        ``test_pagination_async.TestCanonicalFiveStrategyContract.test_async_rejects_legacy_url_parameter_key``.

        Without this, a future refactor could silently alias the legacy
        key back into the sync ``strategy_map`` (or restore the historic
        ``_paginate_next_button`` default-fallback) and emit data from
        the wrong dispatcher.
        """
        config = PaginationConfig(
            strategy=self.LEGACY_STRATEGY,
            max_pages=1,
            delay_between_pages=0,
        )
        result = paginate(config)
        assert result.stopped_reason == "error", (
            f"legacy url_parameter must reject with stopped_reason='error'; got stopped_reason={result.stopped_reason!r}"
        )
        assert "Unknown pagination strategy" in (result.error or ""), (
            "paginate() must explicitly reject the legacy "
            "url_parameter key (expected 'Unknown pagination strategy' "
            f"error); got error={result.error!r}"
        )
        assert self.LEGACY_STRATEGY in (result.error or ""), (
            f"rejection error should name the offending legacy key for debuggability; got error={result.error!r}"
        )

    def test_workflow_pagination_config_accepts_canonical_only(self) -> None:
        """``PaginationConfig().strategy`` default + ``WorkflowPaginationConfig``
        strategy Literal MUST be mutually consistent with the canonical-5 set,
        AND the legacy ``url_parameter`` MUST be rejected at config-build time.

        This catches any silent drift where one layer keeps a typo'd or stale
        key while the other has been corrected.
        """
        # The default config must use one of the canonical-5 keys,
        # not the legacy typo.
        assert PaginationConfig().strategy in self.CANONICAL_STRATEGIES, (
            f"PaginationConfig default strategy must be one of the canonical 5; got {PaginationConfig().strategy!r}"
        )
        # WorkflowPaginationConfig must accept all 5 canonical keys.
        for strategy in self.CANONICAL_STRATEGIES:
            wf = WorkflowPaginationConfig(strategy=strategy)
            assert wf.strategy == strategy, (
                f"WorkflowPaginationConfig.strategy={strategy!r} round-trip failed; got {wf.strategy!r}"
            )
        # And it MUST reject the legacy typo at config-build time too.
        # Pydantic v2 raises ``ValidationError`` for Literal mismatches;
        # pydantic v1 raises ``ValueError``. Both targets are listed so a
        # future v1-to-v2 swap (or vice-versa) does not silently flip the
        # test into a passing-for-the-wrong-reason state.
        with pytest.raises((ValidationError, ValueError)) as exc_info:
            WorkflowPaginationConfig(strategy=self.LEGACY_STRATEGY)
        assert exc_info.value is not None


class TestCentralizedCanonicalConstant:
    """Regression pin: the centralized ``PAGINATION_STRATEGIES``
    constant in ``app.pagination_executor`` MUST stay in lockstep with:

    * the ``WorkflowPaginationConfig.strategy`` pydantic Literal (the
      API contract surface);
    * the ``DEFAULT_PAGINATION_STRATEGY`` constant (single source of
      truth for the default ``PaginationConfig().strategy``);
    * the canonical-5 set pinned by the bilateral test pair in
      ``TestCanonicalFiveStrategyContract`` (this file) and
      ``test_pagination_async.TestCanonicalFiveStrategyContract``.

    A drift detected here signals that the canonical-5 enum, the
    pydantic Literal, and the centralized constant are no longer
    consistent. Any new strategy addition MUST be applied to all
    THREE locations in lockstep (canonical constant + Literal +
    sync + async strategy_map dispatchers).
    """

    CONSTANT_CANONICAL = (
        "next_button",
        "page_number",
        "url_pattern",
        "infinite_scroll",
        "load_more",
    )

    def test_pagination_strategies_is_frozen_canonical_set(self) -> None:
        """``PAGINATION_STRATEGIES`` is exposed as a frozen canonical
        source-of-truth with exactly the canonical-5 names, and any
        caller attempting to mutate it MUST get a ``TypeError`` /
        ``AttributeError``.
        """
        assert isinstance(PAGINATION_STRATEGIES, frozenset), (
            "PAGINATION_STRATEGIES MUST be a frozenset to enforce "
            "immutability and prevent silent runtime mutation; got "
            f"type={type(PAGINATION_STRATEGIES).__name__}"
        )
        assert set(PAGINATION_STRATEGIES) == set(self.CONSTANT_CANONICAL), (
            f"PAGINATION_STRATEGIES={set(PAGINATION_STRATEGIES)!r} "
            f"must equal the canonical-5 contract {set(self.CONSTANT_CANONICAL)!r}"
        )
        with pytest.raises((AttributeError, TypeError)):
            PAGINATION_STRATEGIES.add("not_a_real_strategy")  # type: ignore[attr-defined]

    def test_pagination_strategies_matches_workflow_pagination_literal(
        self,
    ) -> None:
        """``WorkflowPaginationConfig.strategy`` Literal MUST enumerate
        exactly the 5 names from ``PAGINATION_STRATEGIES``.

        Pydantic v2 stores Literal values in ``model_fields[...].annotation``;
        pydantic v1 stores them in ``__fields__[...].type_``. Both versions
        are supported via ``typing.get_args`` which is comparable across
        pydantic versions.
        """
        if hasattr(WorkflowPaginationConfig, "model_fields"):
            model_fields: Any = WorkflowPaginationConfig.model_fields
            annotation = model_fields["strategy"].annotation
        else:
            legacy_fields: Any = WorkflowPaginationConfig.__fields__
            annotation = legacy_fields["strategy"].type_
        literal_values = set(typing.get_args(annotation))
        assert literal_values == set(PAGINATION_STRATEGIES), (
            "WorkflowPaginationConfig.strategy Literal MUST match "
            f"PAGINATION_STRATEGIES exactly; got Literal={literal_values!r} "
            f"vs PAGINATION_STRATEGIES={set(PAGINATION_STRATEGIES)!r}"
        )

    @pytest.mark.parametrize(
        "strategy",
        sorted(PAGINATION_STRATEGIES),
        ids=lambda strategy: f"strategy={strategy}",
    )
    def test_workflow_pagination_literal_round_trips_each_canonical_strategy(
        self,
        strategy: str,
    ) -> None:
        """Build-time positive pin (parametrized): ``WorkflowPaginationConfig(strategy=s)``
        must succeed and round-trip cleanly for every name in
        ``PAGINATION_STRATEGIES``. Each ``strategy`` parameter is a
        separately identifiable pytest test case so a single failing key
        produces a targeted failure report naming exactly the offending
        strategy instead of a generic loop-position index.
        """
        wf = WorkflowPaginationConfig(strategy=strategy)
        assert wf.strategy == strategy, (
            f"WorkflowPaginationConfig.strategy={strategy!r} round-trip failed; got wf.strategy={wf.strategy!r}"
        )

    def test_default_pagination_strategy_is_in_canonical_set(self) -> None:
        """``DEFAULT_PAGINATION_STRATEGY`` MUST be a member of
        ``PAGINATION_STRATEGIES`` and equal the historically-pinned
        ``"next_button"`` default."""
        assert DEFAULT_PAGINATION_STRATEGY in PAGINATION_STRATEGIES, (
            f"DEFAULT_PAGINATION_STRATEGY={DEFAULT_PAGINATION_STRATEGY!r} "
            f"must be a member of PAGINATION_STRATEGIES="
            f"{set(PAGINATION_STRATEGIES)!r}"
        )
        assert DEFAULT_PAGINATION_STRATEGY == "next_button"
        # Also verify the dataclass default agrees.
        assert PaginationConfig().strategy == DEFAULT_PAGINATION_STRATEGY

    def test_legacy_pagination_strategies_disjoint_from_canonical(self) -> None:
        """``LEGACY_PAGINATION_STRATEGIES`` MUST be disjoint from
        ``PAGINATION_STRATEGIES``: legacy keys are explicitly rejected
        (fail-closed), so they cannot semantically overlap with the
        canonical enum."""
        assert LEGACY_PAGINATION_STRATEGIES.isdisjoint(PAGINATION_STRATEGIES), (
            f"LEGACY_PAGINATION_STRATEGIES={set(LEGACY_PAGINATION_STRATEGIES)!r} "
            f"must not overlap with canonical set "
            f"PAGINATION_STRATEGIES={set(PAGINATION_STRATEGIES)!r}"
        )
        # The post-rename ``url_parameter`` legacy key MUST be enumerated.
        assert "url_parameter" in LEGACY_PAGINATION_STRATEGIES

    def test_legacy_to_canonical_replacement_keys_match_legacy_frozenset(
        self,
    ) -> None:
        """``set(LEGACY_TO_CANONICAL_REPLACEMENT)`` MUST equal
        ``LEGACY_PAGINATION_STRATEGIES``.

        They are the dual sources-of-truth for legacy-alias dispatch:
        the frozenset is the enumeration used by the regression tests
        for "legacy keys are disjoint from canonical", and the dict is
        the replacement map used by ``_format_unknown_strategy_error``
        for the ``(legacy, please use <canonical>)`` suffix.

        If a future maintainer adds to one but not the other, the
        error message either silently defaults to the non-suffixed
        variant (key in frozenset but not in dict) or the
        dispatcher's exception handler throws ``KeyError`` (key in
        dict but not in frozenset). The bilateral regression tests
        in ``TestCanonicalFiveStrategyContract`` cover both halves;
        this test specifically pins the equality of the two sources.
        """
        assert set(LEGACY_TO_CANONICAL_REPLACEMENT) == LEGACY_PAGINATION_STRATEGIES, (
            f"LEGACY_TO_CANONICAL_REPLACEMENT keys must match "
            f"LEGACY_PAGINATION_STRATEGIES; "
            f"got dict_keys={set(LEGACY_TO_CANONICAL_REPLACEMENT)!r} "
            f"vs frozenset={set(LEGACY_PAGINATION_STRATEGIES)!r}"
        )

    def test_dispatcher_error_message_includes_legacy_suffix_for_url_parameter(
        self,
    ) -> None:
        """``paginate()`` MUST return an Unknown-error message with the
        ``(legacy, please use url_pattern)`` suffix when called with
        ``strategy="url_parameter"``.

        Mirrors the equivalent bilinear pin in
        ``test_pagination_async.TestCanonicalFiveStrategyContract.test_async_rejects_legacy_url_parameter_key``
        + the new ``_format_unknown_strategy_error`` dispatch path.
        """
        config = PaginationConfig(
            strategy="url_parameter",
            max_pages=1,
            delay_between_pages=0,
        )
        result = paginate(config)
        assert result.stopped_reason == "error"
        expected_suffix = "(legacy, please use url_pattern)"
        assert expected_suffix in (result.error or ""), (
            f"paginate() error must include the debuggable "
            f"{expected_suffix!r} suffix for url_parameter; "
            f"got error={result.error!r}"
        )
        assert "Unknown pagination strategy: url_parameter" in (result.error or "")
