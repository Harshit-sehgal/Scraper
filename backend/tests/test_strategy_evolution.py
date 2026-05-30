"""
Tests for Strategy Evolution Engine

Tests the autonomous fetch strategy selection and evolution system:
- Per-domain strategy performance tracking
- Strategy recommendations based on performance
- Automatic strategy switching when degraded
- Learning from successful/failed attempts
- Strategy evolution and exploration
"""

from app.strategy_evolution import (
    FetchStrategy,
    StrategyPerformance,
    DomainStrategyState,
    StrategyEvolutionEngine,
    get_strategy_evolution_engine,
)


class TestFetchStrategy:
    """Test FetchStrategy enum."""

    def test_all_strategies_defined(self):
        """Test that all strategies are available."""
        strategies = [
            FetchStrategy.PLAYWRIGHT_FULL,
            FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT,
            FetchStrategy.PLAYWRIGHT_STEALTH,
            FetchStrategy.HTTPX_BASIC,
            FetchStrategy.HTTPX_WITH_UA,
            FetchStrategy.HTTPX_SMART,
            FetchStrategy.HYBRID,
            FetchStrategy.CACHED,
        ]

        assert len(strategies) == 8
        assert all(isinstance(s, FetchStrategy) for s in strategies)

    def test_strategy_string_values(self):
        """Test that strategy values are strings."""
        assert isinstance(FetchStrategy.PLAYWRIGHT_FULL.value, str)
        assert FetchStrategy.PLAYWRIGHT_FULL.value == "playwright_full"


class TestStrategyPerformance:
    """Test strategy performance tracking."""

    def test_create_strategy_performance(self):
        """Test creating strategy performance record."""
        perf = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
        )

        assert perf.domain == "example.com"
        assert perf.strategy == FetchStrategy.PLAYWRIGHT_FULL
        assert perf.success_count == 0
        assert perf.failure_count == 0
        assert perf.consecutive_failures == 0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        perf = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.HTTPX_BASIC,
            success_count=8,
            failure_count=2,
        )

        assert perf.success_rate == 0.8

    def test_success_rate_no_attempts(self):
        """Test success rate with no attempts."""
        perf = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
        )

        assert perf.success_rate == 0.0

    def test_avg_time_calculation(self):
        """Test average time calculation."""
        perf = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT,
            success_count=10,
            total_time_ms=1000.0,
        )

        assert perf.avg_time_ms == 100.0  # 1000 / 10

    def test_is_healthy_property(self):
        """Test is_healthy property."""
        # Healthy: high success rate, no failures
        healthy = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success_count=10,
            failure_count=1,
        )
        assert healthy.is_healthy is True

        # Not healthy: low success rate
        unhealthy = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success_count=3,
            failure_count=7,
        )
        assert unhealthy.is_healthy is False

    def test_is_degraded_property(self):
        """Test is_degraded property."""
        # Degraded: too many consecutive failures
        degraded = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success_count=1,
            failure_count=4,
            consecutive_failures=5,
        )
        assert degraded.is_degraded is True

        # Degraded: low success rate
        low_success = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success_count=2,
            failure_count=8,
        )
        assert low_success.is_degraded is True

    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        perf = StrategyPerformance(
            domain="example.com",
            strategy=FetchStrategy.HTTPX_BASIC,
            success_count=5,
            failure_count=1,
        )

        perf_dict = perf.to_dict()

        assert isinstance(perf_dict, dict)
        assert perf_dict["domain"] == "example.com"
        assert perf_dict["success_count"] == 5


class TestDomainStrategyState:
    """Test per-domain strategy state tracking."""

    def test_create_domain_strategy_state(self):
        """Test creating domain strategy state."""
        state = DomainStrategyState(domain="example.com")

        assert state.domain == "example.com"
        assert len(state.strategies) == 8  # All strategies initialized
        assert state.current_strategy == FetchStrategy.PLAYWRIGHT_FULL

    def test_all_strategies_initialized(self):
        """Test that all strategies are initialized."""
        state = DomainStrategyState(domain="example.com")

        for strategy in FetchStrategy:
            assert strategy in state.strategies
            perf = state.strategies[strategy]
            assert perf.domain == "example.com"
            assert perf.success_count == 0

    def test_record_success_attempt(self):
        """Test recording a successful fetch attempt."""
        state = DomainStrategyState(domain="example.com")

        state.record_attempt(
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=True,
            time_ms=150.0,
            quality=0.95,
        )

        perf = state.strategies[FetchStrategy.PLAYWRIGHT_FULL]
        assert perf.success_count == 1
        assert perf.failure_count == 0
        assert perf.consecutive_failures == 0
        assert perf.total_time_ms == 150.0
        # First record uses exponential moving average: alpha=0.3, so 0.3 * 0.95 = 0.285
        assert perf.avg_quality == 0.285

    def test_record_failure_attempt(self):
        """Test recording a failed fetch attempt."""
        state = DomainStrategyState(domain="example.com")

        state.record_attempt(
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=False,
            time_ms=200.0,
            failure_reason="timeout",
        )

        perf = state.strategies[FetchStrategy.PLAYWRIGHT_FULL]
        assert perf.success_count == 0
        assert perf.failure_count == 1
        assert perf.consecutive_failures == 1

    def test_multiple_attempts_success_rate(self):
        """Test success rate with multiple attempts."""
        state = DomainStrategyState(domain="example.com")
        strategy = FetchStrategy.HTTPX_BASIC

        # 8 successes, 2 failures
        for _ in range(8):
            state.record_attempt(strategy, success=True, time_ms=100.0)
        for _ in range(2):
            state.record_attempt(strategy, success=False, time_ms=100.0)

        perf = state.strategies[strategy]
        assert perf.success_rate == 0.8

    def test_get_best_strategy(self):
        """Test getting best performing strategy."""
        state = DomainStrategyState(domain="example.com")

        # Give PLAYWRIGHT_FULL 9/10 successes
        for _ in range(9):
            state.record_attempt(FetchStrategy.PLAYWRIGHT_FULL, success=True, time_ms=100.0)
        state.record_attempt(FetchStrategy.PLAYWRIGHT_FULL, success=False, time_ms=100.0)

        # Give HTTPX_BASIC 1/10 successes
        for _ in range(1):
            state.record_attempt(FetchStrategy.HTTPX_BASIC, success=True, time_ms=100.0)
        for _ in range(9):
            state.record_attempt(FetchStrategy.HTTPX_BASIC, success=False, time_ms=100.0)

        best = state.get_best_strategy()
        assert best == FetchStrategy.PLAYWRIGHT_FULL

    def test_get_worst_strategy(self):
        """Test getting worst performing strategy."""
        state = DomainStrategyState(domain="example.com")

        # Give one strategy many failures
        for _ in range(10):
            state.record_attempt(FetchStrategy.HTTPX_BASIC, success=False, time_ms=100.0)
        state.record_attempt(FetchStrategy.HTTPX_BASIC, success=True, time_ms=100.0)

        worst = state.get_worst_strategy()
        assert worst == FetchStrategy.HTTPX_BASIC


class TestStrategyEvolutionEngine:
    """Test strategy evolution engine."""

    def test_create_strategy_evolution_engine(self):
        """Test creating strategy evolution engine."""
        engine = StrategyEvolutionEngine()

        assert isinstance(engine, StrategyEvolutionEngine)
        assert len(engine.domain_states) == 0

    def test_record_fetch_attempt(self):
        """Test recording a fetch attempt."""
        engine = StrategyEvolutionEngine()

        engine.record_fetch_attempt(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=True,
            time_ms=150.0,
            quality=0.95,
        )

        state = engine.domain_states["example.com"]
        perf = state.strategies[FetchStrategy.PLAYWRIGHT_FULL]
        assert perf.success_count == 1

    def test_record_multiple_attempts(self):
        """Test recording multiple attempts."""
        engine = StrategyEvolutionEngine()

        for i in range(5):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=(i < 4),  # 4 successes, 1 failure
                time_ms=100.0 + i,
                quality=0.9,
            )

        state = engine.domain_states["example.com"]
        perf = state.strategies[FetchStrategy.PLAYWRIGHT_FULL]
        assert perf.success_count == 4
        assert perf.failure_count == 1

    def test_recommend_strategy_insufficient_data(self):
        """Test strategy recommendation with insufficient data."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        recommendation = engine.recommend_strategy("new-domain.com")

        assert recommendation.recommended_strategy == FetchStrategy.PLAYWRIGHT_FULL
        # Cold start uses confidence 0.4 which is < 0.5
        assert recommendation.confidence < 0.5
        assert "Cold start" in recommendation.reason

    def test_recommend_strategy_with_data(self):
        """Test strategy recommendation with sufficient data."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        # Record 10 attempts with high success on PLAYWRIGHT_FULL
        for _ in range(9):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )
        engine.record_fetch_attempt(
            domain="example.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=False,
            time_ms=200.0,
        )

        recommendation = engine.recommend_strategy("example.com")

        assert recommendation.recommended_strategy == FetchStrategy.PLAYWRIGHT_FULL
        assert recommendation.confidence > 0.5
        assert isinstance(recommendation.alternatives, list)

    def test_recommendation_confidence_increases_with_success(self):
        """Test that confidence increases with high success rates."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        # Low success domain
        for _ in range(3):
            engine.record_fetch_attempt(
                domain="low-success.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=False,
                time_ms=100.0,
            )
        engine.record_fetch_attempt(
            domain="low-success.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=True,
            time_ms=100.0,
            quality=0.5,
        )

        low_rec = engine.recommend_strategy("low-success.com")

        # High success domain
        for _ in range(10):
            engine.record_fetch_attempt(
                domain="high-success.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        high_rec = engine.recommend_strategy("high-success.com")

        assert high_rec.confidence > low_rec.confidence

    def test_should_switch_strategy_healthy(self):
        """Test that healthy strategies don't trigger switch."""
        engine = StrategyEvolutionEngine()

        # Record healthy performance
        for _ in range(10):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        should_switch = engine.should_switch_strategy("example.com")
        assert should_switch is False

    def test_should_switch_strategy_degraded(self):
        """Test that degraded strategies trigger switch."""
        engine = StrategyEvolutionEngine()

        # Record degraded performance (consecutive failures)
        state = engine._get_or_create_state("example.com")
        state.current_strategy = FetchStrategy.PLAYWRIGHT_FULL

        for _ in range(4):
            state.record_attempt(
                FetchStrategy.PLAYWRIGHT_FULL,
                success=False,
                time_ms=100.0,
            )

        should_switch = engine.should_switch_strategy("example.com")
        assert should_switch is True

    def test_evolve_strategy_picks_best(self):
        """Test that evolution picks best available strategy."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        # Set up multiple strategies with different performance
        for _ in range(8):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        for _ in range(2):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.HTTPX_BASIC,
                success=True,
                time_ms=50.0,
                quality=0.85,
            )

        for _ in range(5):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT,
                success=False,
                time_ms=100.0,
            )

        new_strategy = engine.evolve_strategy("example.com")

        # Should recommend PLAYWRIGHT_FULL (best success rate)
        assert new_strategy in [FetchStrategy.PLAYWRIGHT_FULL, FetchStrategy.HTTPX_BASIC]

    def test_get_domain_strategy_report(self):
        """Test generating domain strategy report."""
        engine = StrategyEvolutionEngine()

        # Record some attempts
        for _ in range(5):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        report = engine.get_domain_strategy_report("example.com")

        assert report["domain"] == "example.com"
        assert "current_strategy" in report
        assert "strategies" in report
        assert isinstance(report["strategies"], list)
        assert len(report["strategies"]) == 8
        assert "success_rate" in report["strategies"][0]

    def test_get_all_domains_strategy_report(self):
        """Test generating report for all domains."""
        engine = StrategyEvolutionEngine()

        # Record attempts for multiple domains
        for domain in ["site1.com", "site2.com", "site3.com"]:
            for _ in range(5):
                engine.record_fetch_attempt(
                    domain=domain,
                    strategy=FetchStrategy.PLAYWRIGHT_FULL,
                    success=True,
                    time_ms=100.0,
                    quality=0.95,
                )

        report = engine.get_all_domains_strategy_report()

        assert report["total_domains"] == 3
        assert isinstance(report["domains"], list)
        assert len(report["domains"]) == 3
        assert "avg_success_rate" in report

    def test_strategy_caching(self):
        """Test that strategy recommendations are consistent."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        # Record initial data
        for _ in range(5):
            engine.record_fetch_attempt(
                domain="example.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        # First recommendation
        rec1 = engine.recommend_strategy("example.com")

        # Second recommendation should be the same
        rec2 = engine.recommend_strategy("example.com")

        assert rec1.recommended_strategy == rec2.recommended_strategy


class TestStrategyEvolutionGlobal:
    """Test global singleton access."""

    def test_get_strategy_evolution_engine_singleton(self):
        """Test that get_strategy_evolution_engine returns singleton."""
        engine1 = get_strategy_evolution_engine()
        engine2 = get_strategy_evolution_engine()

        assert engine1 is engine2

    def test_engine_preserves_state_across_calls(self):
        """Test that engine preserves state across calls."""
        engine = get_strategy_evolution_engine()

        # Record attempt
        engine.record_fetch_attempt(
            domain="persistent.com",
            strategy=FetchStrategy.PLAYWRIGHT_FULL,
            success=True,
            time_ms=100.0,
            quality=0.95,
        )

        # State should be preserved on second call
        report = engine.get_domain_strategy_report("persistent.com")
        assert report["domain"] == "persistent.com"


class TestIntegrationStrategyEvolution:
    """Integration tests for strategy evolution."""

    def test_end_to_end_strategy_learning_and_evolution(self):
        """Test complete strategy learning and evolution workflow."""
        engine = StrategyEvolutionEngine()
        domain = "ecommerce.example.com"

        # Phase 1: Initial exploration (all strategies have some data)
        attempts = [
            (FetchStrategy.PLAYWRIGHT_FULL, True, 0.95),
            (FetchStrategy.PLAYWRIGHT_FULL, True, 0.94),
            (FetchStrategy.PLAYWRIGHT_LIGHTWEIGHT, True, 0.90),
            (FetchStrategy.HTTPX_BASIC, False, 0.0),
            (FetchStrategy.HTTPX_WITH_UA, True, 0.85),
        ]

        for strategy, success, quality in attempts:
            engine.record_fetch_attempt(
                domain=domain,
                strategy=strategy,
                success=success,
                time_ms=100.0,
                quality=quality,
            )

        # Phase 2: Recommend based on initial data
        engine.recommend_strategy(domain)
        # Should recommend PLAYWRIGHT_FULL (best so far)

        # Phase 3: Continue learning
        for _ in range(8):
            engine.record_fetch_attempt(
                domain=domain,
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        # Disable exploration to get deterministic recommendation
        engine.exploration_probability = 0.0

        # Phase 4: Evolve strategy
        evolved = engine.evolve_strategy(domain)
        assert evolved == FetchStrategy.PLAYWRIGHT_FULL

        # Phase 5: Check final report
        report = engine.get_domain_strategy_report(domain)
        assert report["total_attempts"] > 5
        assert report["current_strategy"] == FetchStrategy.PLAYWRIGHT_FULL.value

    def test_strategy_switch_on_degradation(self):
        """Test that strategy switches when current one degrades."""
        engine = StrategyEvolutionEngine()
        domain = "example.com"

        # Record good performance for PLAYWRIGHT_FULL
        for _ in range(10):
            engine.record_fetch_attempt(
                domain=domain,
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        # Record better performance for HTTPX_BASIC
        for _ in range(5):
            engine.record_fetch_attempt(
                domain=domain,
                strategy=FetchStrategy.HTTPX_BASIC,
                success=True,
                time_ms=50.0,
                quality=0.93,
            )

        # Simulate degradation of PLAYWRIGHT_FULL
        state = engine.domain_states[domain]
        state.current_strategy = FetchStrategy.PLAYWRIGHT_FULL
        for _ in range(5):
            state.record_attempt(FetchStrategy.PLAYWRIGHT_FULL, success=False, time_ms=100.0)

        # Check if switch is recommended
        should_switch = engine.should_switch_strategy(domain)
        assert should_switch is True

        # Evolve should pick better strategy
        new_strategy = engine.evolve_strategy(domain)
        assert new_strategy != FetchStrategy.PLAYWRIGHT_FULL

    def test_multiple_domains_independent_evolution(self):
        """Test that multiple domains evolve independently."""
        engine = StrategyEvolutionEngine()
        engine.exploration_probability = 0.0

        # Domain 1: Prefers PLAYWRIGHT_FULL
        for _ in range(10):
            engine.record_fetch_attempt(
                domain="dom1.com",
                strategy=FetchStrategy.PLAYWRIGHT_FULL,
                success=True,
                time_ms=100.0,
                quality=0.95,
            )

        # Domain 2: Prefers HTTPX_BASIC
        for _ in range(10):
            engine.record_fetch_attempt(
                domain="dom2.com",
                strategy=FetchStrategy.HTTPX_BASIC,
                success=True,
                time_ms=50.0,
                quality=0.90,
            )

        rec1 = engine.recommend_strategy("dom1.com")
        rec2 = engine.recommend_strategy("dom2.com")

        # Each domain should have different recommendations
        assert rec1.recommended_strategy == FetchStrategy.PLAYWRIGHT_FULL
        assert rec2.recommended_strategy == FetchStrategy.HTTPX_BASIC
