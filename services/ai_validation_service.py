#!/usr/bin/env python3
"""
AI Validation Service
=====================
FastAPI service that uses Claude Agent SDK for specialized validations.
Integrates with ClaudeFlow for PR review and quality scoring.

Usage:
    python ai_validation_service.py
    # Or via systemd service

Endpoints:
    POST /review-pr       - AI code review for PRs
    POST /validate-data   - Data quality validation (pandera/evidently)
    POST /validate-visual - Visual validation (screenshots, UI diff)
    POST /validate-domain - Domain-specific validation
    POST /quality-score   - Calculate and report quality score
    GET /health           - Health check

Environment Variables:
    PORT - Server port (default: 3848)
    QUESTDB_HOST - QuestDB host for metrics (default: localhost)
    QUESTDB_PORT - QuestDB ILP port (default: 9009)

Note: Uses Claude Max subscription via subprocess (no API key needed).
"""

import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ai-validation")

# Environment configuration
PORT = int(os.getenv("PORT", "3848"))
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "localhost")
QUESTDB_PORT = int(os.getenv("QUESTDB_PORT", "9009"))


# =============================================================================
# Domain-Specific System Prompts
# =============================================================================

DOMAIN_PROMPTS = {
    "nautilus": """You are an expert NautilusTrader code reviewer. Focus on:
- Avoid blocking calls in async handlers (use asyncio patterns)
- Validate instrument IDs and trading pairs
- Check position sizing logic and risk parameters
- Verify order management and execution flow
- Watch for race conditions in event handlers
- Ensure proper decimal precision for prices/quantities""",
    "bitcoin": """You are an expert Bitcoin/blockchain code reviewer. Focus on:
- Validate transaction parsing and serialization
- Check for integer overflow in satoshi calculations
- Verify cryptographic operations (hashing, signing)
- Validate address formats (P2PKH, P2SH, bech32)
- Check UTXO handling and dust limits
- Ensure proper handling of block heights and timestamps""",
    "n8n": """You are an expert N8N workflow reviewer. Focus on:
- Validate webhook security (authentication, rate limiting)
- Check credential handling (no hardcoded secrets)
- Verify error handling in nodes (proper try/catch)
- Check for infinite loops in workflow logic
- Validate input/output data transformations
- Ensure proper timeout configurations""",
    "visualization": """You are an expert data visualization reviewer. Focus on:
- Validate data transformations (aggregations, filters)
- Check for XSS vulnerabilities in rendered content
- Verify axis scaling and label formatting
- Check color accessibility (contrast ratios)
- Validate responsive behavior for different screen sizes
- Ensure proper handling of missing/null data""",
    "default": """You are an expert code reviewer. Focus on:
- Security vulnerabilities (OWASP top 10)
- Logic errors and edge cases
- Performance issues and bottlenecks
- Code quality and maintainability
- Test coverage gaps
- Documentation completeness""",
}


# =============================================================================
# Pydantic Models
# =============================================================================


class ValidationSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OK = "OK"


class PRReviewRequest(BaseModel):
    """Request for PR code review"""

    repo: str = Field(..., description="Repository full name (owner/repo)")
    pr_number: int = Field(..., description="Pull request number")
    focus: str = Field("security,logic,patterns", description="Review focus areas (comma-separated)")
    domain: str | None = Field(None, description="Domain for specialized review (nautilus, bitcoin, n8n, etc.)")
    diff: str | None = Field(None, description="PR diff content (optional)")
    files: list[str] | None = Field(None, description="Changed files list")


class PRReviewResponse(BaseModel):
    """Response from PR code review"""

    success: bool
    repo: str
    pr_number: int
    summary: str
    issues: list[dict]
    verdict: str  # APPROVE, REQUEST_CHANGES, COMMENT
    quality_score: float


class DataValidationRequest(BaseModel):
    """Request for data quality validation"""

    repo: str = Field(..., description="Repository full name")
    data_path: str = Field(..., description="Path to data file or directory")
    schema_path: str | None = Field(None, description="Path to schema definition")
    validation_type: str = Field("pandera", description="Validation framework (pandera, evidently, custom)")


class DataValidationResponse(BaseModel):
    """Response from data validation"""

    success: bool
    valid: bool
    errors: list[dict]
    warnings: list[dict]
    quality_score: float


class VisualValidationRequest(BaseModel):
    """Request for visual validation"""

    repo: str = Field(..., description="Repository full name")
    screenshot_path: str = Field(..., description="Path to screenshot")
    baseline_path: str | None = Field(None, description="Path to baseline image")
    validation_type: str = Field("diff", description="Validation type (diff, accessibility, layout)")


class VisualValidationResponse(BaseModel):
    """Response from visual validation"""

    success: bool
    passed: bool
    diff_percentage: float | None = None
    issues: list[dict]


class DomainValidationRequest(BaseModel):
    """Request for domain-specific validation"""

    repo: str = Field(..., description="Repository full name")
    domain: str = Field(..., description="Domain (nautilus, bitcoin, n8n, visualization)")
    file_path: str = Field(..., description="Path to file to validate")
    content: str | None = Field(None, description="File content")


class QualityScoreRequest(BaseModel):
    """Request for quality score calculation"""

    repo: str = Field(..., description="Repository full name")
    commit_sha: str | None = Field(None, description="Commit SHA")
    test_results: dict | None = Field(None, description="Test results")
    lint_results: dict | None = Field(None, description="Lint results")
    coverage: float | None = Field(None, description="Test coverage percentage")


class QualityScoreResponse(BaseModel):
    """Response with quality score"""

    repo: str
    total_score: float
    breakdown: dict
    recommendations: list[str]
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    timestamp: str
    claude_available: bool
    questdb_available: bool


# =============================================================================
# Claude CLI Integration (Max Subscription)
# =============================================================================


def run_claude_review(prompt: str, timeout: int = 120) -> str:
    """
    Run Claude CLI in headless mode (--print).
    Uses Max subscription, no API key needed.
    """
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CLAUDE_NO_INTERACTIVE": "1"},
        )

        if result.returncode != 0:
            logger.warning(f"Claude CLI returned non-zero: {result.stderr}")
            return f"Review failed: {result.stderr[:500]}"

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out")
        return "Review timed out"
    except FileNotFoundError:
        logger.error("Claude CLI not found")
        return "Claude CLI not installed"
    except Exception as e:
        logger.error(f"Claude CLI error: {e}")
        return f"Review error: {str(e)[:500]}"


def parse_review_response(response: str) -> dict:
    """Parse Claude review response into structured format."""
    issues = []
    verdict = "COMMENT"
    summary = ""

    lines = response.split("\n")

    for line in lines:
        line_upper = line.upper().strip()

        # Parse severity lines
        if line_upper.startswith("CRITICAL:"):
            issues.append({"severity": "CRITICAL", "message": line[9:].strip()})
            verdict = "REQUEST_CHANGES"
        elif line_upper.startswith("HIGH:"):
            issues.append({"severity": "HIGH", "message": line[5:].strip()})
            if verdict != "REQUEST_CHANGES":
                verdict = "REQUEST_CHANGES"
        elif line_upper.startswith("MEDIUM:"):
            issues.append({"severity": "MEDIUM", "message": line[7:].strip()})
        elif line_upper.startswith("LOW:"):
            issues.append({"severity": "LOW", "message": line[4:].strip()})
        elif line_upper.startswith("OK"):
            verdict = "APPROVE"

        # Extract summary
        if "summary" in line.lower() and ":" in line:
            summary = line.split(":", 1)[1].strip()

    # Calculate quality score based on issues
    quality_score = 100.0
    for issue in issues:
        if issue["severity"] == "CRITICAL":
            quality_score -= 30
        elif issue["severity"] == "HIGH":
            quality_score -= 15
        elif issue["severity"] == "MEDIUM":
            quality_score -= 5
        elif issue["severity"] == "LOW":
            quality_score -= 2

    quality_score = max(0, quality_score)

    return {
        "issues": issues,
        "verdict": verdict,
        "summary": summary or "Review completed",
        "quality_score": quality_score,
    }


# =============================================================================
# QuestDB Integration (Metrics)
# =============================================================================


async def push_quality_score(repo: str, score: float, breakdown: dict) -> bool:
    """Push quality score to QuestDB via ILP."""
    try:
        import socket

        # ILP line protocol
        timestamp_ns = int(datetime.utcnow().timestamp() * 1e9)
        line = f"quality_scores,repo={repo.replace('/', '_')} "
        line += f"total={score}"

        for key, value in breakdown.items():
            if isinstance(value, (int, float)):
                line += f",{key}={value}"

        line += f" {timestamp_ns}\n"

        # Send to QuestDB
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((QUESTDB_HOST, QUESTDB_PORT))
        sock.sendall(line.encode())
        sock.close()

        logger.info(f"Pushed quality score to QuestDB: {repo} = {score}")
        return True

    except Exception as e:
        logger.warning(f"Failed to push to QuestDB: {e}")
        return False


# =============================================================================
# FastAPI Application
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info(f"Starting AI Validation Service on port {PORT}")
    yield
    logger.info("Shutting down AI Validation Service")


app = FastAPI(
    title="AI Validation Service",
    description="Specialized validation using Claude Agent SDK",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    # Check Claude CLI
    claude_ok = False
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        claude_ok = result.returncode == 0
    except Exception:
        pass

    # Check QuestDB
    questdb_ok = False
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((QUESTDB_HOST, QUESTDB_PORT))
        questdb_ok = result == 0
        sock.close()
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if claude_ok else "degraded",
        timestamp=datetime.utcnow().isoformat() + "Z",
        claude_available=claude_ok,
        questdb_available=questdb_ok,
    )


@app.post("/review-pr", response_model=PRReviewResponse)
async def review_pr(request: PRReviewRequest, background_tasks: BackgroundTasks):
    """
    AI code review for pull requests.

    Uses domain-specific prompts for specialized review.
    Pushes quality score to QuestDB for tracking.
    """
    logger.info(f"Reviewing PR {request.repo}#{request.pr_number}")

    # Get domain-specific system prompt
    domain = request.domain or "default"
    domain_prompt = DOMAIN_PROMPTS.get(domain, DOMAIN_PROMPTS["default"])

    # Build review prompt
    prompt = f"""{domain_prompt}

Review PR #{request.pr_number} in {request.repo}

Focus areas: {request.focus}

"""

    if request.files:
        prompt += f"Changed files:\n{chr(10).join(request.files)}\n\n"

    if request.diff:
        # Truncate diff if too large
        diff = request.diff[:10000] if len(request.diff) > 10000 else request.diff
        prompt += f"Diff:\n{diff}\n\n"

    prompt += """
Provide review with:
- CRITICAL: [issue] (file:line) - Must fix
- HIGH: [issue] (file:line) - Should fix
- MEDIUM: [issue] (file:line) - Consider fixing
- LOW: [issue] (file:line) - Minor improvement
- OK if no issues found

End with verdict: APPROVE, REQUEST_CHANGES, or COMMENT"""

    # Run Claude review
    response = run_claude_review(prompt)
    parsed = parse_review_response(response)

    # Push quality score in background
    background_tasks.add_task(
        push_quality_score,
        request.repo,
        parsed["quality_score"],
        {"pr_number": request.pr_number, "domain": domain},
    )

    return PRReviewResponse(
        success=True,
        repo=request.repo,
        pr_number=request.pr_number,
        summary=parsed["summary"],
        issues=parsed["issues"],
        verdict=parsed["verdict"],
        quality_score=parsed["quality_score"],
    )


@app.post("/validate-data", response_model=DataValidationResponse)
async def validate_data(request: DataValidationRequest):
    """
    Data quality validation using pandera/evidently patterns.
    """
    logger.info(f"Validating data in {request.repo}: {request.data_path}")

    prompt = f"""Analyze data quality for {request.data_path} in {request.repo}.

Validation type: {request.validation_type}
{"Schema: " + request.schema_path if request.schema_path else "No schema provided - infer expected structure."}

Check for:
1. Schema compliance (types, constraints)
2. Data completeness (missing values, nulls)
3. Data consistency (duplicates, outliers)
4. Data freshness (timestamps, staleness)

Format response:
ERRORS:
- [error description]

WARNINGS:
- [warning description]

QUALITY_SCORE: [0-100]"""

    response = run_claude_review(prompt, timeout=60)

    # Parse response
    errors = []
    warnings = []
    quality_score = 80.0

    for line in response.split("\n"):
        if line.strip().startswith("- "):
            if "ERRORS" in response[: response.find(line)].upper():
                errors.append({"message": line[2:].strip()})
            elif "WARNINGS" in response[: response.find(line)].upper():
                warnings.append({"message": line[2:].strip()})

        if "QUALITY_SCORE:" in line.upper():
            try:
                score_str = line.split(":")[-1].strip()
                quality_score = float(score_str.replace("%", ""))
            except ValueError:
                pass

    return DataValidationResponse(
        success=True,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        quality_score=quality_score,
    )


@app.post("/validate-visual", response_model=VisualValidationResponse)
async def validate_visual(request: VisualValidationRequest):
    """
    Visual validation for screenshots and UI.
    """
    logger.info(f"Visual validation: {request.screenshot_path}")

    prompt = f"""Analyze this visual element for {request.repo}.

Screenshot: {request.screenshot_path}
{"Baseline: " + request.baseline_path if request.baseline_path else "No baseline - analyze independently."}
Validation type: {request.validation_type}

Check for:
1. Visual consistency (layout, alignment)
2. Accessibility issues (contrast, text size)
3. Missing elements
4. Unexpected changes

Format:
PASSED: yes/no
ISSUES:
- [issue description]

DIFF_PERCENTAGE: [0-100 if comparing to baseline]"""

    response = run_claude_review(prompt, timeout=60)

    # Parse response
    passed = "PASSED: YES" in response.upper()
    issues = []
    diff_percentage = None

    for line in response.split("\n"):
        if line.strip().startswith("- "):
            issues.append({"message": line[2:].strip()})

        if "DIFF_PERCENTAGE:" in line.upper():
            try:
                diff_str = line.split(":")[-1].strip()
                diff_percentage = float(diff_str.replace("%", ""))
            except ValueError:
                pass

    return VisualValidationResponse(
        success=True,
        passed=passed,
        diff_percentage=diff_percentage,
        issues=issues,
    )


@app.post("/validate-domain")
async def validate_domain(request: DomainValidationRequest):
    """
    Domain-specific validation.
    """
    logger.info(f"Domain validation ({request.domain}): {request.file_path}")

    domain_prompt = DOMAIN_PROMPTS.get(request.domain, DOMAIN_PROMPTS["default"])

    prompt = f"""{domain_prompt}

Validate {request.file_path} in {request.repo}.

{"Content:" + chr(10) + request.content[:5000] if request.content else "Read the file and validate."}

Provide domain-specific validation results:
- CRITICAL: [issue]
- HIGH: [issue]
- MEDIUM: [issue]
- OK if compliant"""

    response = run_claude_review(prompt)
    parsed = parse_review_response(response)

    return {
        "success": True,
        "domain": request.domain,
        "file_path": request.file_path,
        "issues": parsed["issues"],
        "quality_score": parsed["quality_score"],
    }


@app.post("/quality-score", response_model=QualityScoreResponse)
async def calculate_quality_score(request: QualityScoreRequest, background_tasks: BackgroundTasks):
    """
    Calculate and report quality score.
    Integrates with sunrise.md quality scoring system.
    """
    logger.info(f"Calculating quality score for {request.repo}")

    # Weighted score calculation (from sunrise.md)
    breakdown = {
        "code": 25,  # Base: ruff + mypy + bandit
        "test": 30,  # Base: coverage + pass rate
        "data": 25,  # Base: pandera compliance
        "framework": 20,  # Base: speckit/gsd compliance
    }

    # Adjust based on provided results
    if request.test_results:
        pass_rate = request.test_results.get("pass_rate", 100)
        breakdown["test"] = int(30 * (pass_rate / 100))

    if request.coverage:
        breakdown["test"] = int(breakdown["test"] * (request.coverage / 100))

    if request.lint_results:
        error_count = request.lint_results.get("errors", 0)
        deduction = min(25, error_count * 2)
        breakdown["code"] = max(0, 25 - deduction)

    total_score = sum(breakdown.values())

    # Generate recommendations
    recommendations = []
    if breakdown["code"] < 20:
        recommendations.append("Fix lint errors (ruff, mypy)")
    if breakdown["test"] < 25:
        recommendations.append("Improve test coverage and pass rate")
    if total_score < 70:
        recommendations.append("Quality score below threshold - review required")

    # Push to QuestDB
    background_tasks.add_task(push_quality_score, request.repo, total_score, breakdown)

    return QualityScoreResponse(
        repo=request.repo,
        total_score=total_score,
        breakdown=breakdown,
        recommendations=recommendations,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_validation_service:app", host="0.0.0.0", port=PORT, reload=False, log_level="info")
