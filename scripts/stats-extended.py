#!/usr/bin/env python3
"""
Extended Stats Report for Claude Code

Analyzes metrics from:
- ~/.claude/metrics/daily.jsonl (DORA metrics)
- ~/.claude/metrics/tdd_compliance.jsonl (TDD compliance)
- ~/.claude/metrics/prompt_optimization.jsonl (Prompt optimization)
- ~/.claude/metrics/file_edits.json (Rework tracking)
- .claude/stats/session_metrics.jsonl (Token usage & costs)

Usage:
    python stats-extended.py [--days N] [--json] [--project DIR]
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
CLAUDE_DIR = Path.home() / ".claude"


def find_session_metrics_files() -> list[Path]:
    """Find all session_metrics.jsonl files in project directories."""
    files = []
    projects_dir = CLAUDE_DIR / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                stats_file = project_dir / "stats" / "session_metrics.jsonl"
                if stats_file.exists():
                    files.append(stats_file)
    # Also check current directory
    cwd_stats = Path.cwd() / ".claude" / "stats" / "session_metrics.jsonl"
    if cwd_stats.exists() and cwd_stats not in files:
        files.append(cwd_stats)
    return files


def analyze_token_costs(days: int = 7, project_filter: str | None = None) -> dict:
    """Analyze token usage and costs from session_metrics.jsonl files."""
    cutoff = datetime.now() - timedelta(days=days)

    # Aggregate by model
    by_model = {}
    total_cost = 0.0
    total_tokens = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0, "total": 0}
    total_duration = 0.0
    session_count = 0
    sessions_seen = set()

    for stats_file in find_session_metrics_files():
        # Filter by project if specified
        if project_filter:
            project_name = stats_file.parent.parent.name.replace("-", "/")
            if project_filter.lower() not in project_name.lower():
                continue

        with open(stats_file) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    ts = entry.get("timestamp", "")
                    if not ts:
                        continue

                    entry_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if entry_date.replace(tzinfo=None) < cutoff:
                        continue

                    model = entry.get("model", "unknown")
                    tokens = entry.get("tokens", {})
                    cost = entry.get("cost_usd", 0)
                    duration = entry.get("duration_minutes", 0)
                    session_id = entry.get("session_id", "")

                    # Track unique sessions
                    if session_id and session_id not in sessions_seen:
                        sessions_seen.add(session_id)
                        session_count += 1

                    # Initialize model entry
                    if model not in by_model:
                        by_model[model] = {
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "cache_creation": 0,
                            "cache_read": 0,
                            "total_tokens": 0,
                            "cost_usd": 0.0,
                            "duration_minutes": 0.0,
                            "requests": 0,
                        }

                    # Aggregate
                    by_model[model]["tokens_in"] += tokens.get("input", 0)
                    by_model[model]["tokens_out"] += tokens.get("output", 0)
                    by_model[model]["cache_creation"] += tokens.get("cache_creation", 0)
                    by_model[model]["cache_read"] += tokens.get("cache_read", 0)
                    by_model[model]["total_tokens"] += tokens.get("total", 0)
                    by_model[model]["cost_usd"] = max(by_model[model]["cost_usd"], cost)  # Use max (cumulative in file)
                    by_model[model]["duration_minutes"] = max(by_model[model]["duration_minutes"], duration)
                    by_model[model]["requests"] += 1

                    # Total aggregates
                    total_tokens["input"] += tokens.get("input", 0)
                    total_tokens["output"] += tokens.get("output", 0)
                    total_tokens["cache_creation"] += tokens.get("cache_creation", 0)
                    total_tokens["cache_read"] += tokens.get("cache_read", 0)
                    total_tokens["total"] += tokens.get("total", 0)
                    total_cost = max(total_cost, cost)
                    total_duration = max(total_duration, duration)

                except (json.JSONDecodeError, ValueError):
                    continue

    return {
        "by_model": by_model,
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "total_duration_minutes": total_duration,
        "session_count": session_count,
    }


def load_jsonl(file_path: Path, days: int = 7) -> list[dict]:
    """Load JSONL file, filtering by date."""
    if not file_path.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    entries = []

    with open(file_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = entry.get("timestamp", "")
                if ts:
                    entry_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if entry_date.replace(tzinfo=None) > cutoff:
                        entries.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue

    return entries


def analyze_dora_metrics(entries: list[dict]) -> dict:
    """Analyze DORA-style metrics."""
    file_edits = [e for e in entries if e.get("type") == "file_edit"]
    test_runs = [e for e in entries if e.get("type") == "test_run"]
    agent_spawns = [e for e in entries if e.get("type") == "agent_spawn"]
    todo_updates = [e for e in entries if e.get("type") == "todo_update"]
    cycle_times = [e for e in entries if e.get("type") == "cycle_time"]
    session_stats = [e for e in entries if e.get("type") == "session_stats"]

    # Rework rate
    rework_count = sum(1 for e in file_edits if e.get("is_rework"))
    rework_rate = rework_count / len(file_edits) if file_edits else 0

    # Test pass rate
    passed = sum(1 for e in test_runs if e.get("passed"))
    test_pass_rate = passed / len(test_runs) if test_runs else 0

    # Task completion (from todos)
    if todo_updates:
        latest = todo_updates[-1]
        completion_rate = latest.get("completion_rate", 0)
    else:
        completion_rate = 0

    # Agent usage and success rate
    agent_counts = Counter(e.get("agent_type") for e in agent_spawns)
    agent_success = sum(1 for e in agent_spawns if e.get("success", True))
    agent_success_rate = agent_success / len(agent_spawns) if agent_spawns else 1.0

    # Per-agent success rates
    agent_success_by_type = {}
    for agent_type in agent_counts:
        agent_runs = [e for e in agent_spawns if e.get("agent_type") == agent_type]
        successes = sum(1 for e in agent_runs if e.get("success", True))
        agent_success_by_type[agent_type] = successes / len(agent_runs) if agent_runs else 1.0

    # Cycle time analysis
    cycle_minutes = [e.get("cycle_time_minutes", 0) for e in cycle_times]
    avg_cycle_time = sum(cycle_minutes) / len(cycle_minutes) if cycle_minutes else 0

    # Iterations analysis
    iterations = [e.get("iterations", 0) for e in cycle_times if "iterations" in e]
    avg_iterations = sum(iterations) / len(iterations) if iterations else 0

    # Session stats
    total_tool_calls = sum(e.get("tool_calls", 0) for e in session_stats)
    total_errors = sum(e.get("errors", 0) for e in session_stats)
    error_rate = total_errors / total_tool_calls if total_tool_calls else 0

    return {
        "file_edits": len(file_edits),
        "rework_count": rework_count,
        "rework_rate": rework_rate,
        "test_runs": len(test_runs),
        "test_pass_rate": test_pass_rate,
        "task_completion_rate": completion_rate,
        "agent_spawns": len(agent_spawns),
        "agent_success_rate": agent_success_rate,
        "top_agents": dict(agent_counts.most_common(5)),
        "agent_success_by_type": agent_success_by_type,
        "cycle_time_avg_minutes": avg_cycle_time,
        "tasks_with_cycle_time": len(cycle_times),
        "avg_iterations": avg_iterations,
        "total_tool_calls": total_tool_calls,
        "total_errors": total_errors,
        "error_rate": error_rate,
    }


def analyze_tdd_compliance(entries: list[dict]) -> dict:
    """Analyze TDD compliance metrics."""
    compliant = sum(1 for e in entries if e.get("type") == "compliant")
    violations = sum(1 for e in entries if e.get("type") == "violation")
    skipped = sum(1 for e in entries if e.get("type") == "skip")

    total_checks = compliant + violations
    compliance_rate = compliant / total_checks if total_checks else 1.0

    # Files with violations
    violation_files = [e.get("file") for e in entries if e.get("type") == "violation"]

    return {
        "total_checks": total_checks,
        "compliant": compliant,
        "violations": violations,
        "skipped": skipped,
        "compliance_rate": compliance_rate,
        "violation_files": list(set(violation_files))[:10],
    }


def analyze_prompt_optimization(entries: list[dict]) -> dict:
    """Analyze prompt optimization metrics."""
    optimized = [e for e in entries if e.get("type") == "optimized"]
    passthrough = [e for e in entries if e.get("type") == "passthrough"]
    acceptances = [e for e in entries if e.get("type") == "acceptance"]

    optimization_rate = len(optimized) / (len(optimized) + len(passthrough)) if entries else 0

    # Acceptance rate
    accepted_count = sum(1 for e in acceptances if e.get("accepted"))
    acceptance_rate = accepted_count / len(acceptances) if acceptances else 0
    avg_similarity = sum(e.get("similarity", 0) for e in acceptances) / len(acceptances) if acceptances else 0

    # Average ambiguity score
    ambiguity_scores = [e.get("ambiguity_score", 0) for e in optimized if "ambiguity_score" in e]
    avg_ambiguity = sum(ambiguity_scores) / len(ambiguity_scores) if ambiguity_scores else 0

    # Average confidence
    confidence_scores = [e.get("confidence", 0) for e in optimized if "confidence" in e]
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0

    # Target model distribution
    target_models = Counter(e.get("target_model") for e in optimized)

    # Optimizer model distribution
    optimizer_models = Counter(e.get("optimizer_model") for e in optimized)

    # Style distribution
    styles = Counter(e.get("style") for e in optimized)

    # Length expansion ratio
    length_ratios = []
    for e in optimized:
        orig = e.get("original_length", 0)
        sugg = e.get("suggested_length", 0)
        if orig > 0:
            length_ratios.append(sugg / orig)
    avg_expansion = sum(length_ratios) / len(length_ratios) if length_ratios else 1.0

    return {
        "total_prompts": len(entries),
        "optimized": len(optimized),
        "passthrough": len(passthrough),
        "optimization_rate": optimization_rate,
        "avg_ambiguity": avg_ambiguity,
        "avg_confidence": avg_confidence,
        "avg_expansion_ratio": avg_expansion,
        "target_models": dict(target_models),
        "optimizer_models": dict(optimizer_models),
        "styles": dict(styles),
        "suggestions_shown": len(acceptances),
        "suggestions_accepted": accepted_count,
        "acceptance_rate": acceptance_rate,
        "avg_similarity": avg_similarity,
    }


def load_file_edits() -> dict:
    """Load file edit tracking for rework analysis."""
    file_path = METRICS_DIR / "file_edits.json"
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def format_report(dora: dict, tdd: dict, prompt: dict, file_edits: dict, token_costs: dict, days: int) -> str:
    """Format human-readable report."""
    report = []
    report.append(f"\n{'=' * 60}")
    report.append(f"  CLAUDE CODE EXTENDED STATS - Last {days} days")
    report.append(f"{'=' * 60}\n")

    # DORA Metrics
    report.append("📊 DORA-STYLE METRICS")
    report.append("-" * 40)
    report.append(f"  File Edits:      {dora['file_edits']}")
    report.append(f"  Rework Rate:     {dora['rework_rate']:.1%} ({dora['rework_count']} reworks)")
    report.append(f"  Test Runs:       {dora['test_runs']}")
    report.append(f"  Test Pass Rate:  {dora['test_pass_rate']:.1%}")
    report.append(f"  Task Completion: {dora['task_completion_rate']:.1%}")
    report.append(f"  Agent Spawns:    {dora['agent_spawns']}")
    report.append(f"  Agent Success:   {dora['agent_success_rate']:.1%}")
    if dora["top_agents"]:
        report.append("  Top Agents:")
        for agent, count in dora["top_agents"].items():
            success_rate = dora.get("agent_success_by_type", {}).get(agent, 1.0)
            report.append(f"    - {agent}: {count} ({success_rate:.0%} success)")
    report.append("")

    # Cycle Time & Session Stats
    report.append("⏱️ CYCLE TIME & SESSION")
    report.append("-" * 40)
    if dora["tasks_with_cycle_time"] > 0:
        report.append(f"  Avg Cycle Time:  {dora['cycle_time_avg_minutes']:.1f} min")
        report.append(f"  Avg Iterations:  {dora['avg_iterations']:.1f} per task")
        report.append(f"  Tasks Tracked:   {dora['tasks_with_cycle_time']}")
    else:
        report.append("  Cycle Time:      No data yet")
    report.append(f"  Tool Calls:      {dora['total_tool_calls']}")
    report.append(f"  Errors:          {dora['total_errors']}")
    report.append(f"  Error Rate:      {dora['error_rate']:.1%}")
    report.append("")

    # TDD Compliance
    report.append("🧪 TDD COMPLIANCE")
    report.append("-" * 40)
    report.append(f"  Total Checks:    {tdd['total_checks']}")
    report.append(f"  Compliant:       {tdd['compliant']}")
    report.append(f"  Violations:      {tdd['violations']}")
    report.append(f"  Compliance Rate: {tdd['compliance_rate']:.1%}")
    if tdd["violation_files"]:
        report.append("  Recent Violations:")
        for f in tdd["violation_files"][:5]:
            report.append(f"    - {Path(f).name if f else 'unknown'}")
    report.append("")

    # Prompt Optimization
    report.append("💡 PROMPT OPTIMIZATION")
    report.append("-" * 40)
    report.append(f"  Total Prompts:     {prompt['total_prompts']}")
    report.append(f"  Optimized:         {prompt['optimized']}")
    report.append(f"  Passthrough:       {prompt['passthrough']}")
    report.append(f"  Optimization Rate: {prompt['optimization_rate']:.1%}")
    report.append(f"  Avg Ambiguity:     {prompt['avg_ambiguity']:.2f}")
    report.append(f"  Avg Confidence:    {prompt['avg_confidence']:.1%}")
    report.append(f"  Avg Expansion:     {prompt['avg_expansion_ratio']:.1f}x")
    if prompt["optimizer_models"]:
        report.append("  Optimizer Models:")
        for model, count in prompt["optimizer_models"].items():
            if model:
                report.append(f"    - {model}: {count}")
    if prompt["target_models"]:
        report.append("  Target Models:")
        for model, count in prompt["target_models"].items():
            if model:
                report.append(f"    - {model}: {count}")
    if prompt["styles"]:
        report.append("  Prompt Styles:")
        for style, count in prompt["styles"].items():
            if style:
                report.append(f"    - {style}: {count}")
    if prompt["suggestions_shown"] > 0:
        report.append(f"  Suggestions:     {prompt['suggestions_shown']} shown")
        report.append(f"  Accepted:        {prompt['suggestions_accepted']} ({prompt['acceptance_rate']:.1%})")
        report.append(f"  Avg Similarity:  {prompt['avg_similarity']:.1%}")
    report.append("")

    # Rework Hotspots
    if file_edits:
        rework_files = [(f, d.get("rework_count", 0)) for f, d in file_edits.items() if d.get("rework_count", 0) > 0]
        rework_files.sort(key=lambda x: x[1], reverse=True)
        if rework_files:
            report.append("🔄 REWORK HOTSPOTS")
            report.append("-" * 40)
            for f, count in rework_files[:5]:
                report.append(f"  {Path(f).name}: {count} reworks")
            report.append("")

    # Token Usage & Costs
    if token_costs.get("session_count", 0) > 0:
        report.append("💰 TOKEN USAGE & COSTS")
        report.append("-" * 40)
        report.append(f"  Sessions:        {token_costs['session_count']}")
        report.append(f"  Total Cost:      ${token_costs['total_cost_usd']:.2f}")
        report.append(f"  Duration:        {token_costs['total_duration_minutes']:.0f} min")

        # Format tokens
        def fmt_tokens(n):
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            elif n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)

        tt = token_costs["total_tokens"]
        report.append(f"  Tokens In:       {fmt_tokens(tt['input'])}")
        report.append(f"  Tokens Out:      {fmt_tokens(tt['output'])}")
        report.append(f"  Cache Read:      {fmt_tokens(tt['cache_read'])}")

        # By model
        if token_costs.get("by_model"):
            report.append("  By Model:")
            for model, stats in sorted(token_costs["by_model"].items(), key=lambda x: x[1]["cost_usd"], reverse=True):
                cost = stats["cost_usd"]
                tokens_out = stats["tokens_out"]
                report.append(f"    - {model}: ${cost:.2f} ({fmt_tokens(tokens_out)} out)")
        report.append("")

    # Summary
    report.append("📋 SUMMARY")
    report.append("-" * 40)

    # Calculate health score with weighted components
    health_score = (
        dora["test_pass_rate"] * 0.25
        + tdd["compliance_rate"] * 0.25
        + (1 - dora["rework_rate"]) * 0.20
        + dora["task_completion_rate"] * 0.15
        + (1 - dora["error_rate"]) * 0.15
    )
    report.append(f"  Health Score: {health_score:.0%}")

    if health_score >= 0.8:
        report.append("  Status: ✅ Excellent")
    elif health_score >= 0.6:
        report.append("  Status: ⚠️ Good, room for improvement")
    else:
        report.append("  Status: ❌ Needs attention")

    # Key insights
    report.append("")
    report.append("  Key Insights:")
    if dora["rework_rate"] > 0.3:
        report.append("  ⚠️ High rework rate - consider better planning")
    if dora["error_rate"] > 0.1:
        report.append("  ⚠️ High error rate - check tool usage patterns")
    if tdd["compliance_rate"] < 0.8:
        report.append("  ⚠️ TDD compliance low - write tests first")
    if prompt["optimization_rate"] > 0.5 and prompt["avg_confidence"] < 0.7:
        report.append("  💡 Many prompts optimized with low confidence - be more specific")
    if dora["cycle_time_avg_minutes"] > 60 and dora["tasks_with_cycle_time"] > 0:
        report.append("  ⏱️ Long cycle times - break tasks into smaller chunks")
    if health_score >= 0.8:
        report.append("  ✅ Keep up the good work!")

    report.append(f"\n{'=' * 60}\n")

    return "\n".join(report)


def analyze_weekly_trends(days: int = 14) -> dict:
    """Compare this week vs last week metrics."""
    now = datetime.now()
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)

    # Load all entries
    all_entries = load_jsonl(METRICS_DIR / "daily.jsonl", days)

    this_week = [
        e
        for e in all_entries
        if datetime.fromisoformat(e.get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None) > this_week_start
    ]
    last_week = [
        e
        for e in all_entries
        if last_week_start
        < datetime.fromisoformat(e.get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        <= this_week_start
    ]

    def count_by_type(entries, entry_type):
        return sum(1 for e in entries if e.get("type") == entry_type)

    def calc_change(current, previous):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return ((current - previous) / previous) * 100

    # Calculate metrics for each week
    this_edits = count_by_type(this_week, "file_edit")
    last_edits = count_by_type(last_week, "file_edit")

    this_tests = count_by_type(this_week, "test_run")
    last_tests = count_by_type(last_week, "test_run")

    this_agents = count_by_type(this_week, "agent_spawn")
    last_agents = count_by_type(last_week, "agent_spawn")

    this_reworks = sum(1 for e in this_week if e.get("is_rework"))
    last_reworks = sum(1 for e in last_week if e.get("is_rework"))

    return {
        "this_week": {
            "file_edits": this_edits,
            "test_runs": this_tests,
            "agent_spawns": this_agents,
            "reworks": this_reworks,
        },
        "last_week": {
            "file_edits": last_edits,
            "test_runs": last_tests,
            "agent_spawns": last_agents,
            "reworks": last_reworks,
        },
        "changes": {
            "file_edits": calc_change(this_edits, last_edits),
            "test_runs": calc_change(this_tests, last_tests),
            "agent_spawns": calc_change(this_agents, last_agents),
            "reworks": calc_change(this_reworks, last_reworks),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Extended Claude Code Stats")
    parser.add_argument("--days", type=int, default=7, help="Number of days to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--trends", action="store_true", help="Show weekly trends")
    parser.add_argument("--project", type=str, help="Filter by project name")
    args = parser.parse_args()

    # Load metrics
    dora_entries = load_jsonl(METRICS_DIR / "daily.jsonl", args.days)
    tdd_entries = load_jsonl(METRICS_DIR / "tdd_compliance.jsonl", args.days)
    prompt_entries = load_jsonl(METRICS_DIR / "prompt_optimization.jsonl", args.days)
    file_edits = load_file_edits()

    # Filter by project if specified
    if args.project:
        dora_entries = [e for e in dora_entries if e.get("project") == args.project]
        tdd_entries = [e for e in tdd_entries if e.get("project") == args.project]

    # Analyze
    dora = analyze_dora_metrics(dora_entries)
    tdd = analyze_tdd_compliance(tdd_entries)
    prompt = analyze_prompt_optimization(prompt_entries)
    token_costs = analyze_token_costs(args.days, args.project)

    if args.json:
        output = {
            "period_days": args.days,
            "project": args.project or "all",
            "dora": dora,
            "tdd": tdd,
            "prompt_optimization": prompt,
            "token_costs": token_costs,
        }
        if args.trends:
            output["trends"] = analyze_weekly_trends()
        print(json.dumps(output, indent=2))
    elif args.trends:
        # Show trends report
        trends = analyze_weekly_trends()
        print(f"\n{'=' * 50}")
        print("  WEEKLY TRENDS")
        print(f"{'=' * 50}\n")
        print("  Metric          This Week  Last Week  Change")
        print("  " + "-" * 46)

        def fmt_change(val):
            if val > 0:
                return f"+{val:.0f}%"
            elif val < 0:
                return f"{val:.0f}%"
            return "0%"

        tw = trends["this_week"]
        lw = trends["last_week"]
        ch = trends["changes"]

        print(f"  File Edits      {tw['file_edits']:>9}  {lw['file_edits']:>9}  {fmt_change(ch['file_edits']):>7}")
        print(f"  Test Runs       {tw['test_runs']:>9}  {lw['test_runs']:>9}  {fmt_change(ch['test_runs']):>7}")
        print(
            f"  Agent Spawns    {tw['agent_spawns']:>9}  {lw['agent_spawns']:>9}  {fmt_change(ch['agent_spawns']):>7}"
        )
        print(f"  Reworks         {tw['reworks']:>9}  {lw['reworks']:>9}  {fmt_change(ch['reworks']):>7}")
        print(f"\n{'=' * 50}\n")
    else:
        print(format_report(dora, tdd, prompt, file_edits, token_costs, args.days))


if __name__ == "__main__":
    main()
