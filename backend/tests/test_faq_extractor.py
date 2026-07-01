"""Unit tests for FAQ extraction.

Tests both schema.org structured data extraction and heuristic fallback
patterns: details/summary, dt/dd, data attributes, heading+paragraph.
"""

from __future__ import annotations

from app.faq_extractor import extract_faq


def _qa(html: str, **kwargs) -> list[dict]:
    result = extract_faq(html, **kwargs)
    return [p.to_dict() for p in result.pairs]


class TestSchemaJsonLd:
    """FAQPage schema.org JSON-LD extraction."""

    def test_single_qa(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"What is the return policy?",
           "acceptedAnswer":{"@type":"Answer","text":"30-day return policy."}}
        ]}
        </script></body></html>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["question"] == "What is the return policy?"
        assert pairs[0]["answer"] == "30-day return policy."
        assert pairs[0]["source"] == "schema"
        assert pairs[0]["confidence"] >= 0.9

    def test_multiple_qa(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"Q1?","acceptedAnswer":{"@type":"Answer","text":"A1"}},
          {"@type":"Question","name":"Q2?","acceptedAnswer":{"@type":"Answer","text":"A2"}}
        ]}
        </script></body></html>"""
        pairs = _qa(html)
        assert len(pairs) == 2

    def test_suggested_answer(self) -> None:
        """'suggestedAnswer' should be accepted alongside 'acceptedAnswer'."""
        html = """<html><body>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"Q1?","suggestedAnswer":{"@type":"Answer","text":"Suggestion"}}
        ]}
        </script></body></html>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["answer"] == "Suggestion"

    def test_json_ld_list(self) -> None:
        """Top-level JSON-LD can be a list containing an FAQPage."""
        html = """<html><body>
        <script type="application/ld+json">
        [{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"Q?","acceptedAnswer":{"@type":"Answer","text":"A"}}
        ]}]
        </script></body></html>"""
        pairs = _qa(html)
        assert len(pairs) == 1

    def test_standalone_question(self) -> None:
        """A standalone Question (not inside FAQPage) is also extracted."""
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Question","name":"Standalone Q?","acceptedAnswer":{"@type":"Answer","text":"Standalone A"}}
        </script></body></html>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["question"] == "Standalone Q?"

    def test_empty_html(self) -> None:
        assert _qa("") == []

    def test_no_faq(self) -> None:
        html = "<html><body><p>Nothing here.</p></body></html>"
        assert _qa(html) == []


class TestSchemaMicrodata:
    """FAQPage microdata extraction."""

    def test_microdata_single(self) -> None:
        html = """<div itemscope itemtype="https://schema.org/FAQPage">
        <div itemscope itemtype="https://schema.org/Question">
          <h3 itemprop="name">Microdata Q?</h3>
          <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
            <p itemprop="text">Microdata A.</p>
          </div>
        </div></div>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["question"] == "Microdata Q?"
        assert pairs[0]["answer"] == "Microdata A."

    def test_microdata_suggested(self) -> None:
        """suggestedAnswer works in microdata too."""
        html = """<div itemscope itemtype="https://schema.org/FAQPage">
        <div itemscope itemtype="https://schema.org/Question">
          <h3 itemprop="name">Q?</h3>
          <div itemscope itemprop="suggestedAnswer" itemtype="https://schema.org/Answer">
            <p itemprop="text">Suggested A.</p>
          </div>
        </div></div>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["answer"] == "Suggested A."


class TestDetailsSummary:
    """Heuristic extraction from <details>/<summary> patterns."""

    def test_faq_container(self) -> None:
        html = """<div class="faq-container">
        <details><summary>Q1?</summary><p>A1 text.</p></details>
        <details><summary>Q2?</summary><p>A2 text.</p></details>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 2
        assert pairs[0]["question"] == "Q1?"
        assert pairs[1]["source"] == "details"

    def test_no_accordion_container_skipped(self) -> None:
        """<details> outside an accordion container requires question-like summary."""
        html = "<details><summary>Just a note</summary><p>A thing.</p></details>"
        pairs = _qa(html)
        assert len(pairs) == 0

    def test_no_question_outside_container_skipped(self) -> None:
        """Outside a FAQ container, non-question summary is skipped."""
        html = "<details><summary>Some info</summary><p>Not a question.</p></details>"
        pairs = _qa(html)
        assert len(pairs) == 0

    def test_question_outside_container_accepted(self) -> None:
        """Outside a FAQ container, question-like summary is still accepted."""
        html = "<details><summary>What is this?</summary><p>This is a thing.</p></details>"
        pairs = _qa(html)
        assert len(pairs) == 1


class TestDtDd:
    """Heuristic extraction from <dt>/<dd> pairs."""

    def test_faq_container(self) -> None:
        html = """<div class="faq">
        <dl><dt>What is X?</dt><dd>X is a thing.</dd>
            <dt>How does Y work?</dt><dd>Y works via magic.</dd></dl>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 2
        assert pairs[0]["source"] == "dl"

    def test_no_container_skipped(self) -> None:
        html = "<dl><dt>Q?</dt><dd>A.</dd></dl>"
        pairs = _qa(html)
        assert len(pairs) == 0

    def test_faq_id(self) -> None:
        """FAQ containers detected by id attribute."""
        html = """<div id="faq"><dl><dt>Q?</dt><dd>A!</dd></dl></div>"""
        pairs = _qa(html)
        assert len(pairs) == 1


class TestDataAttribute:
    """Heuristic extraction from [data-faq] / [data-question] elements."""

    def test_data_faq(self) -> None:
        html = """<div data-faq="true">
        <p data-question="What is X?" data-answer="X is Y."></p>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["source"] == "data_attr"

    def test_data_question_fallback_content(self) -> None:
        """data-question can use element text content instead of attribute."""
        html = """<div data-faq="true">
        <p data-question="">What is X?</p>
        <p data-answer>X is Y.</p>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 1
        assert pairs[0]["question"] == "What is X?"


class TestHeadingParagraph:
    """Heuristic extraction from heading+paragraph patterns."""

    def test_faq_heading_matches(self) -> None:
        html = """<div class="faq-section">
        <h3>What is the return policy?</h3>
        <p>You can return items within 30 days.</p>
        <h3>How do I track my order?</h3>
        <p>Use the tracking link in your email.</p>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 2
        assert pairs[0]["source"] == "heading"

    def test_non_question_heading_skipped(self) -> None:
        html = """<div class="faq-section">
        <h3>Introduction</h3>
        <p>Some introduction text.</p>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 0

    def test_short_answer_skipped(self) -> None:
        html = """<div class="faq-section">
        <h3>What is this?</h3>
        <p>Short</p>
        </div>"""
        pairs = _qa(html)
        assert len(pairs) == 0


class TestIntegration:
    """End-to-end integration tests."""

    def test_schema_takes_priority(self) -> None:
        """Schema.org should be detected even when heuristic patterns also exist."""
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"Schema Q?","acceptedAnswer":{"@type":"Answer","text":"Schema A"}}
        ]}
        </script>
        <div class="faq">
        <details><summary>Heuristic Q?</summary><p>Heuristic A.</p></details>
        </div>
        </body></html>"""
        result = extract_faq(html)
        pairs = [p.to_dict() for p in result.pairs]
        assert len(pairs) == 1
        assert pairs[0]["question"] == "Schema Q?"
        assert result.source == "schema"

    def test_heuristics_disabled(self) -> None:
        """When enable_heuristics=False, only schema.org is scanned."""
        html = """<div class="faq">
        <details><summary>What is X?</summary><p>X is Y.</p></details>
        </div>"""
        pairs = _qa(html, enable_heuristics=False)
        assert pairs == []

    def test_to_dict_format(self) -> None:
        """Verify the to_dict output format matches expectations."""
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"FAQPage","mainEntity":[
          {"@type":"Question","name":"Q?","acceptedAnswer":{"@type":"Answer","text":"A"}}
        ]}
        </script></body></html>"""
        result = extract_faq(html)
        d = result.to_dict()
        assert d["source"] == "schema"
        assert d["count"] == 1
        assert len(d["pairs"]) == 1
        assert d["pairs"][0]["question"] == "Q?"
