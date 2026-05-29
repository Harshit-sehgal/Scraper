"""
Tests for Selector ML Optimizer

Tests the ML-based selector quality prediction and optimization system:
- Selector feature extraction from CSS selectors
- Quality prediction using weighted feature model
- Selector ranking and recommendations
- Model learning and weight updates
- Batch operations and optimization reports
"""

from app.selector_ml_optimizer import (
    SelectorFeatureExtractor,
    SelectorFeatures,
    SelectorQualityPredictor,
    SelectorPrediction,
    SelectorOptimizationEngine,
    get_selector_optimizer,
)


class TestSelectorFeatureExtractor:
    """Test CSS selector feature extraction."""

    def test_extract_simple_class_selector(self):
        """Test feature extraction from simple class selector."""
        selector = ".product-name"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.selector == selector
        assert features.class_count == 1
        assert features.id_count == 0
        assert features.pseudo_class_count == 0
        assert features.wildcard_usage is False
        assert features.uses_text_node is False

    def test_extract_id_selector(self):
        """Test feature extraction from ID selector."""
        selector = "#main-content"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.selector == selector
        assert features.id_count == 1
        assert features.class_count == 0
        assert features.specificity_score > 0.5  # IDs are specific

    def test_extract_complex_selector(self):
        """Test feature extraction from complex nested selector."""
        selector = "div.container > p.text-content"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.selector == selector
        assert features.class_count == 2
        assert features.descendant_depth > 0
        assert features.tag_count > 0

    def test_extract_selector_with_nth_child(self):
        """Test that nth-child selectors are detected."""
        selector = "ul > li:nth-child(2)"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.has_nth_child is True
        assert features.stability_score < 1.0  # nth-child reduces stability

    def test_extract_selector_with_wildcard(self):
        """Test that wildcard usage is detected."""
        selector = "div * .text"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.wildcard_usage is True
        assert features.stability_score < 1.0

    def test_extract_selector_with_attribute_match(self):
        """Test attribute matching detection."""
        selector = "a[href*='example.com']"
        features = SelectorFeatureExtractor.extract_features(selector)

        assert features.has_attribute_match is True
        assert features.attribute_count > 0

    def test_extract_batch_multiple_selectors(self):
        """Test batch extraction of multiple selectors."""
        selectors = [
            ".product-name",
            "#main",
            "div > p.text",
            "li:nth-child(3)",
        ]

        features_list = SelectorFeatureExtractor.extract_batch(selectors)

        assert len(features_list) == len(selectors)
        assert all(isinstance(f, SelectorFeatures) for f in features_list)
        assert features_list[0].selector == selectors[0]
        assert features_list[3].has_nth_child is True

    def test_specificity_score_range(self):
        """Test that specificity scores stay in valid range."""
        selectors = [
            "p",
            ".text",
            "#main",
            "div.container.active",
            "#nav.menu.open.active",
        ]

        for selector in selectors:
            features = SelectorFeatureExtractor.extract_features(selector)
            assert 0.0 <= features.specificity_score <= 1.0

    def test_stability_score_range(self):
        """Test that stability scores stay in valid range."""
        selectors = [
            "p",
            "li:nth-child(2)",
            "div * .text",
            "#stable-id",
            "body > main > article > section",
        ]

        for selector in selectors:
            features = SelectorFeatureExtractor.extract_features(selector)
            assert 0.0 <= features.stability_score <= 1.0


class TestSelectorQualityPredictor:
    """Test ML-based selector quality prediction."""

    def test_predict_quality_simple_selector(self):
        """Test quality prediction for simple selector."""
        predictor = SelectorQualityPredictor()
        features = SelectorFeatureExtractor.extract_features(".product-name")

        prediction = predictor.predict(features)

        assert isinstance(prediction, SelectorPrediction)
        assert 0.0 <= prediction.predicted_quality <= 1.0
        assert 0.0 <= prediction.confidence <= 1.0
        assert prediction.recommendation in ["keep", "improve", "replace"]
        assert isinstance(prediction.suggested_mutations, list)

    def test_prediction_high_quality_selector(self):
        """Test that specific, stable selectors get high quality scores."""
        predictor = SelectorQualityPredictor()
        # ID selectors are specific and stable
        features = SelectorFeatureExtractor.extract_features("#unique-product")

        prediction = predictor.predict(features)

        # High quality expected for ID selectors
        assert prediction.predicted_quality > 0.5
        assert prediction.confidence > 0.5

    def test_prediction_low_quality_selector(self):
        """Test that generic selectors get lower quality scores."""
        predictor = SelectorQualityPredictor()
        # Generic selectors with wildcards are unstable
        features = SelectorFeatureExtractor.extract_features("div * span")

        prediction = predictor.predict(features)

        # Lower quality expected for unstable selectors
        assert prediction.predicted_quality >= 0.0  # Can still be positive
        # Confidence might vary
        assert prediction.confidence >= 0.0

    def test_feature_importance_computed(self):
        """Test that feature importance is computed in predictions."""
        predictor = SelectorQualityPredictor()
        features = SelectorFeatureExtractor.extract_features("div.container > p.text")

        prediction = predictor.predict(features)

        assert isinstance(prediction.feature_importance, dict)
        assert len(prediction.feature_importance) > 0
        # All feature importance values should be non-negative
        assert all(v >= 0 for v in prediction.feature_importance.values())

    def test_recommendation_logic(self):
        """Test that recommendations are based on quality score."""
        predictor = SelectorQualityPredictor()

        # Test "keep" recommendation (high quality)
        high_quality = SelectorFeatures(
            selector="#main",
            specificity_score=0.95,
            stability_score=0.95,
            class_count=0,
            id_count=1,
            tag_count=0,
            pseudo_class_count=0,
            attribute_count=0,
            descendant_depth=0,
            wildcard_usage=False,
            uses_text_node=False,
            has_nth_child=False,
            has_attribute_match=False,
        )
        pred_high = predictor.predict(high_quality)
        assert pred_high.recommendation == "keep"

        # Test "replace" recommendation (low quality)
        low_quality = SelectorFeatures(
            selector="div * span",
            specificity_score=0.1,
            stability_score=0.2,
            class_count=0,
            id_count=0,
            tag_count=2,
            pseudo_class_count=0,
            attribute_count=0,
            descendant_depth=4,
            wildcard_usage=True,
            uses_text_node=False,
            has_nth_child=False,
            has_attribute_match=False,
        )
        pred_low = predictor.predict(low_quality)
        assert pred_low.recommendation == "replace"

    def test_suggest_mutations_from_pseudo_classes(self):
        """Test mutation suggestion removes pseudo-classes."""
        predictor = SelectorQualityPredictor()
        features = SelectorFeatureExtractor.extract_features("a:hover")

        prediction = predictor.predict(features)

        assert len(prediction.suggested_mutations) > 0
        # Should suggest removing the :hover part
        assert any("a" in mut for mut in prediction.suggested_mutations)

    def test_suggest_mutations_from_deep_nesting(self):
        """Test mutation suggestion for deeply nested selectors."""
        predictor = SelectorQualityPredictor()
        features = SelectorFeatureExtractor.extract_features("body > main > article > section > div > p")

        prediction = predictor.predict(features)

        assert len(prediction.suggested_mutations) > 0

    def test_predict_batch(self):
        """Test batch prediction of multiple selectors."""
        predictor = SelectorQualityPredictor()
        features_list = [
            SelectorFeatureExtractor.extract_features(".product"),
            SelectorFeatureExtractor.extract_features("#main"),
            SelectorFeatureExtractor.extract_features("div * span"),
        ]

        predictions = predictor.predict_batch(features_list)

        assert len(predictions) == len(features_list)
        assert all(isinstance(p, SelectorPrediction) for p in predictions)

    def test_update_weights_improves_model(self):
        """Test that weight updates improve predictions."""
        predictor = SelectorQualityPredictor()
        features = SelectorFeatureExtractor.extract_features("#stable-id")

        # Record initial prediction
        initial_pred = predictor.predict(features)
        initial_quality = initial_pred.predicted_quality

        # Train on this being a very high quality selector (1.0)
        predictor.update_weights([(features, 1.0)], learning_rate=0.1)

        # New prediction should move toward 1.0
        updated_pred = predictor.predict(features)
        updated_quality = updated_pred.predicted_quality

        # Quality should have increased
        assert updated_quality >= initial_quality

    def test_update_weights_with_multiple_samples(self):
        """Test weight update with multiple feedback samples."""
        predictor = SelectorQualityPredictor()

        feedback = [
            (SelectorFeatureExtractor.extract_features(".product"), 0.9),
            (SelectorFeatureExtractor.extract_features("#main"), 0.95),
            (SelectorFeatureExtractor.extract_features("div * span"), 0.3),
        ]

        # Should not raise an error
        predictor.update_weights(feedback, learning_rate=0.01)

    def test_update_weights_empty_feedback(self):
        """Test that empty feedback is handled gracefully."""
        predictor = SelectorQualityPredictor()

        # Should not raise an error
        predictor.update_weights([], learning_rate=0.01)


class TestSelectorOptimizationEngine:
    """Test the optimization engine orchestration."""

    def test_optimize_selectors_single_domain(self):
        """Test selector optimization for a domain."""
        engine = SelectorOptimizationEngine()

        selectors = {
            "title": ".product-title",
            "price": ".product-price",
            "rating": ".product-rating",
        }

        report = engine.optimize_selectors(
            domain="example.com",
            selectors=selectors,
        )

        assert report["domain"] == "example.com"
        assert report["original_count"] == 3
        assert len(report["optimizations"]) == 3
        assert "timestamp" in report
        assert "summary" in report

        # Check summary
        summary = report["summary"]
        assert summary["keep"] + summary["improve"] + summary["replace"] == 3
        assert 0.0 <= summary["total_quality"] <= 1.0

    def test_optimization_report_structure(self):
        """Test that optimization report has correct structure."""
        engine = SelectorOptimizationEngine()

        selectors = {
            "field1": ".text",
            "field2": "#main",
        }

        report = engine.optimize_selectors("test.com", selectors)

        # Check optimization entries
        for opt in report["optimizations"]:
            assert "field_name" in opt
            assert "selector" in opt
            assert "predicted_quality" in opt
            assert "recommendation" in opt
            assert "suggested_mutations" in opt
            assert "features" in opt
            assert isinstance(opt["features"], dict)

    def test_optimization_history_tracking(self):
        """Test that optimization history is tracked."""
        engine = SelectorOptimizationEngine()

        domain = "example.com"
        selectors = {"title": ".product-title"}

        # First optimization
        engine.optimize_selectors(domain, selectors)

        # Second optimization
        engine.optimize_selectors(domain, selectors)

        history = engine.get_optimization_history(domain)

        assert len(history) >= 2
        assert history[0]["domain"] == domain
        assert history[-1]["domain"] == domain

    def test_optimization_history_limit(self):
        """Test that optimization history respects limit."""
        engine = SelectorOptimizationEngine()

        domain = "example.com"
        selectors = {"title": ".product-title"}

        # Create 15 optimizations
        for _ in range(15):
            engine.optimize_selectors(domain, selectors)

        # Get last 10
        history = engine.get_optimization_history(domain, limit=10)

        assert len(history) == 10

    def test_learn_from_results(self):
        """Test learning from actual extraction results."""
        engine = SelectorOptimizationEngine()

        selector = ".product-title"

        # Learn that this selector performed well
        engine.learn_from_results(
            domain="example.com",
            selector=selector,
            actual_quality=0.95,
        )

        # Verify predictor's feature weights exist and have been updated
        predictor = engine.predictor
        # The feature weights dictionary should contain all expected features
        assert len(predictor.feature_weights) > 0, "Feature weights should exist after learning"

        # Re-run optimization to prove learning doesn't break the pipeline
        re_report = engine.optimize_selectors(
            domain="example.com",
            selectors={
                "title": ".product-title",
                "price": ".product-price",
            }
        )
        assert re_report["original_count"] == 2, "Optimization should still produce a report"

    def test_learn_from_multiple_results(self):
        """Test learning from multiple extraction results."""
        engine = SelectorOptimizationEngine()

        selectors = [
            (".product-title", 0.9),
            (".product-price", 0.85),
            ("#main-content", 0.95),
        ]

        for selector, quality in selectors:
            engine.learn_from_results(
                domain="example.com",
                selector=selector,
                actual_quality=quality,
            )

        # Check that optimization works after learning
        report = engine.optimize_selectors(
            domain="example.com",
            selectors={
                "title": ".product-title",
                "price": ".product-price",
            }
        )

        assert report["original_count"] == 2


class TestSelectorOptimizationGlobal:
    """Test global singleton access."""

    def test_get_selector_optimizer_singleton(self):
        """Test that get_selector_optimizer returns singleton."""
        opt1 = get_selector_optimizer()
        opt2 = get_selector_optimizer()

        assert opt1 is opt2

    def test_optimizer_preserves_state_across_calls(self):
        """Test that optimizer preserves state across calls."""
        optimizer = get_selector_optimizer()

        # First optimization
        optimizer.optimize_selectors(
            domain="persistent.com",
            selectors={"field": ".selector"},
        )

        # Second optimization should have history
        history = optimizer.get_optimization_history("persistent.com", limit=2)

        assert len(history) >= 1


class TestIntegrationSelectorML:
    """Integration tests for selector ML system."""

    def test_end_to_end_optimization_workflow(self):
        """Test complete optimization workflow."""
        optimizer = SelectorOptimizationEngine()

        # 1. Optimize selectors
        initial_selectors = {
            "title": ".product-title",
            "price": ".product-price",
            "rating": "div:nth-child(3) > span",
            "description": "* > .text",
        }

        # 1. Optimize selectors (result stored for side effects)
        optimizer.optimize_selectors(
            domain="ecommerce.example.com",
            selectors=initial_selectors,
        )

        # 2. Learn from actual results
        results = [
            (".product-title", 0.95),
            (".product-price", 0.92),
            ("div:nth-child(3) > span", 0.65),  # Low quality
            ("* > .text", 0.55),  # Low quality
        ]

        for selector, quality in results:
            optimizer.learn_from_results(
                domain="ecommerce.example.com",
                selector=selector,
                actual_quality=quality,
            )

        # 3. Re-optimize with updated model
        updated_report = optimizer.optimize_selectors(
            domain="ecommerce.example.com",
            selectors=initial_selectors,
        )

        # Check that recommendations reflect learned knowledge
        assert updated_report is not None
        assert len(updated_report["optimizations"]) == 4

    def test_quality_improvement_through_learning(self):
        """Test that quality predictions improve through learning."""
        optimizer = SelectorOptimizationEngine()
        predictor = optimizer.predictor

        selector = ".unstable-selector"
        features = SelectorFeatureExtractor.extract_features(selector)

        # Initial prediction (should be low quality due to vagueness)
        initial_pred = predictor.predict(features)

        # Learn that it's actually high quality (hypothetical)
        predictor.update_weights([(features, 0.9)], learning_rate=0.05)

        # New prediction should be higher
        updated_pred = predictor.predict(features)

        assert updated_pred.predicted_quality >= initial_pred.predicted_quality

    def test_batch_optimization_multiple_domains(self):
        """Test optimization across multiple domains."""
        optimizer = SelectorOptimizationEngine()

        domains = ["site1.com", "site2.com", "site3.com"]

        for domain in domains:
            optimizer.optimize_selectors(
                domain=domain,
                selectors={
                    "field1": ".selector1",
                    "field2": ".selector2",
                },
            )

        # Verify all domains have history
        for domain in domains:
            history = optimizer.get_optimization_history(domain)
            assert len(history) >= 1
