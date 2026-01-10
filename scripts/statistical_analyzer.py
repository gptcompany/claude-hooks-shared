#!/usr/bin/env python3
"""
Statistical Analyzer for Tips Engine v2

Provides:
- Z-score calculation
- Anomaly detection
- Confidence intervals
- Trend analysis
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ZScoreResult:
    """Result of z-score calculation."""

    value: float
    mean: float
    stddev: float
    z_score: float
    is_anomaly: bool  # z > 2
    is_extreme: bool  # z > 3
    percentile: float  # Approximate percentile (0-100)


def calculate_z_score(
    value: float,
    mean: float,
    stddev: float,
    min_stddev: float = 0.01,
) -> ZScoreResult:
    """
    Calculate z-score for a value given mean and standard deviation.

    Args:
        value: The observed value
        mean: Population/sample mean
        stddev: Population/sample standard deviation
        min_stddev: Minimum stddev to avoid division by zero

    Returns:
        ZScoreResult with z-score and anomaly flags
    """
    # Avoid division by zero
    effective_stddev = max(stddev, min_stddev)

    z = (value - mean) / effective_stddev

    # Approximate percentile using normal distribution
    # For z=0 -> 50%, z=1 -> 84%, z=2 -> 97.7%, z=-1 -> 16%
    percentile = _z_to_percentile(z)

    return ZScoreResult(
        value=value,
        mean=mean,
        stddev=stddev,
        z_score=z,
        is_anomaly=abs(z) > 2,  # 95% confidence
        is_extreme=abs(z) > 3,  # 99.7% confidence
        percentile=percentile,
    )


def _z_to_percentile(z: float) -> float:
    """
    Convert z-score to approximate percentile.
    Uses standard normal distribution approximation.
    """
    # Approximation using error function
    # CDF(z) = 0.5 * (1 + erf(z / sqrt(2)))
    return 50 * (1 + math.erf(z / math.sqrt(2)))


def detect_anomalies(
    values: list[float],
    threshold_z: float = 2.0,
) -> list[tuple[int, float, float]]:
    """
    Detect anomalies in a list of values.

    Returns list of (index, value, z_score) for anomalous values.
    """
    if len(values) < 3:
        return []

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stddev = math.sqrt(variance) if variance > 0 else 0.01

    anomalies = []
    for i, v in enumerate(values):
        z = (v - mean) / stddev
        if abs(z) > threshold_z:
            anomalies.append((i, v, z))

    return anomalies


def calculate_trend(values: list[float]) -> dict:
    """
    Calculate trend statistics for a time series.

    Returns:
        dict with slope, direction, strength, and confidence
    """
    if len(values) < 3:
        return {
            "slope": 0.0,
            "direction": "stable",
            "strength": 0.0,
            "confidence": 0.0,
        }

    n = len(values)
    x_values = list(range(n))

    # Calculate means
    x_mean = sum(x_values) / n
    y_mean = sum(values) / n

    # Calculate slope (linear regression)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)

    slope = numerator / denominator if denominator != 0 else 0

    # Calculate R-squared for confidence
    y_pred = [slope * x + (y_mean - slope * x_mean) for x in x_values]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(values, y_pred))
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    # Determine direction and strength
    if abs(slope) < 0.01:
        direction = "stable"
    elif slope > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    # Strength based on slope magnitude relative to mean
    strength = abs(slope) / abs(y_mean) if y_mean != 0 else abs(slope)
    strength = min(1.0, strength)  # Cap at 1.0

    return {
        "slope": slope,
        "direction": direction,
        "strength": strength,
        "confidence": max(0, r_squared),
    }


def z_score_to_confidence(z: float, base_confidence: float = 0.5) -> float:
    """
    Convert z-score to confidence percentage.

    Higher z-scores (in absolute terms) indicate more anomalous behavior,
    which increases confidence that something is wrong.

    Args:
        z: Z-score value
        base_confidence: Starting confidence (default 50%)

    Returns:
        Confidence value between 0.1 and 0.95
    """
    # z=0 -> base_confidence
    # z=2 -> ~80%
    # z=3 -> ~95%
    confidence = base_confidence + (abs(z) * 0.15)
    return min(0.95, max(0.10, confidence))


def compare_to_benchmark(
    value: float,
    elite_threshold: float,
    good_threshold: Optional[float] = None,
    higher_is_better: bool = False,
) -> dict:
    """
    Compare a value against DORA-style thresholds.

    Args:
        value: The observed value
        elite_threshold: Threshold for "elite" performance
        good_threshold: Optional threshold for "good" (defaults to 2x elite)
        higher_is_better: Whether higher values are better (e.g., test pass rate)

    Returns:
        dict with category and distance from elite
    """
    if good_threshold is None:
        good_threshold = elite_threshold * 2 if not higher_is_better else elite_threshold * 0.5

    if higher_is_better:
        if value >= elite_threshold:
            category = "elite"
        elif value >= good_threshold:
            category = "good"
        else:
            category = "needs_improvement"
        distance = elite_threshold - value
    else:
        if value <= elite_threshold:
            category = "elite"
        elif value <= good_threshold:
            category = "good"
        else:
            category = "needs_improvement"
        distance = value - elite_threshold

    return {
        "category": category,
        "elite_threshold": elite_threshold,
        "good_threshold": good_threshold,
        "distance_from_elite": distance,
        "is_elite": category == "elite",
    }


# DORA benchmark thresholds
DORA_THRESHOLDS = {
    "error_rate": {
        "elite": 0.15,  # Change Failure Rate
        "good": 0.30,
        "higher_is_better": False,
    },
    "rework_rate": {
        "elite": 0.15,
        "good": 0.30,
        "higher_is_better": False,
    },
    "test_pass_rate": {
        "elite": 0.95,
        "good": 0.80,
        "higher_is_better": True,
    },
    "agent_success_rate": {
        "elite": 0.90,
        "good": 0.70,
        "higher_is_better": True,
    },
}


def compare_session_to_dora(
    error_rate: float,
    rework_rate: float,
    test_pass_rate: float,
    agent_success_rate: float,
) -> dict:
    """
    Compare session metrics against DORA benchmarks.

    Returns comprehensive comparison with all metrics.
    """
    return {
        "error_rate": compare_to_benchmark(
            error_rate,
            DORA_THRESHOLDS["error_rate"]["elite"],
            DORA_THRESHOLDS["error_rate"]["good"],
            DORA_THRESHOLDS["error_rate"]["higher_is_better"],
        ),
        "rework_rate": compare_to_benchmark(
            rework_rate,
            DORA_THRESHOLDS["rework_rate"]["elite"],
            DORA_THRESHOLDS["rework_rate"]["good"],
            DORA_THRESHOLDS["rework_rate"]["higher_is_better"],
        ),
        "test_pass_rate": compare_to_benchmark(
            test_pass_rate,
            DORA_THRESHOLDS["test_pass_rate"]["elite"],
            DORA_THRESHOLDS["test_pass_rate"]["good"],
            DORA_THRESHOLDS["test_pass_rate"]["higher_is_better"],
        ),
        "agent_success_rate": compare_to_benchmark(
            agent_success_rate,
            DORA_THRESHOLDS["agent_success_rate"]["elite"],
            DORA_THRESHOLDS["agent_success_rate"]["good"],
            DORA_THRESHOLDS["agent_success_rate"]["higher_is_better"],
        ),
    }


if __name__ == "__main__":
    # Test z-score calculation
    result = calculate_z_score(0.37, 0.10, 0.05)
    print(f"Z-score for error_rate=37%: {result.z_score:.2f}")
    print(f"  Is anomaly: {result.is_anomaly}")
    print(f"  Percentile: {result.percentile:.1f}%")

    # Test DORA comparison
    dora = compare_session_to_dora(
        error_rate=0.37,
        rework_rate=0.32,
        test_pass_rate=0.40,
        agent_success_rate=0.60,
    )
    print("\nDORA Comparison:")
    for metric, comparison in dora.items():
        print(f"  {metric}: {comparison['category']} (distance: {comparison['distance_from_elite']:.2f})")
