#!/usr/bin/env node
/**
 * Smart Safety Check Hook - Intelligent Command Protection
 *
 * Risk-based categorization:
 * - CRITICAL: Block entirely (fork bombs, rm -rf /, etc.)
 * - HIGH: Warning + checkpoint suggestion
 * - MEDIUM: Warning only
 *
 * Configurable via ~/.claude/safety-config.json
 *
 * Returns: { decision: "block", reason: "..." } or { decision: "warn", message: "..." } or {}
 */

const path = require('path');
const fs = require('fs');
const { readStdinJson, output, getHomeDir } = require(path.join(__dirname, '..', '..', 'lib', 'utils.js'));

// Risk levels
const RISK_CRITICAL = 'CRITICAL';
const RISK_HIGH = 'HIGH';
const RISK_MEDIUM = 'MEDIUM';

// Default configuration
const DEFAULT_CONFIG = {
  enabled: true,
  sudoWhitelist: ['apt', 'apt-get', 'systemctl', 'snap'],
  secretPatterns: ['API_KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PRIVATE_KEY', 'CREDENTIAL'],
  criticalPaths: ['/', '/etc', '/usr', '/var', '/boot', '/sys', '/proc'],
  allowChmod777InCwd: false
};

/**
 * Load configuration from ~/.claude/safety-config.json
 */
function loadConfig() {
  const configPath = path.join(getHomeDir(), '.claude', 'safety-config.json');
  try {
    if (fs.existsSync(configPath)) {
      const userConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      return { ...DEFAULT_CONFIG, ...userConfig };
    }
  } catch (err) {
    console.error(`Warning: Could not load safety config: ${err.message}`);
  }
  return DEFAULT_CONFIG;
}

// Critical patterns - ALWAYS BLOCK (no recovery possible)
const CRITICAL_PATTERNS = [
  { pattern: /:\s*\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?\s*:/, reason: 'Fork bomb detected' },
  { pattern: /dd\s+if=\/dev\/(zero|random|urandom)\s+of=\//, reason: 'dd to critical path' },
  { pattern: /mkfs\.\w+\s+\/dev\//, reason: 'Filesystem formatting detected' },
  { pattern: />\s*\/dev\/(sda|nvme|vda)/, reason: 'Writing to disk device' },
  { pattern: /rm\s+.*-[a-z]*r[a-z]*f[a-z]*\s+["']?\/["']?(?:\s|$)/, reason: 'rm -rf / detected' },
  { pattern: /rm\s+.*-[a-z]*r[a-z]*f[a-z]*\s+["']?\/\*["']?/, reason: 'rm -rf /* detected' },
  { pattern: /rm\s+.*-[a-z]*r[a-z]*f[a-z]*\s+["']?~["']?(?:\s|$)/, reason: 'rm -rf ~ detected' },
  { pattern: /rm\s+.*-[a-z]*r[a-z]*f[a-z]*\s+["']?\$HOME["']?(?:\s|$)/, reason: 'rm -rf $HOME detected' },
  { pattern: /chmod\s+.*-[a-z]*R[a-z]*\s+777\s+["']?\//, reason: 'chmod -R 777 / detected' }
];

// High-risk patterns - Warn strongly, suggest checkpoint
const HIGH_RISK_PATTERNS = [
  { pattern: /rm\s+.*-[a-z]*r[a-z]*f/, reason: 'Recursive force deletion (rm -rf)' },
  { pattern: /rm\s+.*\*.*\*/, reason: 'Multiple wildcards in rm command' },
  { pattern: /find\s+.*-delete/, reason: 'find with -delete flag' },
  { pattern: /curl\s+.*\|\s*(ba)?sh/, reason: 'Piping curl to shell (curl | bash)' },
  { pattern: /wget\s+.*\|\s*(ba)?sh/, reason: 'Piping wget to shell' },
  { pattern: />\s*\/dev\/null\s*2>&1/, reason: 'Silencing all output' }
];

// Medium-risk patterns - Warn only
const MEDIUM_RISK_PATTERNS = [
  { pattern: /chmod\s+.*777/, reason: 'chmod 777 detected (insecure permissions)' },
  { pattern: /chown\s+.*-R/, reason: 'Recursive chown' },
  { pattern: /npm\s+install\s+-g/, reason: 'Global npm install' },
  { pattern: /pip\s+install(?!.*--user)(?!.*-e\s+\.)/, reason: 'System-wide pip install' }
];

/**
 * Escape string for safe use in RegExp constructor
 */
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Check if command contains secrets
 */
function checkForSecrets(command, config) {
  for (const pattern of config.secretPatterns) {
    const safe = escapeRegExp(String(pattern));
    const regex = new RegExp(`${safe}\\s*=\\s*['\"]?[^\\s'\"]+`, 'i');
    if (regex.test(command)) {
      return pattern;
    }
  }
  return null;
}

/**
 * Check if sudo command is whitelisted
 */
function checkSudoWhitelist(command, config) {
  if (!/sudo\s/.test(command)) {
    return { hasSudo: false };
  }

  // Extract the command after sudo
  const match = command.match(/sudo\s+(-[a-zA-Z]+\s+)*(\S+)/);
  if (match) {
    const sudoCommand = match[2];
    const isWhitelisted = config.sudoWhitelist.some(w => sudoCommand === w || sudoCommand.startsWith(`${w} `));
    return { hasSudo: true, isWhitelisted, command: sudoCommand };
  }

  return { hasSudo: true, isWhitelisted: false, command: 'unknown' };
}

/**
 * Categorize command risk level
 */
function categorizeRisk(command, config) {
  // Flag shell evaluation syntax that defeats regex-based inspection
  if (/[`]|(\$\()|(\<\<)/.test(command)) {
    return { level: RISK_HIGH, reason: 'Shell evaluation syntax detected (backticks, $(), or heredoc)' };
  }

  // Split chained commands and check each segment independently
  const segments = command.split(/\s*(?:&&|\|\||;)\s*/);

  for (const segment of segments) {
    const trimmed = segment.trim();
    if (!trimmed) continue;

    // Check critical patterns
    for (const { pattern, reason } of CRITICAL_PATTERNS) {
      if (pattern.test(trimmed)) {
        return { level: RISK_CRITICAL, reason };
      }
    }

    // Check for secrets
    const secretFound = checkForSecrets(trimmed, config);
    if (secretFound) {
      return { level: RISK_HIGH, reason: `Secret detected in command: ${secretFound}` };
    }

    // Check sudo whitelist
    const sudoCheck = checkSudoWhitelist(trimmed, config);
    if (sudoCheck.hasSudo && !sudoCheck.isWhitelisted) {
      return { level: RISK_HIGH, reason: `sudo with non-whitelisted command: ${sudoCheck.command}` };
    }

    // Check high-risk patterns
    for (const { pattern, reason } of HIGH_RISK_PATTERNS) {
      if (pattern.test(trimmed)) {
        return { level: RISK_HIGH, reason };
      }
    }

    // Check medium-risk patterns
    for (const { pattern, reason } of MEDIUM_RISK_PATTERNS) {
      if (pattern.test(trimmed)) {
        return { level: RISK_MEDIUM, reason };
      }
    }
  }

  return null;
}

/**
 * Check if command operates on critical paths
 */
function checkCriticalPaths(command, config) {
  // Split chained commands and check each segment
  const segments = command.split(/\s*(?:&&|\|\||;)\s*/);
  for (const segment of segments) {
    const normalized = segment.replace(/["']/g, '');
    for (const critPath of config.criticalPaths) {
      // Anchor path to space/start-of-arg to avoid matching sub-paths
      const escapedPath = critPath.replace(/\//g, '\\/');
      const regex = new RegExp(`(rm|mv|cp|chmod|chown)\\s+.*(?:\\s|^)${escapedPath}(?:\\/|\\s|[;)|&]|$)`);
      if (regex.test(normalized)) {
        return critPath;
      }
    }
  }
  return null;
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

    // Only check Bash commands
    if (toolName !== 'Bash' || !command) {
      output({});
      process.exit(0);
    }

    // Check for critical path operations
    const criticalPath = checkCriticalPaths(command, config);
    if (criticalPath) {
      output({
        decision: 'block',
        reason: `Operation on critical system path '${criticalPath}' is blocked.\n` +
          `This could damage the system. Run manually if absolutely necessary.`
      });
      process.exit(0);
    }

    // Categorize risk
    const risk = categorizeRisk(command, config);

    if (!risk) {
      // Safe command
      output({});
      process.exit(0);
    }

    const cwd = process.cwd();

    // Handle CRITICAL risk - BLOCK entirely
    if (risk.level === RISK_CRITICAL) {
      output({
        decision: 'block',
        reason: `BLOCKED: ${risk.reason}\n` +
          `Command: ${command.substring(0, 100)}${command.length > 100 ? '...' : ''}\n\n` +
          `This operation is too dangerous and has been blocked.\n` +
          `If absolutely necessary, run it manually outside Claude Code.`
      });
      process.exit(0);
    }

    // Handle HIGH risk - Strong warning
    if (risk.level === RISK_HIGH) {
      output({
        decision: 'warn',
        message: `HIGH RISK: ${risk.reason}\n` +
          `Command: ${command.substring(0, 100)}${command.length > 100 ? '...' : ''}\n\n` +
          `Current directory: ${cwd}\n` +
          `Consider creating a git checkpoint before proceeding:\n` +
          `  git add . && git commit -m "[CHECKPOINT] Before risky operation"`
      });
      process.exit(0);
    }

    // Handle MEDIUM risk - Warning only
    if (risk.level === RISK_MEDIUM) {
      output({
        decision: 'warn',
        message: `MEDIUM RISK: ${risk.reason}\n` +
          `Review this operation carefully before proceeding.`
      });
      process.exit(0);
    }

    // Default: allow
    output({});
    process.exit(0);

  } catch (err) {
    // On error, fail open (allow operation)
    console.error(`Smart safety check error: ${err.message}`);
    output({});
    process.exit(0);
  }
}

main();
