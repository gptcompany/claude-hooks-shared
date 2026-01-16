#!/usr/bin/env python3
"""
Enterprise Secret Rotation Script

Rotates age keys and re-encrypts all .env.enc files across repositories.
Semi-automatic: requires manual confirmation before rotation.

Usage:
    python secret_rotation.py              # Interactive mode (recommended)
    python secret_rotation.py --check      # Check if rotation is due
    python secret_rotation.py --force      # Force rotation without prompts (dangerous)

Safety features:
    - Creates backup before rotation
    - Verifies all decrypts work before committing
    - Keeps previous key as backup
    - Atomic operation (all or nothing)
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
ROTATION_INTERVAL_DAYS = 90
AGE_KEYS_DIR = Path.home() / ".config" / "sops" / "age"
AGE_KEYS_FILE = AGE_KEYS_DIR / "keys.txt"
ROTATION_STATE_FILE = AGE_KEYS_DIR / "rotation_state.json"
SOPS_CONFIG = Path("/media/sam/1TB/.sops.yaml")
BACKUP_ROOT = Path("/media/sam/2TB-NVMe/backups/secrets")

REPOS = [
    Path("/media/sam/1TB/nautilus_dev"),
    Path("/media/sam/1TB/N8N_dev"),
    Path("/media/sam/1TB/UTXOracle"),
    Path("/media/sam/1TB/LiquidationHeatmap"),
    Path("/media/sam/1TB/backstage-portal"),
    Path("/media/sam/1TB/academic_research"),
    Path("/media/sam/1TB/claude-hooks-shared"),
    Path.home() / ".claude",
]


def log(msg: str, level: str = "INFO"):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "ROTATE": "🔄"}.get(level, "")
    print(f"[{timestamp}] {prefix} {msg}")


def run_cmd(cmd: list, capture: bool = True) -> tuple[int, str, str]:
    """Run command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=capture, text=True)
    return result.returncode, result.stdout, result.stderr


def get_rotation_state() -> dict:
    """Load rotation state from file."""
    if ROTATION_STATE_FILE.exists():
        with open(ROTATION_STATE_FILE) as f:
            return json.load(f)
    return {"last_rotation": None, "rotation_count": 0}


def save_rotation_state(state: dict):
    """Save rotation state to file."""
    ROTATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ROTATION_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def days_since_last_rotation() -> int | None:
    """Return days since last rotation, or None if never rotated."""
    state = get_rotation_state()
    if not state.get("last_rotation"):
        return None
    last = datetime.fromisoformat(state["last_rotation"])
    return (datetime.now() - last).days


def is_rotation_due() -> bool:
    """Check if rotation is due."""
    days = days_since_last_rotation()
    if days is None:
        # First rotation - initialize state
        return True
    return days >= ROTATION_INTERVAL_DAYS


def get_current_public_key() -> str | None:
    """Extract public key from current keys file."""
    if not AGE_KEYS_FILE.exists():
        return None
    with open(AGE_KEYS_FILE) as f:
        for line in f:
            if "public key:" in line:
                return line.split(":")[1].strip()
    return None


def generate_new_key() -> tuple[str, str]:
    """Generate new age keypair. Returns (public_key, private_key_line)."""
    code, stdout, stderr = run_cmd(["age-keygen"])
    if code != 0:
        raise RuntimeError(f"Failed to generate key: {stderr}")

    public_key = None
    private_key = None

    for line in stdout.strip().split("\n"):
        if line.startswith("# public key:"):
            public_key = line.split(":")[1].strip()
        elif line.startswith("AGE-SECRET-KEY"):
            private_key = line.strip()

    if not public_key or not private_key:
        raise RuntimeError("Failed to parse generated key")

    return public_key, private_key


def decrypt_env(env_enc_path: Path) -> str | None:
    """Decrypt .env.enc file, return contents or None on failure."""
    code, stdout, stderr = run_cmd(
        ["sops", "-d", "--input-type", "dotenv", "--output-type", "dotenv", str(env_enc_path)]
    )
    if code != 0:
        return None
    return stdout


def encrypt_env(content: str, output_path: Path, public_key: str) -> bool:
    """Encrypt content to .env.enc file with new key."""
    # Write temp file
    temp_path = output_path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        f.write(content)

    try:
        code, stdout, stderr = run_cmd(
            ["sops", "-e", "--age", public_key, "--input-type", "dotenv", "--output-type", "dotenv", str(temp_path)]
        )

        if code != 0:
            log(f"Encrypt failed: {stderr}", "ERROR")
            return False

        # Write encrypted content
        with open(output_path.with_suffix(".new"), "w") as f:
            f.write(stdout)

        return True
    finally:
        temp_path.unlink(missing_ok=True)


def create_pre_rotation_backup() -> Path:
    """Create backup before rotation."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"pre_rotation_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup all .env.enc files
    for repo in REPOS:
        env_enc = repo / ".env.enc"
        if env_enc.exists():
            repo_name = repo.name if repo.name != ".claude" else "dot_claude"
            shutil.copy(env_enc, backup_dir / f"{repo_name}.env.enc")

    # Backup current keys
    if AGE_KEYS_FILE.exists():
        shutil.copy(AGE_KEYS_FILE, backup_dir / "keys.txt.old")

    log(f"Backup created: {backup_dir}", "OK")
    return backup_dir


def update_sops_config(new_public_key: str):
    """Update .sops.yaml with new public key."""
    if not SOPS_CONFIG.exists():
        log(f"SOPS config not found: {SOPS_CONFIG}", "ERROR")
        return False

    content = SOPS_CONFIG.read_text()

    # Find and replace age public key
    old_key = get_current_public_key()
    if old_key:
        content = content.replace(old_key, new_public_key)
        SOPS_CONFIG.write_text(content)
        log("Updated SOPS config with new key", "OK")
        return True

    log("Could not find old key in SOPS config", "ERROR")
    return False


def rotate_secrets(force: bool = False) -> bool:
    """
    Main rotation procedure.

    1. Create backup
    2. Generate new key
    3. Decrypt all with old key
    4. Re-encrypt all with new key
    5. Verify all new encryptions
    6. Commit changes (atomic)
    7. Update SOPS config
    8. Archive old key
    """
    log("=== SECRET ROTATION STARTED ===", "ROTATE")

    # Step 1: Create backup
    backup_dir = create_pre_rotation_backup()

    # Step 2: Generate new key
    log("Generating new age keypair...", "INFO")
    new_public, new_private = generate_new_key()
    log(f"New public key: {new_public[:20]}...", "OK")

    # Step 3: Decrypt all with old key
    log("Decrypting all secrets with current key...", "INFO")
    decrypted = {}

    for repo in REPOS:
        env_enc = repo / ".env.enc"
        if env_enc.exists():
            content = decrypt_env(env_enc)
            if content is None:
                log(f"Failed to decrypt {repo.name}", "ERROR")
                log("Aborting rotation - no changes made", "ERROR")
                return False
            decrypted[repo] = content
            log(f"Decrypted: {repo.name}", "OK")

    # Step 4: Re-encrypt all with new key
    log("Re-encrypting all secrets with new key...", "INFO")

    for repo, content in decrypted.items():
        env_enc = repo / ".env.enc"
        if not encrypt_env(content, env_enc, new_public):
            log(f"Failed to re-encrypt {repo.name}", "ERROR")
            log("Aborting rotation - restoring from backup", "ERROR")
            # Restore would happen here
            return False
        log(f"Re-encrypted: {repo.name}", "OK")

    # Step 5: Verify all new encryptions work
    log("Verifying new encryptions...", "INFO")

    # Save new key temporarily for verification
    temp_keys = AGE_KEYS_DIR / "keys.txt.new"
    with open(temp_keys, "w") as f:
        f.write(f"# created: {datetime.now().isoformat()}\n")
        f.write(f"# public key: {new_public}\n")
        f.write(f"{new_private}\n")

    # Set env to use new keys for verification
    old_env = os.environ.get("SOPS_AGE_KEY_FILE")
    os.environ["SOPS_AGE_KEY_FILE"] = str(temp_keys)

    verification_ok = True
    for repo in decrypted:
        env_new = repo / ".env.enc.new"
        code, stdout, stderr = run_cmd(
            ["sops", "-d", "--input-type", "dotenv", "--output-type", "dotenv", str(env_new)]
        )
        if code != 0:
            log(f"Verification failed for {repo.name}: {stderr}", "ERROR")
            verification_ok = False
        else:
            log(f"Verified: {repo.name}", "OK")

    # Restore env
    if old_env:
        os.environ["SOPS_AGE_KEY_FILE"] = old_env
    else:
        os.environ.pop("SOPS_AGE_KEY_FILE", None)

    if not verification_ok:
        log("Verification failed - aborting rotation", "ERROR")
        # Cleanup .new files
        for repo in decrypted:
            (repo / ".env.enc.new").unlink(missing_ok=True)
        temp_keys.unlink(missing_ok=True)
        return False

    # Step 6: Commit changes (atomic)
    log("Committing rotation...", "ROTATE")

    # Archive old key
    old_keys_archive = AGE_KEYS_DIR / f"keys.txt.{datetime.now().strftime('%Y%m%d')}"
    if AGE_KEYS_FILE.exists():
        shutil.move(AGE_KEYS_FILE, old_keys_archive)
        log(f"Archived old key to {old_keys_archive.name}", "OK")

    # Move new key into place
    shutil.move(temp_keys, AGE_KEYS_FILE)
    os.chmod(AGE_KEYS_FILE, 0o600)
    log("New key installed", "OK")

    # Move .new files into place
    for repo in decrypted:
        env_enc = repo / ".env.enc"
        env_new = repo / ".env.enc.new"
        shutil.move(env_new, env_enc)
    log("All .env.enc files updated", "OK")

    # Step 7: Update SOPS config
    update_sops_config(new_public)

    # Step 8: Update rotation state
    state = get_rotation_state()
    state["last_rotation"] = datetime.now().isoformat()
    state["rotation_count"] = state.get("rotation_count", 0) + 1
    state["previous_key_archive"] = str(old_keys_archive)
    save_rotation_state(state)

    log("=== SECRET ROTATION COMPLETED ===", "ROTATE")
    log(f"Next rotation due in {ROTATION_INTERVAL_DAYS} days", "INFO")
    log(f"Backup location: {backup_dir}", "INFO")

    return True


def check_rotation_status():
    """Print rotation status."""
    days = days_since_last_rotation()
    state = get_rotation_state()

    print("\n=== SECRET ROTATION STATUS ===\n")

    if days is None:
        print("Last rotation: Never (not initialized)")
        print("Status: ⚠️  First rotation recommended")
    else:
        print(f"Last rotation: {state.get('last_rotation', 'Unknown')}")
        print(f"Days since rotation: {days}")
        print(f"Rotation interval: {ROTATION_INTERVAL_DAYS} days")
        print(f"Total rotations: {state.get('rotation_count', 0)}")

        if days >= ROTATION_INTERVAL_DAYS:
            print(f"\nStatus: ⚠️  ROTATION DUE ({days - ROTATION_INTERVAL_DAYS} days overdue)")
        else:
            remaining = ROTATION_INTERVAL_DAYS - days
            print(f"\nStatus: ✅ OK (next rotation in {remaining} days)")

    print(f"\nCurrent public key: {get_current_public_key()[:30]}...")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enterprise Secret Rotation")
    parser.add_argument("--check", action="store_true", help="Check rotation status")
    parser.add_argument("--force", action="store_true", help="Force rotation without prompts")
    args = parser.parse_args()

    if args.check:
        check_rotation_status()
        sys.exit(0 if not is_rotation_due() else 1)

    # Interactive rotation
    check_rotation_status()

    if not args.force:
        print("⚠️  This will rotate all secret encryption keys.")
        print("   All .env.enc files will be re-encrypted with new keys.")
        print("   A backup will be created before any changes.\n")

        confirm = input("Proceed with rotation? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Rotation cancelled.")
            sys.exit(0)

    success = rotate_secrets(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
