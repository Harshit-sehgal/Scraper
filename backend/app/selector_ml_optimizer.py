"""
Selector ML Optimizer — Machine learning-based selector quality prediction and optimization.

Provides:
  - Selector feature extraction from CSS selectors and DOM context
  - Quality prediction using lightweight ML models
  - Selector ranking and recommendation
  - Automated selector mutation and generation
  - Performance tracking and model improvement

This system learns what makes selectors effective for each domain:
  - Selector specificity and stability
  - Class / ID naming patterns
  - HTML structure characteristics
  - Historical success / failure rates
  - Domain-specific patterns

LAW: Selectors are not created equal. ML learns which features predict quality.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import re

logger = logging.getLogger(__name__)


@dataclass
class SelectorFeatures:
    """Extracted features from a CSS selector."""

    selector: str
    specificity_score: float  # 0 - 1: how specific
    stability_score: float  # 0 - 1: likely to change
    class_count: int  # Number of classes
    id_count: int  # Number of IDs
    tag_count: int  # Number of tag selectors
    pseudo_class_count: int  # nth-child, etc.
    attribute_count: int  # [attr] selectors
    descendant_depth: int  # How nested
    wildcard_usage: bool  # Uses *
    uses_text_node: bool  # Uses text()
    has_nth_child: bool  # Positional selector
    has_attribute_match: bool  # [attr~=value] style

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SelectorPrediction:
    """ML model prediction for selector quality."""

    selector: str
    predicted_quality: float  # 0 - 1: predicted success rate
    confidence: float  # 0 - 1: confidence in prediction
    feature_importance: Dict[str, float]  # Which features matter most
    recommendation: str  # "keep", "improve", "replace"
    suggested_mutations: List[str]  # Alternative selectors to try


class SelectorFeatureExtractor:
    """Extract features from CSS selectors for ML."""

    @staticmethod
    def extract_features(selector: str, _dom_context: Optional[str] = None) -> SelectorFeatures:
        """Extract ML features from a CSS selector.

        Args:
            selector: CSS selector string
            dom_context: Optional HTML context for better feature extraction

        Returns:
            SelectorFeatures object
        """
        # Basic feature counts
        class_count = selector.count(".")
        id_count = selector.count("#")

        # Robust tag counting using regex
        # Matches alphanumeric tags starting with a letter, either at start or
        # after a combinator / space
        tag_matches = re.findall(r"(?:^|[\s>+~])([a-zA-Z][a-zA-Z0 - 9-]*)", selector)
        tag_count = len(tag_matches)

        pseudo_count = selector.count(":")
        attribute_count = selector.count("[")

        # Calculate specificity (rough approximation)
        # ID: 100, class: 10, tag: 1
        # Normalize to 0 - 1. 100+ is very specific.
        specificity = (id_count * 100 + class_count * 10 + tag_count) / 150.0
        specificity = min(1.0, specificity)

        # Stability factors
        # - IDs are stable, nth-child is unstable
        # - Classes can change, tags are stable
        has_nth = ":nth-child" in selector or ":nth-of-type" in selector
        has_attr_match_val = "~=" in selector or "*=" in selector or "|=" in selector
        uses_wildcard = "*" in selector

        stability = 1.0
        if has_nth:
            stability -= 0.6  # Very unstable
        if uses_wildcard:
            stability -= 0.4
        if class_count > 3:
            stability -= 0.2  # Too many classes suggests fragility
        if descendant_depth_val := (selector.count(" ") + selector.count(">")):
            stability -= descendant_depth_val * 0.1

        stability = max(0.0, min(1.0, stability))

        # Nesting depth
        descendant_depth = selector.count(" ") + selector.count(">") + selector.count("+") + selector.count("~")

        return SelectorFeatures(
            selector=selector,
            specificity_score=specificity,
            stability_score=stability,
            class_count=class_count,
            id_count=id_count,
            tag_count=tag_count,
            pseudo_class_count=pseudo_count,
            attribute_count=attribute_count,
            descendant_depth=min(descendant_depth, 5),  # Cap at 5
            wildcard_usage=uses_wildcard,
            uses_text_node=":text" in selector or "text()" in selector,
            has_nth_child=has_nth,
            has_attribute_match=has_attr_match_val,
        )

    @staticmethod
    def extract_batch(selectors: List[str]) -> List[SelectorFeatures]:
        """Extract features for multiple selectors."""
        return [SelectorFeatureExtractor.extract_features(sel) for sel in selectors]


class SelectorQualityPredictor:
    """Lightweight ML model for selector quality prediction.

    Uses a simple weighted feature model (no external ML libraries required).
    """

    def __init__(self):
        """Initialize predictor with learned weights."""
        # Feature weights learned from successful / failed selectors
        # These are baseline weights; they improve with more training data
        self.feature_weights = {
            "specificity_score": 0.8,  # More specific = better
            "stability_score": 1.0,  # Stable selectors are better
            "class_count": -0.2,  # Too many classes = less stable
            "id_count": 0.5,  # IDs are good
            "tag_count": 0.1,  # Tags are moderately good
            "pseudo_class_count": -0.4,  # Pseudo-classes hurt stability
            "attribute_count": 0.2,  # Attributes are ok
            "descendant_depth": -0.3,  # Deep nesting hurts
            "wildcard_usage": -0.8,  # Wildcards are bad
            "uses_text_node": -0.5,  # Text nodes are fragile
            "has_nth_child": -0.7,  # Position-based selectors are bad
            "has_attribute_match": 0.1,  # Attribute matching is ok
        }

        # Confidence calibration
        self.confidence_boost = 0.6  # Base confidence for predictions

    def predict(self, features: SelectorFeatures) -> SelectorPrediction:
        """Predict quality of a selector.

        Args:
            features: Extracted selector features

        Returns:
            SelectorPrediction with quality score and recommendation
        """
        # Weighted sum of features
        score = 0.4  # Lower base score
        feature_dict: Dict[str, Any] = asdict(features)

        for feature_name, weight in self.feature_weights.items():
            if feature_name == "selector":
                continue

            raw = feature_dict.get(feature_name, 0)

            # Normalize features
            if isinstance(raw, bool):
                value: float = 1.0 if raw else 0.0
            elif feature_name in ["class_count", "pseudo_class_count", "tag_count", "id_count", "attribute_count"]:
                # Normalize counts to [0, 1]
                value = min(1.0, float(raw) / 5.0)
            elif feature_name == "descendant_depth":
                # Normalize depth. Weight is negative, so higher depth reduces
                # score.
                value = float(raw) / 5.0
            else:
                value = float(raw)

            score += weight * value

        # Clamp to [0, 1]
        predicted_quality = max(0.0, min(1.0, score))

        # Confidence depends on feature consistency
        confidence = self.confidence_boost
        if features.specificity_score > 0.6:
            confidence += 0.15
        if features.stability_score > 0.6:
            confidence += 0.15

        # Recommendation
        if predicted_quality >= 0.7:
            recommendation = "keep"
        elif predicted_quality >= 0.4:
            recommendation = "improve"
        else:
            recommendation = "replace"

        # Calculate feature importance
        feature_importance: Dict[str, float] = {}
        for feature_name, weight in self.feature_weights.items():
            if feature_name != "selector":
                raw = feature_dict.get(feature_name, 0)
                if isinstance(raw, bool):
                    val: float = 1.0 if raw else 0.0
                elif feature_name in ["class_count", "pseudo_class_count", "tag_count", "id_count", "attribute_count"]:
                    val = min(1.0, float(raw) / 5.0)
                elif feature_name == "descendant_depth":
                    val = float(raw) / 5.0
                else:
                    val = float(raw)
                feature_importance[feature_name] = abs(weight * val)

        return SelectorPrediction(
            selector=features.selector,
            predicted_quality=predicted_quality,
            confidence=confidence,
            feature_importance=feature_importance,
            recommendation=recommendation,
            suggested_mutations=self._generate_mutations(features),
        )

    def _generate_mutations(self, features: SelectorFeatures) -> List[str]:
        """Generate alternative selectors to try.

        Args:
            features: Features of current selector

        Returns:
            List of suggested alternative selectors
        """
        mutations = []
        selector = features.selector

        # Mutation 1: Remove pseudo-classes if present
        if ":" in selector and "::" not in selector:
            variant = selector.split(":")[0]
            if variant and variant != selector:
                mutations.append(variant)

        # Mutation 2: Simplify by removing deepest nesting
        if " " in selector:
            parts = selector.split(" ")
            if len(parts) > 1:
                # Try parent only
                mutations.append(" ".join(parts[-2:]))
                # Try just last part
                mutations.append(parts[-1])

        # Mutation 3: Replace classes with more specific ones (if ID exists)
        if "#" in selector and "." in selector:
            # Try just the ID
            id_part = [p for p in selector.split(" ") if "#" in p]
            if id_part:
                mutations.append(id_part[0])

        # Mutation 4: Add parent context for uniqueness
        if "#" not in selector and len(mutations) < 3:
            # Suggest adding a parent context
            mutations.append(f"body {selector}")

        return mutations[:3]  # Return top 3 mutations

    def predict_batch(self, features_list: List[SelectorFeatures]) -> List[SelectorPrediction]:
        """Predict quality for multiple selectors."""
        return [self.predict(features) for features in features_list]

    def update_weights(self, feedback: List[tuple], learning_rate: float = 0.01):
        """Update model weights based on feedback.

        Args:
            feedback: List of (features, actual_quality) tuples
            learning_rate: How much to adjust weights
        """
        if not feedback:
            return

        for features, actual_quality in feedback:
            prediction = self.predict(features)
            error = actual_quality - prediction.predicted_quality

            # Adjust weights based on error
            feature_dict: Dict[str, Any] = asdict(features)
            for feature_name in self.feature_weights.keys():
                if feature_name == "selector":
                    continue

                raw = feature_dict.get(feature_name, 0)
                if isinstance(raw, bool):
                    val: float = 1.0 if raw else 0.0
                else:
                    val = float(raw)

                # Simple gradient update
                adjustment = learning_rate * error * val
                # type: ignore[assignment]
                weight: float = self.feature_weights[feature_name]
                self.feature_weights[feature_name] = weight + adjustment

        logger.info("Updated selector quality predictor with %d feedback samples", len(feedback))


class SelectorOptimizationEngine:
    """Orchestrates selector optimization using ML predictions."""

    def __init__(self):
        """Initialize optimizer with quality predictor."""
        self.predictor = SelectorQualityPredictor()
        self.feature_extractor = SelectorFeatureExtractor()
        self.optimization_history: Dict[str, List[Dict[str, Any]]] = {}

    def optimize_selectors(
        self,
        domain: str,
        selectors: Dict[str, str],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Optimize selectors for a domain.

        Args:
            domain: Domain name for tracking
            selectors: Dict of {field_name: selector_css}
            context: Optional HTML context

        Returns:
            Optimization report with recommendations
        """
        report: Dict[str, Any] = {
            "domain": domain,
            "timestamp": time.time(),
            "original_count": len(selectors),
            "optimizations": [],
            "summary": {
                "total_quality": 0.0,
                "keep": 0,
                "improve": 0,
                "replace": 0,
            },
        }

        for field_name, selector in selectors.items():
            # Extract features and predict
            features = self.feature_extractor.extract_features(selector, context)
            prediction = self.predictor.predict(features)

            optimization = {
                "field_name": field_name,
                "selector": selector,
                "predicted_quality": prediction.predicted_quality,
                "recommendation": prediction.recommendation,
                "suggested_mutations": prediction.suggested_mutations,
                "features": features.to_dict(),
            }

            report["optimizations"].append(optimization)
            report["summary"]["total_quality"] += prediction.predicted_quality
            report["summary"][prediction.recommendation] += 1

        if selectors:
            report["summary"]["total_quality"] /= len(selectors)

        # Track optimization
        if domain not in self.optimization_history:
            self.optimization_history[domain] = []
        self.optimization_history[domain].append(report)

        return report

    def get_optimization_history(self, domain: str, limit: int = 10) -> List[dict]:
        """Get recent optimization reports for a domain."""
        hist: list = self.optimization_history.get(domain, [])
        return hist[-limit:]

    def learn_from_results(
        self,
        domain: str,
        selector: str,
        actual_quality: float,
    ):
        """Learn from actual extraction results.

        Args:
            domain: Domain for context
            selector: CSS selector that was used
            actual_quality: Actual quality score achieved [0, 1]
        """
        features = self.feature_extractor.extract_features(selector)

        # Update model weights based on actual results
        self.predictor.update_weights([(features, actual_quality)])

        logger.info("Learned from selector %s (actual=%.2f)", selector, actual_quality)


# Global singleton
_optimizer: SelectorOptimizationEngine | None = None


def get_selector_optimizer() -> SelectorOptimizationEngine:
    """Get the global selector optimization engine."""
    global _optimizer
    if _optimizer is None:
        _optimizer = SelectorOptimizationEngine()
    return _optimizer
