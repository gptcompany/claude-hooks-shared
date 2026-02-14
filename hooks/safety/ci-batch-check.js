#!/usr/bin/env node
/**
 * CI Batch Check Hook - Warns about multiple pushes in short timeframe
 *
 * FAANG best practice: 1 logical unit = 1 push
 * Prevents CI queue explosion from incremental fixes.
 *
 * Configurable via ~/.claude/ci-config.json
 *
 * Returns: { decision: "warn", message: "..." } or {}
 */

const path = require('path');
const fs = require('fs');
const { readStdinJson, output, getHomeDir } = require(path.join(__dirname, '..', '..', 'lib', 'utils.js'));

// Default configuration
const DEFAULT_CONFIG = {
  enabled: true,
  pushCooldownMinutes: 10,
  maxRapidPushes: 2,
  trackForcePushes: true,
  maxForcePushesPerHour: 1
};

// History file location
const PUSH_HISTORY_FILE = path.join(getHomeDir(), '.claude', 'metrics', 'push_history.json');

/**
 * Load configuration from ~/.claude/ci-config.json
 */
function loadConfig() {
  const configPath = path.join(getHomeDir(), '.claude', 'ci-config.json');
  try {
    if (fs.existsSync(configPath)) {
      const userConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      return { ...DEFAULT_CONFIG, ...userConfig };
    }
  } catch (err) {
    console.error(`Warning: Could not load CI config: ${err.message}`);
  }
  return DEFAULT_CONFIG;
}

/**
 * Load push history from temp file
 */
function loadPushHistory() {
  try {
    if (fs.existsSync(PUSH_HISTORY_FILE)) {
      const data = JSON.parse(fs.readFileSync(PUSH_HISTORY_FILE, 'utf8'));
      return {
        pushes: data.pushes || [],
        forcePushes: data.forcePushes || []
      };
    }
  } catch (err) {
    // Ignore errors, return empty history
  }
  return { pushes: [], forcePushes: [] };
}

/**
 * Save push history to temp file
 */
function savePushHistory(history) {
  try {
    const now = Date.now();
    const oneHourAgo = now - (60 * 60 * 1000);

    // Keep only last hour of history
    history.pushes = history.pushes.filter(ts => ts > oneHourAgo);
    history.forcePushes = history.forcePushes.filter(ts => ts > oneHourAgo);

    // Ensure directory exists before writing
    const dir = path.dirname(PUSH_HISTORY_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    fs.writeFileSync(PUSH_HISTORY_FILE, JSON.stringify(history), 'utf8');
  } catch (err) {
    console.error(`Warning: Could not save push history: ${err.message}`);
  }
}

/**
 * Count events within the last N minutes
 */
function countRecentEvents(timestamps, minutes) {
  const cutoff = Date.now() - (minutes * 60 * 1000);
  return timestamps.filter(ts => ts > cutoff).length;
}

/**
 * Check if command is a git push
 */
function isGitPush(command) {
  return /git\s+push/.test(command);
}

/**
 * Check if command is a force push
 */
function isForcePush(command) {
  return /git\s+push\s+.*\s(-f|--force)(\s|$)/.test(command);
}

/**
 * Get branch being pushed to
 */
function getPushBranch(command) {
  // Try to extract branch from command
  const match = command.match(/git\s+push\s+\S+\s+(\S+)/);
  if (match) {
    return match[1];
  }
  // Default to current branch indicator
  return 'current branch';
}

async function main() {
  try {
    const config = loadConfig();

    if (!config.enabled) {
      output({});
      process.exit(0);
    }

    const input = await readStdinJson();

    const toolName = input.tool_name || '';
    const toolInput = input.tool_input || {};
    const command = toolInput.command || '';

    // Only check Bash commands with git push
    if (toolName !== 'Bash' || !isGitPush(command)) {
      output({});
      process.exit(0);
    }

    const history = loadPushHistory();
    const now = Date.now();
    const isForce = isForcePush(command);
    const branch = getPushBranch(command);

    // Check force push limits
    if (isForce && config.trackForcePushes) {
      const forcePushCount = countRecentEvents(history.forcePushes, 60); // Last hour

      if (forcePushCount >= config.maxForcePushesPerHour) {
        output({
          decision: 'warn',
          message: `[CI Batch Warning] ${forcePushCount + 1} force pushes in the last hour.\n` +
            `Force pushing repeatedly can disrupt CI pipelines and collaborators.\n` +
            `Consider squashing your fixes into a single force push.`
        });

        // Record this force push
        history.forcePushes.push(now);
        savePushHistory(history);
        process.exit(0);
      }

      // Record force push
      history.forcePushes.push(now);
    }

    // Check rapid push limits
    const recentPushCount = countRecentEvents(history.pushes, config.pushCooldownMinutes);

    // Record this push
    history.pushes.push(now);
    savePushHistory(history);

    if (recentPushCount >= config.maxRapidPushes) {
      output({
        decision: 'warn',
        message: `[CI Batch Warning] ${recentPushCount + 1} pushes in ${config.pushCooldownMinutes} minutes.\n` +
          `Branch: ${branch}\n\n` +
          `Consider batching fixes into 1 logical unit per push (FAANG best practice).\n` +
          `This helps:\n` +
          `  - Reduce CI queue congestion\n` +
          `  - Create cleaner git history\n` +
          `  - Make code reviews easier`
      });
      process.exit(0);
    }

    // All good
    output({});
    process.exit(0);

  } catch (err) {
    // On error, fail open (allow operation)
    console.error(`CI batch check error: ${err.message}`);
    output({});
    process.exit(0);
  }
}

main();
