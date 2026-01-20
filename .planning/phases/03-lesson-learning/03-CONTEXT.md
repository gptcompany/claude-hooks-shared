# Phase 3: Lesson Learning & Injection - Context

**Gathered:** 2026-01-20
**Status:** Ready for planning

<vision>
## How This Should Work

Il sistema estrae automaticamente pattern/lezioni dalle sessioni e li reinietta quando rilevanti. Funziona come un "memory layer" che impara dagli errori e successi passati.

Due componenti:
1. **meta_learning.py** (Stop hook) - Analizza sessione, estrae lezioni
2. **lesson_injector.py** (UserPromptSubmit hook) - Cerca e inietta lezioni rilevanti

Il tutto sfruttando al MASSIMO:
- claude-flow MCP (pattern-store, pattern-search, intelligence_learn)
- Hooks esistenti (session_analyzer, dora-tracker, trajectory_tracker)
- Metriche consolidate in QuestDB

Non reinventiamo la ruota - costruiamo il PONTE che attiva le funzionalità già esistenti.

</vision>

<essential>
## What Must Be Nailed

- **Massimo riuso** - Usa claude-flow pattern-store/search, non storage custom
- **Fonti multiple** - Trajectories + session metrics + QuestDB analytics
- **Injection ibrida** - Alta confidence (>0.8) = auto, media = suggerisci, bassa = skip
- **TDD obbligatorio** - Test scritti PRIMA del codice (tdd-guard attivo su hooks/)
- **Confidence scores** - Ogni lezione ha confidence per filtrare noise

</essential>

<specifics>
## Specific Ideas

### Fonti dati per estrazione lezioni:
- `trajectory_tracker.py` → success rate per task type
- `session_analyzer.py` → error rate, tool call patterns
- `dora-tracker.py` → rework rate, cycle time
- `quality-score-tracker.py` → quality trends
- QuestDB → trend storici, pattern ricorrenti

### Pattern da estrarre:
- High rework on file X → "Break changes into smaller commits"
- Error rate > 25% → "Use checkpoints before risky changes"
- Long cycle time on task type Y → "Consider different approach"
- Quality drop after Z → "Run tests more frequently"

### Injection via additionalContext:
```
[Lessons] Based on past sessions:
- Similar task had 40% failure rate - consider checkpoints
- File X was edited 7x in last session - break into smaller changes
```

### claude-flow APIs da usare:
- `pattern-store` → Store learned patterns (HNSW indexed)
- `pattern-search` → Retrieve relevant patterns
- `intelligence_learn` → Trigger SONA consolidation

</specifics>

<notes>
## Additional Context

### Metriche consolidate (analisi completata):
- session_analyzer: Working (JSON)
- dora-tracker: Working (QuestDB: dora_metrics)
- quality-score-tracker: Working (QuestDB: claude_quality_scores)
- claudeflow-sync: Working (QuestDB: 10+ tables)

### TDD guard ora attivo su hooks/:
- Ogni nuovo hook richiede test
- Pattern: RED → GREEN → REFACTOR

### Differenza da claude-flow built-in:
- claude-flow ha learning ma è PASSIVO (deve essere chiamato)
- I nostri hooks sono il PONTE che attiva automaticamente
- NON duplicazione, INTEGRAZIONE

</notes>

---

*Phase: 03-lesson-learning*
*Context gathered: 2026-01-20*
