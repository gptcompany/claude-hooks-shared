#!/usr/bin/env python3
"""
Verbalized Sampling A/B Test Hook (KISS Implementation)

Compares Claude Sonnet 4.5 vs Gemini 2.5 Pro on creative generation tasks.
Based on Stanford CHATS lab paper: https://github.com/CHATS-lab/verbalized-sampling

Usage: /vsample [N] <your request>
Example: /vsample 5 write a Bitcoin joke

Architecture (Scenario B - Dual Track Independent):
1. Claude Sonnet 4.5 generates N responses + self-selects best
2. Gemini 2.5 Pro generates N responses + self-selects best
3. Comparative output shows both tracks + analysis

KISS Approach: Single hook modifies prompt, Claude orchestrates everything.
"""

import json
import sys
import re


def main():
    # Read hook input
    input_data = json.loads(sys.stdin.read())
    prompt = input_data.get("userPrompt", "")

    # Detect /vsample command
    if not prompt.strip().startswith("/vsample"):
        sys.exit(0)  # Pass through, not our command

    # Parse command: /vsample [N] <request>
    match = re.match(r"/vsample\s+(\d+)?\s*(.*)", prompt.strip())
    if not match:
        sys.exit(0)

    num_samples_str = match.group(1)
    user_request = match.group(2).strip()

    # Default to 5 samples if not specified
    num_samples = int(num_samples_str) if num_samples_str else 5

    # Validate request exists
    if not user_request:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "shouldBlock": True,
                "blockMessage": (
                    "❌ Usage: /vsample [N] <your request>\n\n"
                    "Examples:\n"
                    "  /vsample write a haiku about Bitcoin\n"
                    "  /vsample 7 explain quantum computing\n"
                    "  /vsample 3 create a Python function to validate emails"
                ),
            }
        }
        print(json.dumps(output))
        sys.exit(1)

    # KISS: Transform prompt to instruct Claude to orchestrate the A/B test
    # Claude will:
    # 1. Generate its own VS responses
    # 2. Call Gemini via mcp__gemini-cli__ask-gemini
    # 3. Present comparative analysis

    new_prompt = f"""🎭 VERBALIZED SAMPLING A/B TEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are conducting a dual-track comparison between:
• **Claude Sonnet 4.5** (yourself)
• **Gemini 2.5 Pro** (via MCP)

**User Request**: "{user_request}"
**Samples per track**: {num_samples}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**STEP 1: Generate YOUR responses (Claude Sonnet 4.5)**

Use the Verbalized Sampling technique from the Stanford CHATS lab paper.

Generate {num_samples} diverse and distinct responses to: "{user_request}"

For each response, include:
• **text**: the response content only (no explanations)
• **probability**: estimated likelihood (0.0-1.0) relative to full distribution

Format as JSON:
{{
  "responses": [
    {{"text": "...", "probability": 0.X}},
    ...
  ]
}}

Then SELECT your best response based on creativity, relevance, and quality.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**STEP 2: Get Gemini's responses**

Use the `mcp__gemini-cli__ask-gemini` tool with this EXACT prompt:

"Generate {num_samples} diverse responses to this request: '{user_request}'

Return ONLY a JSON object in this format:
{{
  \"responses\": [
    {{\"text\": \"response 1\", \"probability\": 0.X}},
    {{\"text\": \"response 2\", \"probability\": 0.Y}},
    ...
  ]
}}

Then select the best response and explain why in a 'selection' field:
{{\"selected_index\": N, \"reasoning\": \"...\"}}

Use Verbalized Sampling: sample from the full distribution, maximize diversity."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**STEP 3: Present Comparative Analysis**

Output format:

═══════════════════════════════════════════════════════════
🎭 VERBALIZED SAMPLING A/B TEST RESULTS
═══════════════════════════════════════════════════════════

📝 Request: "{user_request}"
🔢 Samples per track: {num_samples}

───────────────────────────────────────────────────────────
🧠 CLAUDE SONNET 4.5 TRACK
───────────────────────────────────────────────────────────

Generated Responses:
1. (p=X.XX) [response text]
2. (p=X.XX) [response text]
...

✅ Claude's Selection: #N (p=X.XX)
📌 Reasoning: [why you selected this one]

───────────────────────────────────────────────────────────
🤖 GEMINI 2.5 PRO TRACK
───────────────────────────────────────────────────────────

Generated Responses:
[Parse from Gemini's JSON response]

✅ Gemini's Selection: #N (p=X.XX)
📌 Reasoning: [from Gemini's response]

───────────────────────────────────────────────────────────
📊 COMPARATIVE ANALYSIS
───────────────────────────────────────────────────────────

• **Diversity**: Compare probability distributions
• **Creativity**: Analyze uniqueness of responses
• **Quality**: Evaluate selected responses
• **Performance**: Note response times if available

**Recommendation**: Which track produced better results for this specific task?

═══════════════════════════════════════════════════════════

**IMPORTANT**:
• Actually execute mcp__gemini-cli__ask-gemini, don't skip it
• Present ALL {num_samples}×2 = {num_samples * 2} responses
• Be objective in comparing the two tracks
• This is for A/B testing over 1 week, so detailed analysis helps

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**STEP 4: Log Results for Weekly Analysis**

After presenting the comparison, save results to enable pattern analysis.

Use Write tool to append to: `~/.claude/vsample_logs/$(date +%Y-%m-%d).jsonl`

Log entry (one line, compact JSON):
{{
  "timestamp": "ISO8601",
  "request": "{user_request}",
  "num_samples": {num_samples},
  "claude": {{"responses": [...], "selection": {{"idx": N, "text": "...", "p": X, "why": "..."}}}},
  "gemini": {{"responses": [...], "selection": {{"idx": N, "text": "...", "p": X, "why": "..."}}}},
  "meta": {{"diversity_c": X, "diversity_g": Y, "agree": bool, "rec": "..."}}
}}

If dir missing: `mkdir -p ~/.claude/vsample_logs` via Bash first.
Use `jq -c` or manual compact JSON for single-line append.

This enables the verbalized-sampling-analyzer subagent (invoke after 1 week).
"""

    # Return modified prompt
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "modifiedUserPrompt": new_prompt,
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
