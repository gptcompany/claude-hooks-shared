#!/usr/bin/env python3
"""
Pre-implementation verification for each phase.
Run before implementing to avoid duplicating existing work.

Usage:
    python verify_phase.py 0      # Run all phases
    python verify_phase.py 1      # Run phase 1 only
    python verify_phase.py 2      # Run phase 2 only
    ...
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Installing pyyaml...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

import json

REPOS = [
    Path("/media/sam/1TB/nautilus_dev"),
    Path("/media/sam/1TB/UTXOracle"),
    Path("/media/sam/1TB/N8N_dev"),
    Path("/media/sam/1TB/LiquidationHeatmap"),
]

GLOBAL_TEMPLATES = Path.home() / ".claude/templates"
SHARED_TEMPLATES = Path("/media/sam/1TB/claude-hooks-shared/templates")


@dataclass
class VerificationResult:
    item: str
    exists: bool
    location: str | None
    action: str  # "skip", "create", "update", "migrate"


def verify_phase_1() -> list[VerificationResult]:
    """Verify Backstage auto-discovery requirements."""
    results = []

    # Check if GitHub provider already configured
    app_config = Path("/media/sam/1TB/backstage-portal/app-config.yaml")
    if app_config.exists():
        with open(app_config) as f:
            config = yaml.safe_load(f)
        providers = config.get("catalog", {}).get("providers", {})
        if "github" in providers:
            results.append(
                VerificationResult(
                    "GitHub Entity Provider",
                    True,
                    str(app_config),
                    "skip - already configured",
                )
            )
        else:
            results.append(
                VerificationResult(
                    "GitHub Entity Provider",
                    False,
                    str(app_config),
                    "create - add github provider",
                )
            )

        # Check for hardcoded locations
        locations = config.get("catalog", {}).get("locations", [])
        hardcoded = [loc for loc in locations if loc.get("type") == "file" and "/repos/" in str(loc.get("target", ""))]
        if hardcoded:
            results.append(
                VerificationResult(
                    "Hardcoded repo locations",
                    True,
                    f"{len(hardcoded)} found",
                    "update - remove hardcoded, keep static",
                )
            )
        else:
            results.append(
                VerificationResult(
                    "Hardcoded repo locations",
                    False,
                    None,
                    "skip - none found",
                )
            )

    # Check catalog-info.yaml in each repo
    for repo in REPOS:
        catalog = repo / "catalog-info.yaml"
        if catalog.exists():
            with open(catalog) as f:
                data = yaml.safe_load(f)
            annotations = data.get("metadata", {}).get("annotations", {})
            missing = []
            for ann in ["github.com/project-slug", "github.com/workflows-folder"]:
                if ann not in annotations:
                    missing.append(ann)
            if missing:
                results.append(
                    VerificationResult(
                        f"{repo.name}/catalog-info.yaml annotations",
                        False,
                        str(catalog),
                        f"update - add: {', '.join(missing)}",
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        f"{repo.name}/catalog-info.yaml",
                        True,
                        str(catalog),
                        "skip - complete",
                    )
                )
        else:
            results.append(
                VerificationResult(
                    f"{repo.name}/catalog-info.yaml",
                    False,
                    None,
                    "create - file missing",
                )
            )

    return results


def verify_phase_2() -> list[VerificationResult]:
    """Verify repo consistency templates."""
    results = []

    # Check pre-commit template
    template_found = False
    for template_dir in [GLOBAL_TEMPLATES, SHARED_TEMPLATES]:
        precommit = template_dir / ".pre-commit-config.yaml"
        if precommit.exists():
            results.append(VerificationResult("Pre-commit template", True, str(precommit), "skip - exists"))
            template_found = True
            break
    if not template_found:
        results.append(
            VerificationResult(
                "Pre-commit template",
                False,
                str(GLOBAL_TEMPLATES / ".pre-commit-config.yaml"),
                "create",
            )
        )

    # Check mkdocs template
    template_found = False
    for template_dir in [GLOBAL_TEMPLATES, SHARED_TEMPLATES]:
        mkdocs = template_dir / "mkdocs.yml"
        if mkdocs.exists():
            results.append(VerificationResult("MkDocs template", True, str(mkdocs), "skip - exists"))
            template_found = True
            break
    if not template_found:
        results.append(
            VerificationResult(
                "MkDocs template",
                False,
                str(GLOBAL_TEMPLATES / "mkdocs.yml"),
                "create",
            )
        )

    # Check catalog-info template
    template_found = False
    for template_dir in [GLOBAL_TEMPLATES, SHARED_TEMPLATES]:
        catalog_template = template_dir / "catalog-info.yaml"
        if catalog_template.exists():
            results.append(VerificationResult("Catalog-info template", True, str(catalog_template), "skip - exists"))
            template_found = True
            break
    if not template_found:
        results.append(
            VerificationResult(
                "Catalog-info template",
                False,
                str(GLOBAL_TEMPLATES / "catalog-info.yaml"),
                "create",
            )
        )

    # Check each repo for pre-commit and mkdocs
    for repo in REPOS:
        precommit = repo / ".pre-commit-config.yaml"
        results.append(
            VerificationResult(
                f"{repo.name}/.pre-commit-config.yaml",
                precommit.exists(),
                str(precommit) if precommit.exists() else None,
                "skip" if precommit.exists() else "create from template",
            )
        )

        mkdocs = repo / "mkdocs.yml"
        results.append(
            VerificationResult(
                f"{repo.name}/mkdocs.yml",
                mkdocs.exists(),
                str(mkdocs) if mkdocs.exists() else None,
                "skip" if mkdocs.exists() else "create from template",
            )
        )

    return results


def verify_phase_3() -> list[VerificationResult]:
    """Verify DevOps automation hardening."""
    results = []

    # Check secret_rotation.py for --unattended flag
    rotation_script = Path("/media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py")
    if rotation_script.exists():
        content = rotation_script.read_text()
        if "--unattended" in content or "unattended" in content:
            results.append(
                VerificationResult(
                    "secret_rotation.py --unattended",
                    True,
                    str(rotation_script),
                    "skip - already implemented",
                )
            )
        else:
            results.append(
                VerificationResult(
                    "secret_rotation.py --unattended",
                    False,
                    str(rotation_script),
                    "update - add flag",
                )
            )
    else:
        results.append(
            VerificationResult(
                "secret_rotation.py",
                False,
                None,
                "create - script missing",
            )
        )

    # Check for credentials in crontab
    try:
        crontab_result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        crontab_content = crontab_result.stdout
        # Look for inline credentials (VAR="value" pattern before a command)
        has_inline_creds = False
        for line in crontab_content.split("\n"):
            if not line.strip().startswith("#") and "DISCORD_WEBHOOK" in line:
                if "=" in line and ("https://" in line or "http://" in line):
                    has_inline_creds = True
                    break

        if has_inline_creds:
            results.append(
                VerificationResult(
                    "Crontab credentials",
                    True,
                    "crontab -l",
                    "update - move to SOPS",
                )
            )
        else:
            results.append(VerificationResult("Crontab credentials", False, None, "skip - no inline credentials"))
    except Exception as e:
        results.append(VerificationResult("Crontab credentials", False, None, f"skip - error checking: {e}"))

    # Check log directory
    log_dir = Path("/var/log/claude-hooks")
    results.append(
        VerificationResult(
            "Persistent log directory",
            log_dir.exists(),
            str(log_dir) if log_dir.exists() else None,
            "skip" if log_dir.exists() else "create",
        )
    )

    # Check heartbeat script
    heartbeat_script = Path("/media/sam/1TB/claude-hooks-shared/scripts/heartbeat.py")
    results.append(
        VerificationResult(
            "heartbeat.py (dead man's switch)",
            heartbeat_script.exists(),
            str(heartbeat_script) if heartbeat_script.exists() else None,
            "skip" if heartbeat_script.exists() else "create",
        )
    )

    return results


def verify_phase_4() -> list[VerificationResult]:
    """Verify documentation automation."""
    results = []

    # Check runbooks directory
    runbooks = Path("/media/sam/1TB/claude-hooks-shared/docs/runbooks")
    if runbooks.exists():
        existing = list(runbooks.glob("*.md"))
        if len(existing) >= 5:
            results.append(
                VerificationResult(
                    "Runbooks directory",
                    True,
                    str(runbooks),
                    f"skip - {len(existing)} files exist",
                )
            )
        else:
            results.append(
                VerificationResult(
                    "Runbooks directory",
                    True,
                    str(runbooks),
                    f"update - only {len(existing)} files, need 5",
                )
            )
    else:
        results.append(
            VerificationResult(
                "Runbooks directory",
                False,
                str(runbooks),
                "create with 5 runbooks",
            )
        )

    # Check TechDocs CI workflow template
    techdocs_workflow = GLOBAL_TEMPLATES / "workflows" / "techdocs.yml"
    results.append(
        VerificationResult(
            "TechDocs CI workflow template",
            techdocs_workflow.exists(),
            str(techdocs_workflow) if techdocs_workflow.exists() else None,
            "skip" if techdocs_workflow.exists() else "create",
        )
    )

    # Check sync_templates.sh
    sync_script = Path("/media/sam/1TB/claude-hooks-shared/scripts/sync_templates.sh")
    results.append(
        VerificationResult(
            "sync_templates.sh",
            sync_script.exists(),
            str(sync_script) if sync_script.exists() else None,
            "skip" if sync_script.exists() else "create",
        )
    )

    return results


def verify_phase_5() -> list[VerificationResult]:
    """Verify validation & enforcement."""
    results = []

    # Check compliance script
    compliance = Path("/media/sam/1TB/claude-hooks-shared/scripts/repo_compliance.py")
    results.append(
        VerificationResult(
            "Compliance checker script",
            compliance.exists(),
            str(compliance) if compliance.exists() else None,
            "skip" if compliance.exists() else "create",
        )
    )

    # Check canary deploy script
    canary = Path("/media/sam/1TB/claude-hooks-shared/scripts/canary_deploy.sh")
    results.append(
        VerificationResult(
            "Canary deployment script",
            canary.exists(),
            str(canary) if canary.exists() else None,
            "skip" if canary.exists() else "create",
        )
    )

    # Check validation config in each repo
    for repo in REPOS:
        validation = repo / ".claude/validation/config.json"
        if validation.exists():
            try:
                with open(validation) as f:
                    config = json.load(f)
                # Check if it has advanced fields like nautilus_dev
                has_specialist = "specialist_agent" in config
                has_antipatterns = len(config.get("anti_patterns", [])) > 3
                quality = "complete" if (has_specialist and has_antipatterns) else "basic"
                results.append(
                    VerificationResult(
                        f"{repo.name}/validation/config.json",
                        True,
                        str(validation),
                        f"skip - {quality}" if quality == "complete" else "update - enhance to match nautilus_dev",
                    )
                )
            except json.JSONDecodeError:
                results.append(
                    VerificationResult(
                        f"{repo.name}/validation/config.json",
                        True,
                        str(validation),
                        "update - invalid JSON",
                    )
                )
        else:
            results.append(
                VerificationResult(
                    f"{repo.name}/validation/config.json",
                    False,
                    None,
                    "create from template",
                )
            )

    return results


def print_report(phase: int, results: list[VerificationResult]):
    """Print verification report."""
    print(f"\n{'=' * 60}")
    print(f"PHASE {phase} VERIFICATION REPORT")
    print(f"{'=' * 60}\n")

    skip_count = sum(1 for r in results if "skip" in r.action.lower())
    action_count = len(results) - skip_count

    print(f"Total items: {len(results)}")
    print(f"Already done: {skip_count}")
    print(f"Action needed: {action_count}\n")

    for r in results:
        status = "✅" if "skip" in r.action.lower() else "❌"
        print(f"{status} {r.item}")
        if r.location:
            print(f"   Location: {r.location}")
        print(f"   Action: {r.action}\n")


def main():
    phase = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    phase_funcs = {
        1: ("Backstage Auto-Discovery", verify_phase_1),
        2: ("Repo Consistency Templates", verify_phase_2),
        3: ("DevOps Automation Hardening", verify_phase_3),
        4: ("Documentation Automation", verify_phase_4),
        5: ("Validation & Enforcement", verify_phase_5),
    }

    if phase == 0:
        # Run all phases
        print("\n" + "=" * 60)
        print("FULL VERIFICATION REPORT - ALL PHASES")
        print("=" * 60)

        total_skip = 0
        total_action = 0

        for p in range(1, 6):
            name, func = phase_funcs[p]
            results = func()
            skip = sum(1 for r in results if "skip" in r.action.lower())
            action = len(results) - skip
            total_skip += skip
            total_action += action
            print_report(p, results)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total items already done: {total_skip}")
        print(f"Total actions needed: {total_action}")
        print(f"Completion rate: {total_skip / (total_skip + total_action) * 100:.0f}%")
    else:
        if phase in phase_funcs:
            name, func = phase_funcs[phase]
            print(f"\nVerifying Phase {phase}: {name}")
            print_report(phase, func())
        else:
            print(f"Unknown phase: {phase}")
            print("Valid phases: 0 (all), 1-5")
            sys.exit(1)


if __name__ == "__main__":
    main()
