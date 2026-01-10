#!/usr/bin/env python3
"""
Dynamic Tips Engine v2 - Evidence-Based Design

Generates optimization tips based on:
- DORA metrics and thresholds
- Statistical anomaly detection (z-score)
- Historical success rates
- Similar situation lookup
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
import math


@dataclass
class SessionMetrics:
    """Current session metrics collected by hooks."""

    # Raw counts
    tool_calls: int = 0
    errors: int = 0
    file_edits: int = 0
    reworks: int = 0
    test_runs: int = 0
    tests_passed: int = 0
    agent_spawns: int = 0
    agent_successes: int = 0
    duration_seconds: int = 0

    # Iteration tracking
    max_task_iterations: int = 0
    stuck_tasks: int = 0
    most_used_tool_in_stuck_task: str = ""

    # Change size metrics
    lines_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    files_modified: int = 0

    # Per-file churn
    max_file_edits: int = 0
    max_file_reworks: int = 0
    most_churned_file: str = ""

    # Context
    project: str = ""
    recently_failed_commands: list = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        return self.errors / self.tool_calls if self.tool_calls > 0 else 0.0

    @property
    def rework_rate(self) -> float:
        """Calculate rework rate."""
        return self.reworks / self.file_edits if self.file_edits > 0 else 0.0

    @property
    def test_pass_rate(self) -> float:
        """Calculate test pass rate."""
        return self.tests_passed / self.test_runs if self.test_runs > 0 else 0.0

    @property
    def agent_success_rate(self) -> float:
        """Calculate agent success rate."""
        return self.agent_successes / self.agent_spawns if self.agent_spawns > 0 else 0.0


@dataclass
class HistoricalStats:
    """Historical statistics from QuestDB or defaults."""

    # Session counts
    session_count: int = 0
    data_source: str = "defaults"  # "project", "cross_project", "defaults"

    # Error rate stats
    avg_error_rate: float = 0.10
    stddev_error_rate: float = 0.05

    # Rework rate stats
    avg_rework_rate: float = 0.15
    stddev_rework_rate: float = 0.08

    # Test pass rate stats
    avg_test_pass_rate: float = 0.85
    stddev_test_pass_rate: float = 0.10

    # Command success rates (command -> rate)
    command_success_rates: dict = field(default_factory=dict)

    # Rule accuracy tracking
    rule_accuracies: dict = field(default_factory=dict)

    # Confidence penalty for less reliable data
    confidence_penalty: float = 0.0

    def get_command_success_rate(self, command: str) -> Optional[float]:
        """Get historical success rate for a command."""
        return self.command_success_rates.get(command)

    def get_rule_accuracy(self, rule_name: str) -> float:
        """Get historical accuracy for a rule."""
        return self.rule_accuracies.get(rule_name, 0.7)  # Default 70%

    def get_context_similarity(self, current: SessionMetrics) -> float:
        """
        Calculate how similar current context is to historical data.
        Returns 0.0-1.0 (1.0 = very similar).
        """
        if self.session_count == 0:
            return 0.5  # No data, moderate similarity assumed

        # Compare error rate distance
        error_distance = abs(current.error_rate - self.avg_error_rate)
        error_sim = max(0, 1 - error_distance / 0.5)  # 0.5 = max expected distance

        # Compare rework rate distance
        rework_distance = abs(current.rework_rate - self.avg_rework_rate)
        rework_sim = max(0, 1 - rework_distance / 0.5)

        return (error_sim + rework_sim) / 2

    def with_lower_confidence(self, factor: float) -> "HistoricalStats":
        """Return copy with confidence penalty applied."""
        import copy

        new_stats = copy.deepcopy(self)
        new_stats.confidence_penalty = 1 - factor
        return new_stats


class IndustryDefaults:
    """
    Evidence-based defaults from DORA/SPACE research.
    Used when no historical data available.
    """

    # Error rates (from DORA Change Failure Rate)
    avg_error_rate = 0.10
    stddev_error_rate = 0.05
    elite_threshold = 0.15  # DORA elite performers

    # Rework rates (from code churn research)
    avg_rework_rate = 0.15
    stddev_rework_rate = 0.08
    danger_threshold = 0.30

    # Test pass rates
    avg_test_pass_rate = 0.85
    stddev_test_pass_rate = 0.10

    # Command success rates (conservative estimates)
    default_command_success = {
        "/tdd:cycle": 0.70,
        "/tdd:red": 0.75,
        "/undo:checkpoint": 0.90,
        "/speckit.plan": 0.65,
        "/speckit.specify": 0.70,
        "/speckit.clarify": 0.80,
        "/speckit.tasks": 0.70,
    }

    @classmethod
    def to_historical_stats(cls) -> HistoricalStats:
        """Convert to HistoricalStats with default values."""
        return HistoricalStats(
            session_count=0,
            data_source="defaults",
            avg_error_rate=cls.avg_error_rate,
            stddev_error_rate=cls.stddev_error_rate,
            avg_rework_rate=cls.avg_rework_rate,
            stddev_rework_rate=cls.stddev_rework_rate,
            avg_test_pass_rate=cls.avg_test_pass_rate,
            stddev_test_pass_rate=cls.stddev_test_pass_rate,
            command_success_rates=cls.default_command_success.copy(),
            confidence_penalty=0.5,  # 50% penalty for using defaults
        )


@dataclass
class Tip:
    """A single optimization tip."""

    rule_name: str
    message: str
    command: str
    confidence: float
    evidence: str
    category: str
    rationale: str = ""
    similar_outcomes: str = ""


# Command Registry with categories
COMMAND_REGISTRY = {
    "safety": {
        "commands": [
            {
                "name": "/undo:checkpoint",
                "risk": "low",
                "cost": "low",
                "success_baseline": 0.90,
                "when": "errors, long sessions, before risky ops",
            },
            {
                "name": "/undo:rollback",
                "risk": "medium",
                "cost": "low",
                "success_baseline": 0.85,
                "when": "need to recover from bad state",
            },
        ],
        "selection_priority": ["success_rate", "risk", "cost"],
    },
    "quality": {
        "commands": [
            {
                "name": "/tdd:cycle",
                "risk": "low",
                "cost": "medium",
                "success_baseline": 0.70,
                "when": "rework high, no tests, quality issues",
            },
            {
                "name": "/tdd:red",
                "risk": "low",
                "cost": "low",
                "success_baseline": 0.80,
                "when": "need to write tests first",
            },
            {
                "name": "/tdd:spec-to-test",
                "risk": "low",
                "cost": "low",
                "success_baseline": 0.75,
                "when": "have spec, need tests",
            },
        ],
        "selection_priority": ["success_rate", "cost", "risk"],
    },
    "planning": {
        "commands": [
            {
                "name": "/speckit.specify",
                "risk": "low",
                "cost": "medium",
                "success_baseline": 0.70,
                "when": "new feature, unclear requirements",
            },
            {
                "name": "/speckit.plan",
                "risk": "low",
                "cost": "medium",
                "success_baseline": 0.65,
                "when": "have spec, need implementation plan",
            },
            {
                "name": "/speckit.clarify",
                "risk": "low",
                "cost": "low",
                "success_baseline": 0.80,
                "when": "stuck, need to identify gaps",
            },
            {
                "name": "/speckit.tasks",
                "risk": "low",
                "cost": "low",
                "success_baseline": 0.70,
                "when": "break into smaller tasks",
            },
        ],
        "selection_priority": ["success_rate", "cost"],
    },
    "diagnosis": {
        "commands": [
            {
                "name": "/health",
                "risk": "none",
                "cost": "low",
                "success_baseline": 0.95,
                "when": "quick system check",
            },
            {
                "name": "/audit",
                "risk": "none",
                "cost": "medium",
                "success_baseline": 0.90,
                "when": "deep analysis needed",
            },
        ],
        "selection_priority": ["cost", "success_rate"],
    },
}

RISK_SCORES = {"none": 1.0, "low": 0.9, "medium": 0.6, "high": 0.3}
COST_SCORES = {"low": 1.0, "medium": 0.7, "medium-high": 0.5, "high": 0.3}


def select_best_command(
    category: str,
    current: SessionMetrics,
    historical: HistoricalStats,
    fallback: str = "",
) -> tuple[str, float, str]:
    """
    Select best command based on category priority rules.

    Returns: (command, score, rationale)
    """
    registry = COMMAND_REGISTRY.get(category)
    if not registry:
        return fallback, 0.5, "Category not found, using fallback"

    priority_order = registry["selection_priority"]
    candidates = []

    for cmd_info in registry["commands"]:
        cmd_name = cmd_info["name"]

        # Get actual success rate (or baseline if cold start)
        success_rate = historical.get_command_success_rate(cmd_name)
        is_baseline = success_rate is None
        if is_baseline:
            success_rate = cmd_info["success_baseline"]

        # Calculate composite score based on priority
        score = 0.0
        for i, factor in enumerate(priority_order):
            weight = 1.0 - (i * 0.2)  # First factor: 1.0, second: 0.8, third: 0.6

            if factor == "success_rate":
                score += weight * success_rate
            elif factor == "risk":
                score += weight * RISK_SCORES.get(cmd_info["risk"], 0.5)
            elif factor == "cost":
                score += weight * COST_SCORES.get(cmd_info["cost"], 0.5)

        # Penalty if recently failed
        if cmd_name in current.recently_failed_commands:
            score *= 0.5  # 50% penalty

        candidates.append(
            {
                "command": cmd_name,
                "score": score,
                "success_rate": success_rate,
                "is_baseline": is_baseline,
                "when": cmd_info["when"],
            }
        )

    # Sort by score descending
    candidates.sort(key=lambda x: -x["score"])
    best = candidates[0]

    # Build rationale
    if best["is_baseline"]:
        rationale = f"Baseline success rate: {best['success_rate']:.0%}"
    else:
        rationale = f"Historical success: {best['success_rate']:.0%} for {current.project}"

    return best["command"], best["score"], rationale


def calculate_confidence(
    rule_name: str,
    current: SessionMetrics,
    historical: HistoricalStats,
    z_score: Optional[float] = None,
) -> float:
    """
    Calculate confidence based on:
    1. Statistical significance (z-score)
    2. Sample size
    3. Historical rule accuracy
    4. Context match quality
    """
    # 1. Z-score: How anomalous is current value?
    if z_score is None:
        if rule_name == "high_error_rate" and historical.stddev_error_rate > 0:
            z_score = (current.error_rate - historical.avg_error_rate) / historical.stddev_error_rate
        elif rule_name == "high_rework" and historical.stddev_rework_rate > 0:
            z_score = (current.rework_rate - historical.avg_rework_rate) / historical.stddev_rework_rate
        else:
            z_score = 2.0  # Default for non-statistical rules

    # z-score to probability (z=2 -> 95%, z=3 -> 99.7%)
    statistical_confidence = min(0.99, 0.5 + (abs(z_score) * 0.15))

    # 2. Sample size factor (more data = more confident)
    sample_size = historical.session_count
    sample_factor = min(1.0, sample_size / 20)  # Full confidence at 20+ sessions

    # 3. Historical rule accuracy
    rule_accuracy = historical.get_rule_accuracy(rule_name)

    # 4. Context match quality
    context_match = historical.get_context_similarity(current)

    # Weighted combination
    confidence = (
        statistical_confidence * 0.35
        + sample_factor * 0.15
        + rule_accuracy * 0.30
        + context_match * 0.20
    )

    # Apply confidence penalty from data source
    confidence *= 1 - historical.confidence_penalty

    return min(0.95, max(0.10, confidence))  # Clamp to 10-95%


@dataclass
class PatternRule:
    """A pattern rule that can trigger a tip."""

    name: str
    category: str
    evidence: str
    condition: Callable[[SessionMetrics, HistoricalStats], bool]
    message_builder: Callable[[SessionMetrics, HistoricalStats], str]
    fallback_command: str = ""

    def matches(self, current: SessionMetrics, historical: HistoricalStats) -> bool:
        """Check if this rule matches current session."""
        try:
            return self.condition(current, historical)
        except Exception:
            return False

    def build_message(self, current: SessionMetrics, historical: HistoricalStats) -> str:
        """Build the tip message."""
        try:
            return self.message_builder(current, historical)
        except Exception:
            return self.name


# Pattern Rules (Evidence-Based)
PATTERN_RULES = [
    PatternRule(
        name="high_error_rate",
        category="safety",
        evidence="DORA Change Failure Rate threshold + statistical anomaly",
        condition=lambda curr, hist: (
            curr.error_rate > 0.15  # DORA threshold
            and curr.tool_calls >= 10  # Meaningful sample
            and (
                hist.stddev_error_rate == 0
                or curr.error_rate > hist.avg_error_rate + 2 * hist.stddev_error_rate
            )
        ),
        message_builder=lambda curr, hist: (
            f"Error rate {curr.error_rate:.0%} "
            f"(z={((curr.error_rate - hist.avg_error_rate) / hist.stddev_error_rate):.1f}, "
            f"elite <15%)"
            if hist.stddev_error_rate > 0
            else f"Error rate {curr.error_rate:.0%} (elite <15%)"
        ),
        fallback_command="/undo:checkpoint",
    ),
    PatternRule(
        name="stuck_in_loop",
        category="planning",
        evidence="Pattern analysis: >5 iterations = same approach failing",
        condition=lambda curr, hist: curr.max_task_iterations > 5,
        message_builder=lambda curr, hist: f"Stuck in loop: {curr.max_task_iterations} iterations on same task",
        fallback_command="/speckit.plan",
    ),
    PatternRule(
        name="high_rework",
        category="quality",
        evidence="Microsoft Research: Code churn predicts defects with 89% accuracy",
        condition=lambda curr, hist: (
            curr.rework_rate > 0.30 and curr.file_edits >= 5  # 30% of edits are reworks
        ),
        message_builder=lambda curr, hist: f"High rework rate: {curr.rework_rate:.0%} of edits are reworks",
        fallback_command="/tdd:cycle",
    ),
    PatternRule(
        name="no_tests",
        category="quality",
        evidence="Test coverage correlates with 75-77% precision in defect prediction",
        condition=lambda curr, hist: curr.file_edits > 5 and curr.test_runs == 0,
        message_builder=lambda curr, hist: f"{curr.file_edits} file edits without running tests",
        fallback_command="/tdd:red",
    ),
    PatternRule(
        name="large_change_size",
        category="quality",
        evidence="Cisco study: 40% fewer defects when changes <200 lines",
        condition=lambda curr, hist: curr.lines_changed > 400,
        message_builder=lambda curr, hist: f"Large change: {curr.lines_changed} lines modified",
        fallback_command="/speckit.clarify",
    ),
    PatternRule(
        name="too_many_files",
        category="planning",
        evidence="PR size studies: fewer files = easier review, fewer bugs",
        condition=lambda curr, hist: curr.files_modified > 10,
        message_builder=lambda curr, hist: f"Many files touched: {curr.files_modified} files modified",
        fallback_command="/speckit.tasks",
    ),
    PatternRule(
        name="high_churn_single_file",
        category="safety",
        evidence="Microsoft Research: file churn predicts defects",
        condition=lambda curr, hist: (
            curr.max_file_edits > 5 and curr.max_file_reworks > 2  # Same file edited 5+ times with reworks
        ),
        message_builder=lambda curr, hist: f"File {curr.most_churned_file} edited {curr.max_file_edits}x",
        fallback_command="/undo:checkpoint",
    ),
    PatternRule(
        name="low_agent_success",
        category="diagnosis",
        evidence="Low agent success rate indicates prompts may need refinement",
        condition=lambda curr, hist: (
            curr.agent_spawns >= 3 and curr.agent_success_rate < 0.70
        ),
        message_builder=lambda curr, hist: f"Low agent success: {curr.agent_success_rate:.0%} ({curr.agent_successes}/{curr.agent_spawns})",
        fallback_command="/audit",
    ),
    PatternRule(
        name="low_test_pass_rate",
        category="quality",
        evidence="Focus on one test at a time for better debugging",
        condition=lambda curr, hist: (
            curr.test_runs >= 3 and curr.test_pass_rate < 0.60
        ),
        message_builder=lambda curr, hist: f"Low test pass rate: {curr.test_pass_rate:.0%}",
        fallback_command="/tdd:red",
    ),
]


def generate_all_tips(
    current: SessionMetrics,
    historical: HistoricalStats,
) -> list[Tip]:
    """
    Generate tips from all matching pattern rules.

    Each rule is evaluated independently.
    Tips are sorted by confidence and limited to max 5.
    """
    tips = []

    for rule in PATTERN_RULES:
        if rule.matches(current, historical):
            # Select best command for this rule's category
            command, score, rationale = select_best_command(
                category=rule.category,
                current=current,
                historical=historical,
                fallback=rule.fallback_command,
            )

            # Calculate confidence
            confidence = calculate_confidence(
                rule_name=rule.name,
                current=current,
                historical=historical,
            )

            tips.append(
                Tip(
                    rule_name=rule.name,
                    message=rule.build_message(current, historical),
                    command=command,
                    confidence=confidence,
                    evidence=rule.evidence,
                    category=rule.category,
                    rationale=rationale,
                )
            )

    # Sort by confidence descending
    tips.sort(key=lambda t: -t.confidence)

    # Deduplicate (same command -> merge)
    tips = deduplicate_tips(tips)

    # Limit to max 5 tips
    return tips[:5]


def deduplicate_tips(tips: list[Tip]) -> list[Tip]:
    """
    If multiple tips suggest the same command,
    keep the one with highest confidence and merge evidence.
    """
    seen_commands = {}
    deduplicated = []

    for tip in tips:  # Already sorted by confidence desc
        if tip.command not in seen_commands:
            seen_commands[tip.command] = tip
            deduplicated.append(tip)
        else:
            # Merge evidence into existing tip
            existing = seen_commands[tip.command]
            if tip.evidence not in existing.evidence:
                existing.evidence += f"; Also: {tip.evidence}"

    return deduplicated


def format_tips_for_display(tips: list[Tip], cold_start: bool = False) -> str:
    """Format tips for terminal display at session stop."""
    if not tips:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 66)
    if cold_start:
        lines.append("  DYNAMIC OPTIMIZATION TIPS (Cold Start Mode)")
    else:
        lines.append(f"  DYNAMIC OPTIMIZATION TIPS ({len(tips)} triggered)")
    lines.append("=" * 66)
    lines.append("")

    for i, tip in enumerate(tips, 1):
        conf_pct = int(tip.confidence * 100)
        lines.append(f"  {i}. [Conf: {conf_pct}%] {tip.message}")
        lines.append(f"     -> {tip.command}")
        lines.append(f"     Evidence: {tip.evidence}")
        if tip.rationale:
            lines.append(f"     ({tip.rationale})")
        lines.append("")

    lines.append("-" * 66)
    lines.append(f"  {len(tips)} rules triggered")
    if cold_start:
        lines.append("  Note: Building your project baseline. After 5+ sessions,")
        lines.append("  tips will be personalized to YOUR patterns.")
    lines.append("")
    lines.append("  -> Next session: /tips to inject these recommendations")
    lines.append("=" * 66)
    lines.append("")

    return "\n".join(lines)


def tips_to_dict(tips: list[Tip], session_id: str, project: str, historical: HistoricalStats) -> dict:
    """Convert tips to JSON-serializable dict for storage."""
    return {
        "session_id": session_id,
        "project": project,
        "analysis": {
            "sessions_analyzed": historical.session_count,
            "data_source": historical.data_source,
            "statistical_method": "z-score anomaly detection",
        },
        "tips": [
            {
                "confidence": tip.confidence,
                "message": tip.message,
                "command": tip.command,
                "evidence": tip.evidence,
                "category": tip.category,
                "rationale": tip.rationale,
                "rule_name": tip.rule_name,
            }
            for tip in tips
        ],
    }


if __name__ == "__main__":
    # Quick test with sample data
    current = SessionMetrics(
        tool_calls=1050,
        errors=390,
        file_edits=25,
        reworks=8,
        test_runs=5,
        tests_passed=2,
        agent_spawns=10,
        agent_successes=6,
        max_task_iterations=19,
        lines_changed=523,
        files_modified=15,
        max_file_edits=19,
        max_file_reworks=5,
        most_churned_file="settings.json",
        project="claude-hooks-shared",
    )

    historical = IndustryDefaults.to_historical_stats()

    tips = generate_all_tips(current, historical)
    print(format_tips_for_display(tips, cold_start=True))
