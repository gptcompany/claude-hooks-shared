#!/usr/bin/env node
/**
 * Git Safety Check Hook for Claude Code
 * Prevents dangerous Git operations
 *
 * Protects from:
 * - Force push to main/master
 * - git reset --hard
 * - git clean -f
 * - git checkout . (discards all changes)
 * - git branch -D (force delete)
 *
 * Returns: { decision: "block", reason: "..." } or {} to allow
 */

const path = require('path');
const { readStdinJson, output, runCommand } = require(path.join(__dirname, '..', '..', 'lib', 'utils.js'));

// Configuration
const PROTECTED_BRANCHES = ['main', 'master', 'production'];

/**
 * Get current Git branch name
 */
function getCurrentBranch() {
  const result = runCommand('git rev-parse --abbrev-ref HEAD');
  return result.success ? result.output : null;
}

/**
 * Check if branch is protected
 */
function isProtectedBranch(branch) {
  return PROTECTED_BRANCHES.includes(branch);
}

/**
 * Check for force push attempts
 */
function checkForcePush(command) {
  // Patterns for force push
  const forcePushPatterns = [
    /git\s+push\s+.*--force/,
    /git\s+push\s+.*\s-f(?:\s|$)/,
    /git\s+push\s+--force-with-lease/  // Safer but still risky
  ];

  for (const pattern of forcePushPatterns) {
    if (pattern.test(command)) {
      // Check if pushing to main/master specifically
      if (/\s+(origin\s+)?(main|master)(\s|$)/.test(command)) {
        return { isForce: true, toProtected: true };
      }
      return { isForce: true, toProtected: false };
    }
  }
  return { isForce: false, toProtected: false };
}

/**
 * Check for hard reset
 */
function checkHardReset(command) {
  return /git\s+reset\s+--hard/.test(command);
}

/**
 * Check for git clean with force
 */
function checkGitClean(command) {
  return /git\s+clean\s+.*(--force|-[a-z]*f)/.test(command);
}

/**
 * Check for checkout . (discard all changes)
 */
function checkCheckoutDiscard(command) {
  return /git\s+checkout\s+\./.test(command) || /git\s+restore\s+\./.test(command);
}

/**
 * Check for force branch deletion
 */
function checkBranchForceDelete(command) {
  // Check ALL segments of chained commands
  const segments = command.split(/\s*(?:&&|\|\||;)\s*/);
  for (const segment of segments) {
    const match = segment.trim().match(/git\s+branch\s+.*-D\s+(.+)/);
    if (match) {
      const branches = match[1].trim().split(/\s+/)
        .map(b => b.replace(/["']/g, ''));
      const protectedFound = branches.filter(b => PROTECTED_BRANCHES.includes(b));
      return {
        isForceDelete: true,
        isProtected: protectedFound.length > 0,
        branchName: branches.join(', '),
        protectedBranches: protectedFound
      };
    }
  }
  return { isForceDelete: false };
}

async function main() {
  try {
    const input = await readStdinJson();

    const toolName = input.tool_name || '';
    const toolInput = input.tool_input || {};
    const command = toolInput.command || '';

    // Only check Bash commands with git
    if (toolName !== 'Bash' || !command.includes('git')) {
      output({});
      process.exit(0);
    }

    const currentBranch = getCurrentBranch();
    const errors = [];
    const warnings = [];

    // Check 1: Force push
    const forcePushResult = checkForcePush(command);
    if (forcePushResult.isForce) {
      if (forcePushResult.toProtected) {
        errors.push(
          `BLOCKED: Force push to protected branch (main/master) is not allowed.\n` +
          `Use 'git push' without --force, or create a feature branch first.`
        );
      } else if (currentBranch && isProtectedBranch(currentBranch)) {
        errors.push(
          `BLOCKED: Force push to protected branch '${currentBranch}' is not allowed.\n` +
          `Use 'git push' without --force, or switch to a feature branch.`
        );
      } else {
        warnings.push(
          `WARNING: Force push detected on branch '${currentBranch || 'unknown'}'.\n` +
          `This may overwrite remote history. Proceed with caution.`
        );
      }
    }

    // Check 2: Hard reset
    if (checkHardReset(command)) {
      errors.push(
        `BLOCKED: 'git reset --hard' will discard all uncommitted changes.\n` +
        `Use 'git stash' first to save changes, or 'git reset --soft' to keep them.`
      );
    }

    // Check 3: Git clean with force
    if (checkGitClean(command)) {
      errors.push(
        `BLOCKED: 'git clean -f' will permanently delete untracked files.\n` +
        `Use 'git clean -n' first to see what would be deleted.`
      );
    }

    // Check 4: Checkout discard
    if (checkCheckoutDiscard(command)) {
      errors.push(
        `BLOCKED: 'git checkout .' or 'git restore .' will discard all uncommitted changes.\n` +
        `Use 'git stash' first to save changes.`
      );
    }

    // Check 5: Force branch deletion
    const branchDeleteResult = checkBranchForceDelete(command);
    if (branchDeleteResult.isForceDelete) {
      if (branchDeleteResult.isProtected) {
        errors.push(
          `BLOCKED: Cannot force-delete protected branch '${branchDeleteResult.branchName}'.\n` +
          `Protected branches: ${PROTECTED_BRANCHES.join(', ')}`
        );
      } else {
        warnings.push(
          `WARNING: Force deleting branch '${branchDeleteResult.branchName}'.\n` +
          `This cannot be undone if the branch is not merged. Consider using -d instead.`
        );
      }
    }

    // If errors, block the operation
    if (errors.length > 0) {
      output({
        decision: 'block',
        reason: errors.join('\n\n')
      });
      process.exit(0);
    }

    // If warnings, show but allow (via empty object - Claude Code handles warnings differently)
    if (warnings.length > 0) {
      // For now, just allow with warnings logged to stderr
      console.error(warnings.join('\n\n'));
    }

    // All clear
    output({});
    process.exit(0);

  } catch (err) {
    // On error, fail open (allow operation)
    console.error(`Git safety check error: ${err.message}`);
    output({});
    process.exit(0);
  }
}

main();
