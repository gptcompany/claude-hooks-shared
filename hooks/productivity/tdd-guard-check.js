#!/usr/bin/env node
/**
 * TDD Guard Hook - Check tests exist before code changes
 *
 * PreToolUse hook that checks if tests exist before allowing writes
 * to production code. Supports strict/warn/off modes.
 *
 * Hook type: PreToolUse (for Write, Edit)
 *
 * Ported from: /media/sam/1TB/claude-hooks-shared/hooks/productivity/tdd-guard-check.py
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

// Configuration file path
const CONFIG_PATH = path.join(os.homedir(), '.claude', 'tdd-config.json');

// Default configuration
const DEFAULT_CONFIG = {
  mode: 'warn',  // 'strict' | 'warn' | 'off'
  productionPaths: [
    'src/',
    'lib/',
    'app/',
    'core/',
    'services/',
    'models/',
    'handlers/',
    'controllers/',
    'utils/',
    'helpers/',
    'hooks/',
  ],
  skipPaths: [
    'tests/',
    'test/',
    '__tests__/',
    'spec/',
    '__pycache__',
    '.pytest_cache',
    'docs/',
    '.claude/',
    'specs/',
    'config/',
    '.planning/',
    'scripts/',
    'migrations/',
    'fixtures/',
    'node_modules/',
  ],
  codeExtensions: ['.js', '.ts', '.tsx', '.jsx', '.py', '.rs'],
};

// Metrics storage
const METRICS_DIR = path.join(os.homedir(), '.claude', 'metrics');
const TDD_LOG = path.join(METRICS_DIR, 'tdd_compliance.jsonl');

/**
 * Load configuration
 */
function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const content = fs.readFileSync(CONFIG_PATH, 'utf8');
      const config = JSON.parse(content);
      return { ...DEFAULT_CONFIG, ...config };
    }
  } catch {
    // Use defaults
  }
  return DEFAULT_CONFIG;
}

/**
 * Get project name from git repo or environment
 */
function getProjectName() {
  const envName = process.env.CLAUDE_PROJECT_NAME;
  if (envName && envName !== 'unknown') {
    return envName;
  }

  try {
    const result = execSync('git rev-parse --show-toplevel', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 2000,
    });
    return path.basename(result.trim());
  } catch {
    return path.basename(process.cwd());
  }
}

/**
 * Log TDD compliance metric
 */
function logTddMetric(data) {
  try {
    if (!fs.existsSync(METRICS_DIR)) {
      fs.mkdirSync(METRICS_DIR, { recursive: true });
    }

    const entry = {
      timestamp: new Date().toISOString(),
      project: getProjectName(),
      ...data,
    };

    fs.appendFileSync(TDD_LOG, JSON.stringify(entry) + '\n');
  } catch {
    // Silent fail
  }
}

/**
 * Check if file needs TDD verification
 */
function shouldCheckFile(filePath, config) {
  const ext = path.extname(filePath).toLowerCase();

  // Skip non-code files
  if (!config.codeExtensions.includes(ext)) {
    return false;
  }

  // Normalize path
  const normalizedPath = filePath.replace(/\\/g, '/').toLowerCase();

  // Skip test files and other non-production paths
  for (const skip of config.skipPaths) {
    if (normalizedPath.includes(skip.toLowerCase())) {
      return false;
    }
  }

  // Check if in production path
  return config.productionPaths.some(prodPath =>
    normalizedPath.includes(prodPath.toLowerCase())
  );
}

/**
 * Find corresponding test file for a source file
 */
function findTestFile(filePath) {
  const parsed = path.parse(filePath);
  const baseName = parsed.name;
  const dir = parsed.dir;
  const ext = parsed.ext;

  // Determine test file extension based on source extension
  const testExt = ext || '.js';

  // Common test file patterns
  const testPatterns = [
    // Same directory
    path.join(dir, `${baseName}.test${testExt}`),
    path.join(dir, `${baseName}.spec${testExt}`),
    path.join(dir, `test_${baseName}${testExt}`),
    path.join(dir, `${baseName}_test${testExt}`),
    // __tests__ directory
    path.join(dir, '__tests__', `${baseName}.test${testExt}`),
    path.join(dir, '__tests__', `${baseName}.spec${testExt}`),
    // tests/ directory at same level
    path.join(dir, 'tests', `test_${baseName}${testExt}`),
    path.join(dir, 'tests', `${baseName}.test${testExt}`),
    // Parent tests/ directory
    path.join(dir, '..', 'tests', `test_${baseName}${testExt}`),
    path.join(dir, '..', 'tests', `${baseName}.test${testExt}`),
    // Two levels up tests/ directory
    path.join(dir, '..', '..', 'tests', `test_${baseName}${testExt}`),
    path.join(dir, '..', '..', 'tests', `${baseName}.test${testExt}`),
  ];

  // Check each pattern
  for (const testPath of testPatterns) {
    if (fs.existsSync(testPath)) {
      return testPath;
    }
  }

  // Search in project tests/ directory
  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const testDirs = ['tests', 'test', '__tests__', 'spec'];

  for (const testDir of testDirs) {
    const testDirPath = path.join(projectDir, testDir);
    if (fs.existsSync(testDirPath)) {
      // Search recursively (one level)
      try {
        const entries = fs.readdirSync(testDirPath, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isFile()) {
            const name = entry.name.toLowerCase();
            if (name.includes(baseName.toLowerCase()) &&
                (name.includes('test') || name.includes('spec'))) {
              return path.join(testDirPath, entry.name);
            }
          } else if (entry.isDirectory()) {
            // Check subdirectory
            const subDir = path.join(testDirPath, entry.name);
            try {
              const subEntries = fs.readdirSync(subDir);
              for (const subEntry of subEntries) {
                const subName = subEntry.toLowerCase();
                if (subName.includes(baseName.toLowerCase()) &&
                    (subName.includes('test') || subName.includes('spec'))) {
                  return path.join(subDir, subEntry);
                }
              }
            } catch {
              // Ignore
            }
          }
        }
      } catch {
        // Ignore
      }
    }
  }

  return null;
}

/**
 * Read JSON from stdin
 */
async function readStdinJson() {
  return new Promise((resolve, reject) => {
    let data = '';

    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      data += chunk;
    });

    process.stdin.on('end', () => {
      try {
        if (data.trim()) {
          resolve(JSON.parse(data));
        } else {
          resolve({});
        }
      } catch (err) {
        reject(err);
      }
    });

    process.stdin.on('error', reject);

    // Timeout for stdin read
    setTimeout(() => {
      resolve({});
    }, 1000);
  });
}

/**
 * Main function
 */
async function main() {
  try {
    const input = await readStdinJson();
    const config = loadConfig();

    // Check if guard is disabled
    if (config.mode === 'off') {
      console.log(JSON.stringify({}));
      process.exit(0);
    }

    const toolName = input.tool_name || '';
    const toolInput = input.tool_input || {};
    const filePath = toolInput.file_path || '';

    // Only check Write/Edit operations
    if (!['Write', 'Edit', 'MultiEdit'].includes(toolName)) {
      console.log(JSON.stringify({}));
      process.exit(0);
    }

    if (!filePath) {
      console.log(JSON.stringify({}));
      process.exit(0);
    }

    // Check if this file needs TDD verification
    if (!shouldCheckFile(filePath, config)) {
      logTddMetric({
        type: 'skip',
        file: filePath,
        reason: 'not_production_code',
      });
      console.log(JSON.stringify({}));
      process.exit(0);
    }

    // Look for corresponding test file
    const testFile = findTestFile(filePath);

    if (testFile) {
      // Test exists - good!
      logTddMetric({
        type: 'compliant',
        file: filePath,
        test_file: testFile,
      });
      console.log(JSON.stringify({}));
      process.exit(0);
    }

    // No test found - block or warn based on mode
    logTddMetric({
      type: 'violation',
      file: filePath,
      test_file: null,
      blocked: config.mode === 'strict',
    });

    const baseName = path.basename(filePath, path.extname(filePath));
    const ext = path.extname(filePath);
    const testExt = ext || '.js';

    if (config.mode === 'strict') {
      // BLOCK the operation
      const blockMessage = `
TDD VIOLATION: No test file found for \`${path.basename(filePath)}\`

Expected test file patterns:
- \`tests/test_${baseName}${testExt}\`
- \`${baseName}.test${testExt}\` (same directory)
- \`__tests__/${baseName}.test${testExt}\`

Action Required: Write the test FIRST (Red phase), then implement.

To change mode: Edit ~/.claude/tdd-config.json and set "mode": "warn"
`;

      const output = {
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          decision: 'block',
          reason: blockMessage,
        },
      };
      console.log(JSON.stringify(output));
      process.exit(1);  // Non-zero exit to block
    } else {
      // Warn only (default)
      const warning = `
TDD Warning: No test file found for \`${path.basename(filePath)}\`

Expected test file patterns:
- \`tests/test_${baseName}${testExt}\`
- \`${baseName}.test${testExt}\` (same directory)
- \`__tests__/${baseName}.test${testExt}\`

TDD Best Practice: Write failing test BEFORE production code.
`;

      const output = {
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          decision: 'warn',
          message: warning,
        },
      };
      console.log(JSON.stringify(output));
      process.exit(0);
    }
  } catch (err) {
    // Any error, fail open
    console.log(JSON.stringify({}));
    process.exit(0);
  }
}

main();
