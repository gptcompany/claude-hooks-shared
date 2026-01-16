# Onboarding New Repo Runbook

## Quick Start

```bash
# Use the new-project script
/media/sam/1TB/claude-hooks-shared/scripts/new-project.sh <project-name>
```

## Manual Onboarding

### 1. Create Project Structure

```bash
cd /media/sam/1TB/<new-repo>

# Create .claude directory
mkdir -p .claude/validation

# Copy validation config
cp ~/.claude/templates/validation-config.json .claude/validation/config.json
```

### 2. Add Templates

```bash
# Run sync script
/media/sam/1TB/claude-hooks-shared/scripts/sync_templates.sh

# Or manually:
cp ~/.claude/templates/.pre-commit-config.yaml .
sed "s/\${PROJECT_NAME}/<repo-name>/g" ~/.claude/templates/mkdocs.yml > mkdocs.yml
```

### 3. Create Backstage Catalog

```bash
# Copy and customize template
cp ~/.claude/templates/catalog-info.yaml .

# Edit required fields:
# - name
# - description
# - tags
# - spec.type
# - spec.lifecycle
```

### 4. Setup SOPS Encryption

```bash
# Create .env.enc (if needed)
echo "API_KEY=your-key" > .env.tmp
AGE_KEY=$(grep "public key" ~/.config/sops/age/keys.txt | cut -d: -f2 | tr -d ' ')
sops -e --age "$AGE_KEY" --input-type dotenv --output-type dotenv .env.tmp > .env.enc
rm .env.tmp
```

### 5. Initialize Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

### 6. Verify Compliance

```bash
python3 /media/sam/1TB/claude-hooks-shared/scripts/repo_compliance.py
```

## Checklist

- [ ] `.pre-commit-config.yaml` present
- [ ] `mkdocs.yml` configured
- [ ] `catalog-info.yaml` with annotations
- [ ] `.claude/validation/config.json` present
- [ ] `.env.enc` encrypted (if secrets needed)
- [ ] `ARCHITECTURE.md` created
- [ ] `README.md` updated
- [ ] Pre-commit hooks installed
- [ ] Compliance score > 80%
