"""Unit tests for price history tracking.

Tests: record, get_history, get_trend, record_from_record,
price parsing, boundary conditions, concurrency, singleton.
"""

from __future__ import annotations

import time

from app.price_history import (
    PriceHistory,
    _parse_price,
    get_price_history,
    reset_price_history_for_testing,
)


class TestParsePrice:
    def test_float(self) -> None:
        assert _parse_price(29.99) == 29.99

    def test_int(self) -> None:
        assert _parse_price(30) == 30.0

    def test_usd_string(self) -> None:
        assert _parse_price("$29.99") == 29.99

    def test_euro_string(self) -> None:
        assert _parse_price("29,99 €") == 29.99

    def test_comma_separated(self) -> None:
        assert _parse_price("1,234.56") == 1234.56

    def test_none(self) -> None:
        assert _parse_price(None) is None

    def test_empty_string(self) -> None:
        assert _parse_price("") is None

    def test_non_numeric(self) -> None:
        assert _parse_price("free") is None

    def test_whitespace(self) -> None:
        assert _parse_price("  $ 12.50  ") == 12.50


class TestRecord:
    def test_record_price(self) -> None:
        h = PriceHistory()
        snap = h.record("https://example.com/p1", 29.99, currency="USD")
        assert snap is not None
        assert snap.price == 29.99
        assert snap.currency == "USD"

    def test_record_none_price(self) -> None:
        h = PriceHistory()
        snap = h.record("https://example.com/p1", None)
        assert snap is None

    def test_record_multiple(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0)
        h.record("https://example.com/p1", 15.0)
        hist = h.get_history("https://example.com/p1")
        assert len(hist) == 2

    def test_record_different_fields(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 29.99, field_name="price")
        h.record("https://example.com/p1", 5.99, field_name="shipping")
        price_hist = h.get_history("https://example.com/p1", field_name="price")
        ship_hist = h.get_history("https://example.com/p1", field_name="shipping")
        assert len(price_hist) == 1
        assert len(ship_hist) == 1

    def test_bounded_history(self) -> None:
        h = PriceHistory(max_snapshots_per_key=3)
        for i in range(10):
            h.record("https://example.com/p1", float(i))
        hist = h.get_history("https://example.com/p1")
        assert len(hist) == 3
        # Should keep newest prices (7, 8, 9 -> newest first is 9, 8, 7)
        prices = [s.price for s in hist]
        assert prices == [9.0, 8.0, 7.0]

    def test_timestamp_order(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0, timestamp=100.0)
        h.record("https://example.com/p1", 20.0, timestamp=200.0)
        h.record("https://example.com/p1", 15.0, timestamp=150.0)
        hist = h.get_history("https://example.com/p1")
        assert hist[0].price == 20.0  # newest first
        assert hist[1].price == 15.0
        assert hist[2].price == 10.0

    def test_get_history_limit(self) -> None:
        h = PriceHistory()
        for i in range(10):
            h.record("https://example.com/p1", float(i), timestamp=float(i))
        hist = h.get_history("https://example.com/p1", limit=3)
        assert len(hist) == 3


class TestRecordFromRecord:
    def test_basic(self) -> None:
        h = PriceHistory()
        snaps = h.record_from_record("https://example.com/p1", {"price": 29.99})
        assert len(snaps) == 1
        assert snaps[0].price == 29.99

    def test_multiple_price_fields(self) -> None:
        h = PriceHistory()
        record = {"price": 29.99, "original_price": 49.99, "shipping": 5.99}
        snaps = h.record_from_record(
            "https://example.com/p1",
            record,
            price_fields=("price", "original_price"),
        )
        assert len(snaps) == 2

    def test_currency_extracted(self) -> None:
        h = PriceHistory()
        snaps = h.record_from_record(
            "https://example.com/p1",
            {"price": 29.99, "currency": "USD"},
            price_fields=("price",),
        )
        assert snaps[0].currency == "USD"

    def test_none_price_skipped(self) -> None:
        h = PriceHistory()
        snaps = h.record_from_record("https://example.com/p1", {"price": None})
        assert len(snaps) == 0


class TestGetTrend:
    def test_no_data(self) -> None:
        h = PriceHistory()
        trend = h.get_trend("https://example.com/nonexistent")
        assert trend.sample_count == 0
        assert trend.direction == "new"

    def test_single_snapshot(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 29.99)
        trend = h.get_trend("https://example.com/p1")
        assert trend.current == 29.99
        assert trend.sample_count == 1
        assert trend.direction == "new"

    def test_price_increase(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0, timestamp=100.0)
        h.record("https://example.com/p1", 15.0, timestamp=200.0)
        trend = h.get_trend("https://example.com/p1")
        assert trend.direction == "up"
        assert trend.change_amount == 5.0
        assert trend.change_pct == 50.0
        assert trend.previous == 10.0

    def test_price_decrease(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 20.0, timestamp=100.0)
        h.record("https://example.com/p1", 15.0, timestamp=200.0)
        trend = h.get_trend("https://example.com/p1")
        assert trend.direction == "down"
        assert trend.change_amount == -5.0
        assert trend.previous == 20.0

    def test_price_stable(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0, timestamp=100.0)
        h.record("https://example.com/p1", 10.0, timestamp=200.0)
        trend = h.get_trend("https://example.com/p1")
        assert trend.direction == "stable"
        assert trend.change_amount == 0.0

    def test_min_max_avg(self) -> None:
        h = PriceHistory()
        for price, ts in [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0), (15.0, 4.0)]:
            h.record("https://example.com/p1", price, timestamp=ts)
        trend = h.get_trend("https://example.com/p1")
        assert trend.min_price == 10.0
        assert trend.max_price == 30.0
        assert trend.average_price == 18.75  # (10+20+30+15)/4
        assert trend.sample_count == 4

    def test_volatility(self) -> None:
        h = PriceHistory()
        # All same price -> zero volatility
        for _ in range(5):
            h.record("https://example.com/p1", 10.0, timestamp=time.time())
        trend = h.get_trend("https://example.com/p1")
        assert trend.volatility == 0.0

    def test_trend_field_isolation(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0, field_name="price")
        h.record("https://example.com/p1", 5.0, field_name="shipping")
        price_trend = h.get_trend("https://example.com/p1", field_name="price")
        ship_trend = h.get_trend("https://example.com/p1", field_name="shipping")
        assert price_trend.current == 10.0
        assert ship_trend.current == 5.0


class TestClear:
    def test_clear_single_url(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0)
        h.record("https://example.com/p2", 20.0)
        count = h.clear("https://example.com/p1")
        assert count == 1
        assert h.get_history("https://example.com/p1") == []
        assert len(h.get_history("https://example.com/p2")) == 1

    def test_clear_all(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0)
        h.record("https://example.com/p2", 20.0)
        count = h.clear()
        assert count == 2
        assert h.get_all_keys() == []

    def test_clear_nonexistent(self) -> None:
        h = PriceHistory()
        count = h.clear("https://example.com/nonexistent")
        assert count == 0


class TestGetAllKeys:
    def test_multiple_urls(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/a", 10.0)
        h.record("https://example.com/b", 20.0)
        keys = h.get_all_keys()
        assert len(keys) == 2
        assert ("https://example.com/a", "price") in keys
        assert ("https://example.com/b", "price") in keys


class TestSingleton:
    def test_get_price_history_default(self) -> None:
        reset_price_history_for_testing()
        h1 = get_price_history()
        h2 = get_price_history()
        assert h1 is h2

    def test_singleton_records_persist(self) -> None:
        reset_price_history_for_testing()
        h = get_price_history()
        h.record("https://example.com/p1", 10.0)
        h2 = get_price_history()
        assert len(h2.get_history("https://example.com/p1")) == 1

    def test_reset_for_testing(self) -> None:
        reset_price_history_for_testing()
        h = get_price_history()
        h.record("https://example.com/p1", 10.0)
        reset_price_history_for_testing()
        h2 = get_price_history()
        assert h2.get_history("https://example.com/p1") == []


class TestToDict:
    def test_snapshot_to_dict(self) -> None:
        from app.price_history import PriceSnapshot

        snap = PriceSnapshot(price=29.99, currency="USD", url="https://example.com/p1")
        d = snap.to_dict()
        assert d["price"] == 29.99
        assert d["currency"] == "USD"
        assert d["url"] == "https://example.com/p1"

    def test_trend_to_dict(self) -> None:
        h = PriceHistory()
        h.record("https://example.com/p1", 10.0)
        h.record("https://example.com/p1", 20.0)
        trend = h.get_trend("https://example.com/p1")
        d = trend.to_dict()
        assert d["current"] == 20.0
        assert d["sample_count"] == 2
        assert d["direction"] == "up"


class TestConcurrency:
    def test_concurrent_records(self) -> None:
        """Multiple threads recording to the same history should not lose data."""
        import threading

        h = PriceHistory(max_snapshots_per_key=100)
        n_threads = 8
        records_per_thread = 50
        barrier = threading.Barrier(n_threads)

        def _worker(url_idx: int) -> None:
            barrier.wait()
            url = f"https://example.com/p{url_idx}"
            for i in range(records_per_thread):
                h.record(url, float(i))

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        keys = h.get_all_keys()
        assert len(keys) == n_threads
        for url_idx in range(n_threads):
            url = f"https://example.com/p{url_idx}"
            hist = h.get_history(url)
            assert len(hist) == records_per_thread
