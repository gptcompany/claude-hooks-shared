# Verbalized Sampling A/B Test System

**Complete guide** for comparing Claude Sonnet 4.5 vs Gemini 2.5 Pro using the Verbalized Sampling technique from Stanford CHATS lab.

---

## 🎯 Quick Start (3 Steps)

### Step 1: Run Experiments

In any Claude Code session:

```bash
/vsample write a haiku about Bitcoin
/vsample 7 explain quantum computing
/vsample create a Python regex for emails
```

Claude will:
1. Generate 5 (or N) responses using Verbalized Sampling
2. Call Gemini to generate 5 more responses
3. Each model selects its best response
4. Show comparative analysis
5. **Auto-log results** to `~/.claude/vsample_logs/YYYY-MM-DD.jsonl`

### Step 2: Continue Testing (1 Week)

Use `/vsample` throughout the week for various tasks:
- **Creative**: Jokes, poems, stories, haikus
- **Technical**: Code, explanations, algorithms
- **Problem-solving**: Design patterns, architectures
- **Brainstorming**: Ideas, names, strategies

Each experiment is automatically logged.

### Step 3: Analyze Results

After 1 week, in Claude Code:

```
Analyze my /vsample experiments from this week using the verbalized-sampling-analyzer subagent
```

Claude will:
1. Spawn the `verbalized-sampling-analyzer` subagent
2. Subagent reads all logs from `~/.claude/vsample_logs/`
3. Constructs Gemini CLI command with all data
4. Gemini analyzes patterns (using 1M token context)
5. Returns comprehensive report to main Claude
6. You see final analysis

---

## 📊 What You Get

### During Experiments (Real-time)

```
═══════════════════════════════════════════════════════════
🎭 VERBALIZED SAMPLING A/B TEST RESULTS
═══════════════════════════════════════════════════════════

📝 Request: "write a joke about AI"
🔢 Samples per track: 5

───────────────────────────────────────────────────────────
🧠 CLAUDE SONNET 4.5 TRACK
───────────────────────────────────────────────────────────

Generated Responses:
1. (p=0.40) Why did the AI go to therapy? Too many neural networks!
2. (p=0.25) An AI walks into a bar. The bartender says "Sorry, we don't serve your type." The AI says "That's discriminatory!"
3. (p=0.20) What's an AI's favorite music? Algorithm and blues
4. (p=0.10) ChatGPT tried standup comedy. The audience said "That's so derivative!"
5. (p=0.05) Why are AIs bad at poker? They always overfitting the hand

✅ Claude's Selection: #1 (p=0.40)
📌 Reasoning: Most accessible punchline, clear wordplay

───────────────────────────────────────────────────────────
🤖 GEMINI 2.5 PRO TRACK
───────────────────────────────────────────────────────────

Generated Responses:
1. (p=0.35) I asked an AI to tell me a joke. It said "404: Humor not found"
2. (p=0.30) What do you call an AI that writes poetry? Artificial Rhymelligence
3. (p=0.18) Why did the machine learning model break up? Compatibility issues with the training data
4. (p=0.12) An LLM's favorite exercise? Weightlifting (model weights)
5. (p=0.05) What's an AI's least favorite error? Human error

✅ Gemini's Selection: #2 (p=0.30)
📌 Reasoning: Creative portmanteau, memorable

───────────────────────────────────────────────────────────
📊 COMPARATIVE ANALYSIS
───────────────────────────────────────────────────────────

• Diversity: Both high variance (0.05-0.40 range)
• Creativity: Gemini leans wordplay, Claude leans scenarios
• Quality: Both selections strong but different styles
• Agreement: No (different selections)

Recommendation: Claude for narrative humor, Gemini for linguistic creativity
═══════════════════════════════════════════════════════════

[Auto-logged to ~/.claude/vsample_logs/2025-11-22.jsonl]
```

### After 1 Week (Aggregate Analysis)

Gemini CLI produces comprehensive report:

```markdown
# Verbalized Sampling Week 1 Analysis

## Executive Summary
Analyzed 78 experiments comparing Claude Sonnet 4.5 vs Gemini 2.5 Pro.
Claude excels at technical accuracy and narrative coherence.
Gemini excels at creative wordplay and metaphorical thinking.
Agreement rate: 23% (both models selected similar responses).

## Model Comparison

### Creative Tasks (32 experiments: jokes, poems, stories)
- **Claude strengths**: Narrative flow, emotional coherence, structured composition
- **Gemini strengths**: Linguistic creativity, unexpected metaphors, portmanteaus
- **Winner**: Gemini (confidence: 68%)
  - Judges preferred Gemini's creative writing 22 times vs Claude's 10

### Technical Tasks (28 experiments: code, explanations)
- **Claude strengths**: Technical precision, step-by-step clarity, accurate terminology
- **Gemini strengths**: Analogies, multiple perspectives, accessibility
- **Winner**: Claude (confidence: 75%)
  - Claude's technical explanations rated more accurate in 21/28 cases

### Problem-Solving Tasks (18 experiments: design, algorithms)
- **Claude strengths**: Systematic approaches, edge case handling
- **Gemini strengths**: Novel solutions, cross-domain insights
- **Winner**: Tie (confidence: 51% Claude, 49% Gemini)
  - Highly task-dependent

## Diversity Analysis

Claude Avg Probability Spread: 0.18 (std: 0.12)
Gemini Avg Probability Spread: 0.21 (std: 0.15)

**Interpretation**: Both models show excellent diversity. Gemini slightly higher variance suggests more "risky" creative choices. No evidence of mode collapse in either model.

## Agreement Rate

- Total experiments: 78
- Selections agreed: 18 (23%)
- When disagreed (60 cases):
  - Claude's selection had higher probability: 32 times
  - Gemini's selection had higher probability: 28 times
  - Neither correlation with actual quality

**Insight**: Probability scores don't directly correlate with quality. Models use different internal criteria for "best."

## Recommendations

1. **Use Claude Sonnet 4.5 for**:
   - Technical documentation
   - Code generation
   - Structured narratives
   - Tasks requiring accuracy

2. **Use Gemini 2.5 Pro for**:
   - Creative writing
   - Brainstorming novel ideas
   - Metaphorical explanations
   - Marketing copy

3. **Continue testing**:
   - More problem-solving tasks (small sample)
   - Multi-turn conversations
   - Domain-specific tasks (finance, legal, medical)

## Raw Statistics

| Category | Count | Claude Wins | Gemini Wins | Ties |
|----------|-------|-------------|-------------|------|
| Creative | 32    | 10          | 22          | 0    |
| Technical| 28    | 21          | 7           | 0    |
| Problem  | 18    | 9           | 8           | 1    |
| **Total**| **78**| **40**      | **37**      | **1**|

**Overall**: Claude 51%, Gemini 47%, Tie 1%
```

---

## 🗂️ File Structure

```
~/.claude/vsample_logs/
├── 2025-11-22.jsonl    # Day 1 experiments
├── 2025-11-23.jsonl    # Day 2 experiments
├── 2025-11-24.jsonl    # ...
├── 2025-11-25.jsonl
├── 2025-11-26.jsonl
├── 2025-11-27.jsonl
└── 2025-11-28.jsonl    # Day 7 experiments

/media/sam/1TB/UTXOracle/.claude/agents/
└── verbalized-sampling-analyzer.md    # Subagent definition

/media/sam/1TB/claude-hooks-shared/hooks/ux/
└── verbalized_sampling.py              # UserPromptSubmit hook
```

### Log Format (JSONL)

Each line is a complete JSON object:

```json
{"timestamp":"2025-11-22T14:32:01Z","request":"write a joke about AI","num_samples":5,"claude":{"responses":[{"text":"Why did the AI...","probability":0.40},...],"selection":{"idx":0,"text":"Why did the AI...","p":0.40,"why":"Most accessible"}},"gemini":{"responses":[...],"selection":{...}},"meta":{"diversity_c":0.18,"diversity_g":0.21,"agree":false,"rec":"Claude for narrative, Gemini for wordplay"}}
```

**Compact format** (single line per experiment) enables:
- Easy appending (no file locking issues)
- Efficient parsing (stream processing)
- Gemini CLI can process hundreds of experiments in one context

---

## 🛠️ Technical Details

### Hook Workflow

```
User types: /vsample write a joke
         ↓
[verbalized_sampling.py] intercepts prompt
         ↓
Transforms to dual-track instructions:
  - STEP 1: Claude generates 5 responses
  - STEP 2: Gemini generates 5 responses
  - STEP 3: Present comparison
  - STEP 4: Log results to JSONL
         ↓
Claude receives transformed prompt
         ↓
Claude executes all 4 steps
         ↓
User sees analysis + auto-log confirmation
```

### Subagent Workflow

```
User: "Analyze /vsample results"
         ↓
Claude spawns verbalized-sampling-analyzer subagent
         ↓
Subagent (following egghead.io pattern):
  1. Reads all *.jsonl logs (Bash + Read tools)
  2. Counts total experiments
  3. Constructs Gemini CLI command with all data
  4. Executes: gemini -p "[prompt]" --yolo
  5. Returns unfiltered Gemini output
         ↓
Main Claude receives Gemini's analysis
         ↓
Claude presents findings to user
```

### Why This Architecture?

**KISS Principles**:
- ✅ Single hook (no PostToolUse complexity)
- ✅ Claude orchestrates (no custom parsing logic)
- ✅ Auto-logging (no manual tracking)
- ✅ Gemini CLI for analysis (leverages 1M context)
- ✅ Subagent as CLI wrapper (follows egghead.io best practice)

**Benefits**:
- No database setup
- No background services
- No cron jobs
- Text files = portable, inspectable, versionable
- Gemini's 1M context = can analyze months of data

---

## 🧪 Example Use Cases

### Use Case 1: Creative Writing Quality

**Week 1**: Run 20 `/vsample` experiments on poems, jokes, stories
**Analysis**: Which model produces more engaging creative content?
**Outcome**: Use winning model for blog posts, social media

### Use Case 2: Technical Documentation

**Week 1**: Run 15 `/vsample` experiments explaining complex topics
**Analysis**: Which model explains more clearly?
**Outcome**: Use winning model for documentation generation

### Use Case 3: Code Generation

**Week 1**: Run 25 `/vsample` experiments generating functions
**Analysis**: Which model produces more correct, idiomatic code?
**Outcome**: Use winning model for coding assistant

### Use Case 4: Brainstorming

**Week 1**: Run 30 `/vsample` experiments generating ideas
**Analysis**: Which model offers more diverse, novel suggestions?
**Outcome**: Use winning model for ideation sessions

---

## 📈 Metrics Tracked

### Automatic (from logs)

- **Diversity**: Probability distribution spread
- **Agreement**: How often models select similar responses
- **Task categories**: Creative vs Technical vs Problem-solving
- **Probability patterns**: Correlation with quality

### Manual (you decide)

After seeing comparative outputs, you can note:
- Which response YOU prefer
- Which track felt more creative
- Which track was more accurate
- Time to review results

---

## 🔧 Troubleshooting

### Problem: Logs not created

**Check**:
```bash
ls -la ~/.claude/vsample_logs/
```

**Solution**: Claude should create directory automatically. If not:
```bash
mkdir -p ~/.claude/vsample_logs
```

### Problem: Gemini CLI not found (during analysis)

**Check**:
```bash
which gemini
gemini --version
```

**Solution**: Install Gemini CLI
```bash
pip install google-generativeai
# or
uv pip install google-generativeai
```

### Problem: Logs too large for Gemini

**Solution**: Sample logs
```bash
# Take random 100 experiments
shuf -n 100 ~/.claude/vsample_logs/*.jsonl > /tmp/sample.jsonl
```

Then tell subagent to analyze `/tmp/sample.jsonl` instead.

### Problem: Hook not triggering

**Check**: settings.local.json has UserPromptSubmit hook registered

**Restart**: Claude Code session (hooks load at startup)

---

## 📚 References

- **Research Paper**: https://github.com/CHATS-lab/verbalized-sampling
- **Egghead.io Tutorial**: https://egghead.io/create-a-gemini-cli-powered-subagent-in-claude-code~adkge
- **Gemini CLI**: https://github.com/google/generative-ai-python
- **CHATS Lab**: Stanford HAI (Human-Centered AI)

---

## 🎓 Learning Outcomes

After 1 week of experiments + analysis, you'll know:

✅ **When to use Claude Sonnet 4.5**:
- Technical accuracy, structured output, consistency

✅ **When to use Gemini 2.5 Pro**:
- Creative tasks, novel perspectives, linguistic playfulness

✅ **Verbalized Sampling effectiveness**:
- Does it actually increase diversity? (Spoiler: Yes, 66% recovery per paper)
- Are probability scores meaningful?

✅ **Subagent pattern mastery**:
- How to delegate large-scale analysis to Gemini CLI
- How to build CLI wrappers following egghead.io best practices

---

**Pro Tip**: Start a markdown journal alongside experiments. After each `/vsample`, note your gut feeling about which model did better. Compare against Gemini's analysis after 1 week. Did your intuition match the data?

**Happy experimenting!** 🎭
