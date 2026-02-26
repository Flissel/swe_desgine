"""
Shared metric utilities for the Requirements Engineering system.

Provides:
- Severity comparison helpers
- Weighted score calculation
- Quality threshold checking
"""

from typing import Dict, List, Optional

# Severity levels ordered from lowest to highest
SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def max_severity(*levels: str) -> str:
    """
    Return the highest severity level from the given levels.

    Args:
        *levels: Severity level strings (low, medium, high, critical)

    Returns:
        The highest severity level, or "low" if no valid levels given.

    Example:
        >>> max_severity("low", "high", "medium")
        'high'
        >>> max_severity("medium", "critical")
        'critical'
    """
    max_idx = 0
    for level in levels:
        level_lower = level.lower().strip() if isinstance(level, str) else "low"
        try:
            idx = SEVERITY_ORDER.index(level_lower)
            max_idx = max(max_idx, idx)
        except ValueError:
            pass  # Ignore unknown severity levels
    return SEVERITY_ORDER[max_idx]


def weighted_score(
    scores: Dict[str, float],
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate a weighted average score.

    If weights are not provided, returns simple average.
    Weights are normalized to sum to 1.0.

    Args:
        scores: Dict mapping metric name -> score (0.0 - 1.0)
        weights: Optional dict mapping metric name -> weight

    Returns:
        Weighted average score (0.0 - 1.0)
    """
    if not scores:
        return 0.0

    if weights is None:
        # Simple average
        return sum(scores.values()) / len(scores)

    # Weighted average - only use metrics that have both a score and weight
    total_weight = 0.0
    total_score = 0.0

    for metric, score in scores.items():
        w = weights.get(metric, 0.0)
        total_weight += w
        total_score += score * w

    if total_weight == 0.0:
        # Fallback to simple average if no weights match
        return sum(scores.values()) / len(scores)

    return total_score / total_weight


def check_thresholds(
    scores: Dict[str, float],
    thresholds: Dict[str, float],
    prefix: str = "min_"
) -> List[str]:
    """
    Check scores against thresholds and return list of violations.

    Args:
        scores: Dict mapping metric name -> score
        thresholds: Dict mapping threshold name -> minimum value
                    (e.g., {"min_completeness": 0.8})
        prefix: Prefix to strip from threshold keys to match score keys

    Returns:
        List of violation messages (empty if all pass)

    Example:
        >>> check_thresholds(
        ...     {"completeness": 0.6, "clarity": 0.9},
        ...     {"min_completeness": 0.8, "min_clarity": 0.8}
        ... )
        ['completeness below threshold (0.60 < 0.80)']
    """
    violations = []

    for threshold_key, min_value in thresholds.items():
        # Strip prefix to get metric name
        metric = threshold_key[len(prefix):] if threshold_key.startswith(prefix) else threshold_key
        score = scores.get(metric)

        if score is not None and score < min_value:
            violations.append(
                f"{metric} below threshold ({score:.2f} < {min_value:.2f})"
            )

    return violations
