#!/usr/bin/env node
/**
 * ClaudeFlow Sync Hook
 *
 * Ported from /media/sam/1TB/claude-hooks-shared/hooks/metrics/claudeflow-sync.py
 *
 * PostToolUse hook that syncs state with claude-flow:
 * - Saves session state to claude-flow memory
 * - Tracks agent spawns
 * - Syncs task progress
 * - Enables crash recovery by persisting state
 *
 * Reads from:
 * - SQLite: ~/.claude/hive-mind/hive-mind.db
 * - JSON: ~/.claude-flow/*.json (per-repo)
 *
 * Writes to QuestDB for time-series analysis
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync, spawn } = require("child_process");

// Configuration
const HOME_DIR = os.homedir();
const MCP_DATA_DIR = path.join(HOME_DIR, ".claude-flow");
const SYNC_STATE_FILE = path.join(MCP_DATA_DIR, "sync_state.json");
const GLOBAL_DB = path.join(HOME_DIR, ".claude", "hive-mind", "hive-mind.db");

// Try to load libraries
let metricsLib = null;
let mcpClient = null;
try {
  metricsLib = require("../../lib/metrics.js");
} catch (err) {}
try {
  mcpClient = require("../../lib/mcp-client.js");
} catch (err) {}

/**
 * Ensure directory exists
 */
function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * Get ISO timestamp
 */
function getTimestamp() {
  return new Date().toISOString();
}

/**
 * Get project name
 */
function getProjectName() {
  if (mcpClient) {
    return mcpClient.getProjectName();
  }
  try {
    const result = execSync("git rev-parse --show-toplevel", {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["pipe", "pipe", "pipe"],
    });
    return path.basename(result.trim());
  } catch (err) {
    return path.basename(process.cwd());
  }
}

/**
 * Get session ID
 */
function getSessionId() {
  return process.env.CLAUDE_SESSION_ID || `session_${Date.now()}`;
}

/**
 * Load sync state
 */
function loadSyncState() {
  ensureDir(MCP_DATA_DIR);
  if (fs.existsSync(SYNC_STATE_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(SYNC_STATE_FILE, "utf8"));
    } catch (err) {
      // Ignore parse errors
    }
  }
  return {
    lastSync: null,
    syncCount: 0,
    agentSpawns: [],
    taskProgress: {},
    errors: [],
  };
}

/**
 * Save sync state
 */
function saveSyncState(state) {
  ensureDir(MCP_DATA_DIR);
  state.lastSync = getTimestamp();
  state.syncCount = (state.syncCount || 0) + 1;
  fs.writeFileSync(SYNC_STATE_FILE, JSON.stringify(state, null, 2));
}

/**
 * Sync session state to MCP memory
 */
function syncToMemory(key, value) {
  if (mcpClient) {
    return mcpClient.memoryStore(key, value, "claudeflow");
  }

  // Fallback: store in local file
  const memoryFile = path.join(MCP_DATA_DIR, "memory", "store.json");
  ensureDir(path.dirname(memoryFile));

  let store = { entries: {} };
  if (fs.existsSync(memoryFile)) {
    try {
      store = JSON.parse(fs.readFileSync(memoryFile, "utf8"));
    } catch (err) {}
  }

  store.entries[`claudeflow:${key}`] = {
    key: `claudeflow:${key}`,
    value,
    storedAt: getTimestamp(),
    accessCount: 0,
  };

  fs.writeFileSync(memoryFile, JSON.stringify(store, null, 2));
  return { success: true, direct: true };
}

/**
 * Track agent spawn
 */
function trackAgentSpawn(agentType, description, agentId) {
  const state = loadSyncState();
  const now = getTimestamp();

  state.agentSpawns = state.agentSpawns || [];
  state.agentSpawns.push({
    agentId,
    agentType,
    description,
    spawnedAt: now,
    status: "running",
  });

  // Keep only last 50 spawns
  if (state.agentSpawns.length > 50) {
    state.agentSpawns = state.agentSpawns.slice(-50);
  }

  saveSyncState(state);

  // Sync to memory for crash recovery
  syncToMemory(`agent:${agentId}`, {
    agentType,
    description,
    spawnedAt: now,
    project: getProjectName(),
    sessionId: getSessionId(),
  });

  return state;
}

/**
 * Update task progress
 */
function updateTaskProgress(taskId, status, progress = null) {
  const state = loadSyncState();
  const now = getTimestamp();

  state.taskProgress = state.taskProgress || {};
  state.taskProgress[taskId] = {
    status,
    progress,
    updatedAt: now,
  };

  saveSyncState(state);

  // Sync to memory
  syncToMemory(`task:${taskId}`, {
    status,
    progress,
    updatedAt: now,
    project: getProjectName(),
    sessionId: getSessionId(),
  });

  return state;
}

/**
 * Sync agents profiles from .claude-flow/agents-profiles.json
 */
function syncAgentsProfiles() {
  const lines = [];
  const profilesFile = path.join(MCP_DATA_DIR, "agents-profiles.json");

  if (!fs.existsSync(profilesFile)) {
    return lines;
  }

  try {
    const data = JSON.parse(fs.readFileSync(profilesFile, "utf8"));
    const project = getProjectName();
    const now = Date.now();

    for (const [strategy, metrics] of Object.entries(data)) {
      if (typeof metrics !== "object") continue;

      const successRate = metrics.successRate || 0;
      const avgScore = metrics.avgScore || 0;
      const avgExec = metrics.avgExecutionTime || 0;
      const uses = metrics.uses || 0;
      const realExec = metrics.realExecutions || 0;
      const improving = metrics.improving ? "t" : "f";

      let impRate = 0;
      try {
        impRate = parseFloat(metrics.improvementRate || "0");
      } catch (e) {}

      lines.push({
        table: "claude_strategy_metrics",
        tags: { project, strategy },
        values: {
          success_rate: successRate,
          avg_score: avgScore,
          avg_execution_time: avgExec,
          uses,
          real_executions: realExec,
          improving,
          improvement_rate: impRate,
        },
      });
    }
  } catch (err) {
    // Ignore parse errors
  }

  return lines;
}

/**
 * Sync MCP data (agents, tasks, system metrics)
 */
function syncMCPData() {
  const lines = [];

  // Sync agents
  const agentsFile = path.join(MCP_DATA_DIR, "agents", "store.json");
  if (fs.existsSync(agentsFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(agentsFile, "utf8"));
      for (const agent of Object.values(data.agents || {})) {
        lines.push({
          table: "claude_mcp_agents",
          tags: {
            agent_type: agent.agentType || "unknown",
            status: agent.status || "unknown",
            model: agent.model || "unknown",
          },
          values: {
            health: agent.health || 0,
            task_count: agent.taskCount || 0,
          },
        });
      }
    } catch (err) {}
  }

  // Sync tasks
  const tasksFile = path.join(MCP_DATA_DIR, "tasks", "store.json");
  if (fs.existsSync(tasksFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(tasksFile, "utf8"));
      for (const task of Object.values(data.tasks || {})) {
        lines.push({
          table: "claude_mcp_tasks",
          tags: {
            task_type: task.type || "unknown",
            status: task.status || "unknown",
            priority: task.priority || "normal",
          },
          values: {
            progress: task.progress || 0,
          },
        });
      }
    } catch (err) {}
  }

  // Sync system metrics
  const systemFile = path.join(MCP_DATA_DIR, "system", "metrics.json");
  if (fs.existsSync(systemFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(systemFile, "utf8"));
      const mem = data.memory || {};
      const memPct = mem.total > 0 ? (mem.used / mem.total) * 100 : 0;

      lines.push({
        table: "claude_mcp_system",
        tags: {},
        values: {
          health: data.health || 0,
          cpu: data.cpu || 0,
          memory_pct: memPct,
          agents_active: data.agents?.active || 0,
          agents_total: data.agents?.total || 0,
          tasks_pending: data.tasks?.pending || 0,
          tasks_completed: data.tasks?.completed || 0,
          tasks_failed: data.tasks?.failed || 0,
        },
      });
    } catch (err) {}
  }

  return lines;
}

/**
 * Main sync function
 */
async function syncAll() {
  const allLines = [];
  const syncedSources = [];

  // Sync MCP data
  const mcpLines = syncMCPData();
  if (mcpLines.length > 0) {
    allLines.push(...mcpLines);
    syncedSources.push("mcp:global");
  }

  // Sync agents profiles
  const profileLines = syncAgentsProfiles();
  if (profileLines.length > 0) {
    allLines.push(...profileLines);
    syncedSources.push("profiles");
  }

  // Export to QuestDB if available
  let sentCount = 0;
  if (metricsLib && allLines.length > 0) {
    for (const line of allLines) {
      try {
        await metricsLib.exportToQuestDB(line.table, line.values, line.tags);
        sentCount++;
      } catch (err) {
        // Best effort
      }
    }
  }

  return {
    syncedSources,
    linesSent: sentCount,
    timestamp: getTimestamp(),
  };
}

/**
 * Parse pipeline/skill command from Skill tool
 * Intercepts: pipeline:*, speckit.*, gsd:*
 *
 * Examples:
 * - /pipeline:speckit "snake" -> { framework: 'speckit', target: 'snake', step: null }
 * - /speckit.specify "snake" -> { framework: 'speckit', target: 'snake', step: 'specify' }
 * - /speckit.clarify -> { framework: 'speckit', target: 'auto', step: 'clarify' }
 * - /gsd:plan-phase 05 -> { framework: 'gsd', target: '05', step: 'plan-phase' }
 */
function parsePipelineCommand(skillName, args) {
  if (!skillName) return null;

  let framework = null;
  let step = null;
  let target = args ? args.split(/\s+/)[0] : "auto";

  // Pattern 1: pipeline:framework (e.g., pipeline:speckit, pipeline.gsd)
  if (skillName.includes("pipeline")) {
    framework = skillName.replace("pipeline:", "").replace("pipeline.", "");
    if (!["gsd", "speckit", "status"].includes(framework)) return null;
    step = null; // pipeline command runs full pipeline
  }
  // Pattern 2: speckit.step (e.g., speckit.specify, speckit.clarify)
  else if (skillName.startsWith("speckit.")) {
    framework = "speckit";
    step = skillName.replace("speckit.", "");
  }
  // Pattern 3: gsd:step (e.g., gsd:plan-phase, gsd:execute-phase)
  else if (skillName.startsWith("gsd:")) {
    framework = "gsd";
    step = skillName.replace("gsd:", "");
  } else {
    return null;
  }

  // Clean target - remove quotes if present
  if (target) {
    target = target.replace(/^["']|["']$/g, "");
  }

  return { framework, target: target || "auto", step };
}

/**
 * Save pipeline checkpoint to local file (fast, no npx)
 */
function savePipelineCheckpoint(key, value) {
  const checkpointDir = path.join(MCP_DATA_DIR, "checkpoints");
  ensureDir(checkpointDir);

  const checkpointFile = path.join(
    checkpointDir,
    `${key.replace(/:/g, "_")}.json`,
  );
  fs.writeFileSync(
    checkpointFile,
    JSON.stringify({ key, value, timestamp: getTimestamp() }, null, 2),
  );

  // Fire-and-forget async MCP sync (non-blocking)
  asyncMcpSync(key, value);

  return { success: true, method: "file+mcp" };
}

/**
 * Async MCP sync - fire and forget
 * Spawns detached npx process that syncs to MCP memory in background
 */
function asyncMcpSync(key, value) {
  try {
    const valueJson = JSON.stringify(value);
    const child = spawn(
      "npx",
      [
        "@claude-flow/cli@latest",
        "memory",
        "store",
        "--key",
        key,
        "--value",
        valueJson,
        "--namespace",
        "pipeline",
      ],
      {
        detached: true,
        stdio: "ignore",
        shell: false,
      },
    );
    child.unref(); // Don't wait for process to exit
  } catch (err) {
    // Fire-and-forget: ignore errors
  }
}

/**
 * Track pipeline execution
 * @param {string} framework - gsd or speckit
 * @param {string} target - target spec/phase
 * @param {string} status - starting, done, error
 * @param {string|null} step - sub-step (specify, clarify, plan-phase, etc.)
 * @param {string|null} error - error message if any
 */
function trackPipelineExecution(
  framework,
  target,
  status,
  step = null,
  error = null,
) {
  const project = getProjectName();
  // Key format: framework:project:target[:step]
  const key = step
    ? `${framework}:${project}:${target}:${step}`
    : `${framework}:${project}:${target}`;

  const value = {
    status,
    framework,
    target,
    step,
    project,
    timestamp: getTimestamp(),
    sessionId: getSessionId(),
    error: error ? error.slice(0, 500) : null,
  };

  const result = savePipelineCheckpoint(key, value);

  // Also update sync state
  const state = loadSyncState();
  state.pipelineRuns = state.pipelineRuns || [];
  state.pipelineRuns.push({ key, status, step, timestamp: getTimestamp() });
  if (state.pipelineRuns.length > 100) {
    state.pipelineRuns = state.pipelineRuns.slice(-100);
  }
  saveSyncState(state);

  return { key, ...result };
}

/**
 * Main hook function
 */
async function main() {
  // Read input from stdin
  let input = "";

  if (!process.stdin.isTTY) {
    const chunks = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk);
    }
    input = Buffer.concat(chunks).toString("utf8");
  }

  let inputData = {};
  try {
    inputData = input ? JSON.parse(input) : {};
  } catch (err) {
    console.log(JSON.stringify({}));
    process.exit(0);
  }

  const toolName = inputData.tool_name || "";
  const toolInput = inputData.tool_input || {};
  const toolResponse = inputData.tool_response || {};
  // Detect hook type: PRE hooks don't have tool_response, POST hooks do
  // PreToolUse: { tool_name, tool_input }
  // PostToolUse: { tool_name, tool_input, tool_response }
  const hasResponse =
    inputData.hasOwnProperty("tool_response") &&
    Object.keys(toolResponse).length > 0;
  const hookType = hasResponse ? "post" : "pre";

  // Track agent spawns
  if (toolName === "Task") {
    const agentType = toolInput.subagent_type || "explore";
    const description = (toolInput.description || "").slice(0, 200);
    const agentId = `agent_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    trackAgentSpawn(agentType, description, agentId);
  }

  // Track todo/task progress
  if (toolName === "TodoWrite") {
    const todos = toolInput.todos || [];
    for (const todo of todos) {
      const taskId = (todo.content || "").slice(0, 50);
      const status = todo.status || "pending";
      updateTaskProgress(taskId, status);
    }
  }

  // === PIPELINE CHECKPOINT ===
  // Intercepts: pipeline:*, speckit.*, gsd:*
  if (toolName === "Skill") {
    const skillName = toolInput.skill || "";
    const skillArgs = toolInput.args || "";
    const parsed = parsePipelineCommand(skillName, skillArgs);

    if (parsed) {
      const { framework, target, step } = parsed;

      let status,
        error = null;

      if (hookType === "pre") {
        // PRE-hook: save "starting" checkpoint BEFORE execution
        status = "starting";
      } else {
        // POST-hook: save "done" or "error" checkpoint AFTER execution
        const isError = toolResponse.is_error === true;
        status = isError ? "error" : "done";
        error = isError ? toolResponse.content || "unknown" : null;
      }

      const result = trackPipelineExecution(
        framework,
        target,
        status,
        step,
        error,
      );

      // Output pipeline-specific result
      console.log(
        JSON.stringify({
          synced: true,
          pipeline: true,
          hookType,
          key: result.key,
          status,
          method: result.method,
          framework,
          target,
          step,
        }),
      );
      process.exit(0);
    }
  }

  // Sync session state on certain tools
  const syncTriggers = ["Task", "TodoWrite", "Skill"];
  if (syncTriggers.includes(toolName)) {
    const sessionId = getSessionId();
    const project = getProjectName();

    // Save session state for crash recovery
    syncToMemory(`session:${sessionId}`, {
      project,
      lastTool: toolName,
      lastActivity: getTimestamp(),
      state: loadSyncState(),
    });
  }

  // Periodic full sync (every 10 tool calls)
  const state = loadSyncState();
  if ((state.syncCount || 0) % 10 === 0) {
    await syncAll();
  }

  // Output result
  console.log(
    JSON.stringify({
      synced: true,
      syncCount: state.syncCount || 0,
      agentSpawns: (state.agentSpawns || []).length,
      taskProgress: Object.keys(state.taskProgress || {}).length,
    }),
  );

  process.exit(0);
}

// Export for testing
module.exports = {
  loadSyncState,
  saveSyncState,
  syncToMemory,
  trackAgentSpawn,
  updateTaskProgress,
  syncAgentsProfiles,
  syncMCPData,
  syncAll,
  getProjectName,
  getSessionId,
  MCP_DATA_DIR,
  SYNC_STATE_FILE,
  GLOBAL_DB,
};

// Run if executed directly
if (require.main === module) {
  main().catch((err) => {
    console.error(err);
    console.log(JSON.stringify({}));
    process.exit(0);
  });
}
