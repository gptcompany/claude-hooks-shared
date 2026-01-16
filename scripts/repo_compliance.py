#!/usr/bin/env python3
"""
Enterprise Repo Compliance Checker
Validates repos against global standards.

Usage:
    python repo_compliance.py              # Check all repos
    python repo_compliance.py --json       # Output as JSON
    python repo_compliance.py --fix        # Auto-fix simple issues
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPOS = [
    Path("/media/sam/1TB/nautilus_dev"),
    Path("/media/sam/1TB/UTXOracle"),
    Path("/media/sam/1TB/N8N_dev"),
    Path("/media/sam/1TB/LiquidationHeatmap"),
]

REQUIRED_FILES = [
    ".pre-commit-config.yaml",
    "catalog-info.yaml",
    "mkdocs.yml",
    ".env.enc",
    "ARCHITECTURE.md",
    "README.md",
    ".claude/validation/config.json",
]

REQUIRED_ANNOTATIONS = [
    "backstage.io/techdocs-ref",
    "github.com/project-slug",
    "github.com/workflows-folder",
]


@dataclass
class ComplianceResult:
    repo: str
    score: int
    max_score: int
    percentage: int
    issues: list = field(default_factory=list)
    grade: str = ""


def check_repo(repo_path: Path) -> ComplianceResult:
    """Check repo compliance."""
    issues = []
    score = 0
    max_score = len(REQUIRED_FILES) + len(REQUIRED_ANNOTATIONS)

    # Check required files
    for f in REQUIRED_FILES:
        if (repo_path / f).exists():
            score += 1
        else:
            issues.append(f"Missing: {f}")

    # Check catalog annotations
    catalog_file = repo_path / "catalog-info.yaml"
    if catalog_file.exists():
        try:
            with open(catalog_file) as f:
                catalog = yaml.safe_load(f)
            annotations = catalog.get("metadata", {}).get("annotations", {})
            for ann in REQUIRED_ANNOTATIONS:
                if ann in annotations:
                    score += 1
                else:
                    issues.append(f"Missing annotation: {ann}")
        except Exception as e:
            issues.append(f"Invalid catalog-info.yaml: {e}")

    # Calculate grade
    percentage = round(score / max_score * 100) if max_score > 0 else 0
    if percentage >= 90:
        grade = "A"
    elif percentage >= 80:
        grade = "B"
    elif percentage >= 70:
        grade = "C"
    elif percentage >= 60:
        grade = "D"
    else:
        grade = "F"

    return ComplianceResult(
        repo=repo_path.name,
        score=score,
        max_score=max_score,
        percentage=percentage,
        issues=issues,
        grade=grade,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enterprise Repo Compliance Checker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--fix", action="store_true", help="Auto-fix simple issues")
    args = parser.parse_args()

    results = []
    for repo in REPOS:
        if repo.exists():
            result = check_repo(repo)
            results.append(result)

    if args.json:
        output = {
            "repos": [
                {
                    "name": r.repo,
                    "score": r.score,
                    "max_score": r.max_score,
                    "percentage": r.percentage,
                    "grade": r.grade,
                    "issues": r.issues,
                }
                for r in results
            ],
            "average": sum(r.percentage for r in results) / len(results) if results else 0,
        }
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "=" * 60)
        print("ENTERPRISE REPO COMPLIANCE REPORT")
        print("=" * 60 + "\n")

        for result in results:
            status = "OK" if result.percentage >= 80 else "WARN" if result.percentage >= 60 else "FAIL"
            print(f"[{status}] {result.repo}")
            print(f"    Score: {result.score}/{result.max_score} ({result.percentage}%) - Grade: {result.grade}")
            if result.issues:
                for issue in result.issues[:5]:  # Show max 5 issues
                    print(f"    - {issue}")
                if len(result.issues) > 5:
                    print(f"    ... and {len(result.issues) - 5} more issues")
            print()

        # Summary
        avg_score = sum(r.percentage for r in results) / len(results) if results else 0
        print("=" * 60)
        print(f"AVERAGE COMPLIANCE: {avg_score:.0f}%")
        print("=" * 60)

        # Exit with error if any repo below 80%
        if any(r.percentage < 80 for r in results):
            sys.exit(1)


if __name__ == "__main__":
    main()
