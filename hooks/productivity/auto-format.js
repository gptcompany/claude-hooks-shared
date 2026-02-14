#!/usr/bin/env node
/**
 * Auto-Format Hook - Auto-format code files after Write/Edit
 *
 * Automatically formats JavaScript/TypeScript files with prettier/eslint
 * after Write/Edit operations. Fast (<100ms) and silent on errors.
 *
 * Hook type: PostToolUse (for Write, Edit)
 *
 * Ported from: /media/sam/1TB/claude-hooks-shared/hooks/productivity/auto-format.py
 */

const { execSync, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Code file extensions to format
const CODE_EXTENSIONS = new Set(['.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs']);

// Directories to skip
const SKIP_DIRS = [
  'node_modules/',
  '.venv/',
  'venv/',
  '__pycache__/',
  '.git/',
  'dist/',
  'build/',
  'archive/',
  '.next/',
  'coverage/',
];

/**
 * Check if file should be formatted
 */
function shouldFormat(filePath) {
  if (!filePath) return false;

  const ext = path.extname(filePath).toLowerCase();
  if (!CODE_EXTENSIONS.has(ext)) {
    return false;
  }

  // Skip non-code directories
  const normalizedPath = filePath.replace(/\\/g, '/');
  return !SKIP_DIRS.some(dir => normalizedPath.includes(dir));
}

/**
 * Check if a command exists in PATH
 */
function commandExists(cmd) {
  try {
    const bin = process.platform === 'win32' ? 'where' : 'which';
    execFileSync(bin, [cmd], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

/**
 * Find project root (look for package.json or .git)
 */
function findProjectRoot(startPath) {
  let current = path.dirname(startPath);
  const root = path.parse(current).root;

  while (current !== root) {
    if (fs.existsSync(path.join(current, 'package.json')) ||
        fs.existsSync(path.join(current, '.git'))) {
      return current;
    }
    current = path.dirname(current);
  }

  return null;
}

/**
 * Format file with prettier and/or eslint
 */
function formatFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  const projectRoot = findProjectRoot(filePath);
  const cwd = projectRoot || path.dirname(filePath);

  let prettierRan = false;
  let eslintRan = false;

  const hasNpx = commandExists('npx');

  // Try prettier
  if (hasNpx) {
    try {
      // Check if prettier is available in project or globally
      const prettierCheck = execSync('npx prettier --version', {
        cwd,
        stdio: 'pipe',
        timeout: 5000,
      });

      if (prettierCheck) {
        // Run prettier (execFileSync prevents $() subshell injection)
        execFileSync('npx', ['prettier', '--write', '--', filePath], {
          cwd,
          stdio: 'pipe',
          timeout: 10000,
        });
        prettierRan = true;
      }
    } catch {
      // Prettier not available or failed - continue
    }
  }

  // Try eslint --fix
  if (hasNpx) {
    try {
      // Check if eslint is available
      const eslintCheck = execSync('npx eslint --version', {
        cwd,
        stdio: 'pipe',
        timeout: 5000,
      });

      if (eslintCheck) {
        // Run eslint --fix (execFileSync prevents $() subshell injection)
        execFileSync('npx', ['eslint', '--fix', '--', filePath], {
          cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          timeout: 10000,
        });
        eslintRan = true;
      }
    } catch {
      // ESLint not available or failed - continue
    }
  }

  if (prettierRan || eslintRan) {
    return {
      prettier: prettierRan,
      eslint: eslintRan,
      filename: path.basename(filePath),
    };
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

    const toolName = input.tool_name || '';
    const toolInput = input.tool_input || {};
    const filePath = toolInput.file_path || '';

    // Only trigger on Write/Edit
    if (!['Write', 'Edit', 'MultiEdit'].includes(toolName)) {
      process.exit(0);
    }

    // Check if should format
    if (!shouldFormat(filePath)) {
      process.exit(0);
    }

    // Format the file
    const result = formatFile(filePath);

    if (result) {
      // Build message
      const parts = [];
      if (result.prettier) parts.push('prettier');
      if (result.eslint) parts.push('eslint');

      const message = `Auto-formatted ${result.filename} (${parts.join(' + ')})`;

      const output = {
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          message: message,
        },
      };

      console.log(JSON.stringify(output));
    }

    // Always exit 0 (fail open)
    process.exit(0);
  } catch (err) {
    // Any error, fail open
    process.exit(0);
  }
}

main();
