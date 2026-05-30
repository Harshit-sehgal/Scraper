"""Tests for semantic alignment helpers in intent_parser."""

from app.intent_parser import (
    build_semantic_synonym_groups,
    role_tokens_are_exclusive,
    semantic_needs_are_exclusive,
    tokens_to_semantic_need,
)


class TestSemanticAlignmentHelpers:
    def test_build_synonym_groups_from_config(self):
        groups = build_semantic_synonym_groups()
        assert len(groups) >= 5
        price_group = next(g for g in groups if "price" in g)
        assert "cost" in price_group

    def test_tokens_to_semantic_need_price(self):
        assert tokens_to_semantic_need({"price", "fare"}) == "price"

    def test_tokens_to_semantic_need_status(self):
        assert tokens_to_semantic_need({"class", "type"}) == "status"

    def test_semantic_needs_exclusive_status_date(self):
        assert semantic_needs_are_exclusive("status", "date") is True
        assert semantic_needs_are_exclusive("price", "date") is False

    def test_role_tokens_exclusive_source_target(self):
        assert role_tokens_are_exclusive({"source"}, {"target"}) is True
        assert role_tokens_are_exclusive({"source"}, {"source"}) is False
