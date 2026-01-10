# Reusable GitHub Workflows

Workflow centralizzati per tutti i repo dell'organizzazione `gptprojectmanager`.

## Prerequisiti

1. **Runner org-level** attivo con labels: `self-hosted,shared`
2. Repo deve essere nella stessa org (gptprojectmanager)

## Workflow Disponibili

| Workflow | Descrizione | Inputs |
|----------|-------------|--------|
| `_reusable-security.yml` | Bandit SAST + Gitleaks secrets | `bandit-paths`, `fail-on-high-severity` |
| `_reusable-lint.yml` | Ruff + Mypy | `ruff-args`, `mypy-paths`, `fail-on-type-errors` |
| `_reusable-tests.yml` | Pytest + Coverage | `test-paths`, `coverage-paths`, `coverage-threshold` |

## Uso

Crea un file `.github/workflows/ci.yml` nel tuo repo:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  security:
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-security.yml@main
    with:
      bandit-paths: 'src/ scripts/'

  lint:
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-lint.yml@main
    with:
      mypy-paths: 'src/'

  test:
    needs: [security, lint]
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-tests.yml@main
    with:
      coverage-threshold: 80
```

## Esempio Completo (con outputs)

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  security:
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-security.yml@main
    with:
      bandit-paths: 'src/'
      fail-on-high-severity: true

  lint:
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-lint.yml@main
    with:
      python-version: '3.12'
      mypy-paths: 'src/'
      fail-on-type-errors: false

  test:
    needs: [security, lint]
    uses: gptprojectmanager/claude-hooks-shared/.github/workflows/_reusable-tests.yml@main
    with:
      coverage-threshold: 80
      pytest-args: '--ignore=tests/integration'

  summary:
    needs: [security, lint, test]
    runs-on: [self-hosted, shared]
    if: always()
    steps:
      - name: Pipeline Summary
        run: |
          echo "Security: vulns=${{ needs.security.outputs.vulnerabilities }}"
          echo "Lint: errors=${{ needs.lint.outputs.lint_errors }}"
          echo "Test: coverage=${{ needs.test.outputs.coverage }}%"
```

## Note

- I workflow usano `[self-hosted, shared]` come runner
- Tutti i workflow supportano `python-version` (default: 3.12)
- Gli artifact vengono salvati per 7-30 giorni
