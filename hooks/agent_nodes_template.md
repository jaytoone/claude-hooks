# Agent Nodes — Adaptive Multi-Orchestration
_Modes: DIRECT / PIPELINE / SWARM_
_Version: 1.0.0 | Customize this file to fit your workflow_

---

## Every Request: Node 1 First (No Exceptions)

```
Assess complexity  →  select one of the 3 modes below
```

---

## Mode A: DIRECT (Low Complexity)

No TodoWrite. Minimum overhead — single agent, direct execution.

**When to use:**
- Single-file changes or isolated bug fixes
- Clarification or short Q&A
- Tasks completable in under 5 tool calls

**Flow:**
```
Assess request
  → Investigate current state (read relevant files/code)
  → Implement / respond directly
```

---

## Mode B: PIPELINE (Medium Complexity)

Sequential plan → implement → verify pipeline.

**When to use:**
- Multi-file feature additions
- Refactoring with clear before/after states
- Tasks where ordering matters and parallelism is limited

**Flow:**
```
TodoWrite([
  { id: "plan",   content: "Plan: outline approach and affected files", status: "pending" },
  { id: "impl",   content: "Implement: execute plan step by step",      status: "pending" },
  { id: "verify", content: "Verify: test and review output quality",    status: "pending" },
])

Plan → Implement → Verify
```

---

## Mode C: SWARM (High Complexity)

Parallel exploration + autonomous implementation.

**When to use:**
- Large-scale features spanning many independent modules
- Research tasks where multiple approaches should be explored
- Tasks with 3+ clearly independent work streams

**Flow:**
```
1. Identify N independent work streams (2-4 streams)

2. Create stream-level TodoWrite:
   TodoWrite([
     { id: "stream-1", content: "[Stream 1: description]", status: "pending" },
     { id: "stream-2", content: "[Stream 2: description]", status: "pending" },
     { id: "synth",    content: "Synthesize results",      status: "pending" },
     { id: "verify",   content: "Final verification",      status: "pending" },
   ])

3. Execute streams concurrently in a single response block.
   NOTE: Sub-agents must not spawn further sub-agents (max depth = 1).

4. Wait for all streams → synthesize → final verify
```

> If streams share file dependencies, downgrade to PIPELINE.

---

## Complexity Decision Guide

| Signal | Low (DIRECT) | Medium (PIPELINE) | High (SWARM) |
|--------|-------------|------------------|-------------|
| Files affected | 1-2 | 3-10 | 10+ |
| Estimated tool calls | < 5 | 5-20 | 20+ |
| Independent streams | 0 | 0-1 | 2+ |
| Reversibility | Easy | Moderate | Hard |

---

## Mandatory Rules

1. **Before using any tool**: Check if a more specific tool is available for the job.
2. **Task tracking**: Use TodoWrite for PIPELINE and SWARM modes to track progress.
3. **Quality gate**: Always verify output (run tests, read generated files) before marking done.
4. **Memory policy**: Only store important technical decisions or unresolved problems — not routine task steps.
5. **Depth limit**: Sub-agents spawned in SWARM mode must not spawn further sub-agents.
6. **Retry limit**: If quality check fails twice consecutively, re-plan from scratch rather than patching.
7. **File safety**: Never overwrite files without reading them first. Prefer targeted edits over full rewrites.

---

## Customization Notes

- Add your project-specific rules below this line.
- Reference your own skill files or runbook documents.
- Keep this file under 200 lines to minimize token cost per session.

<!-- PROJECT-SPECIFIC RULES START -->

<!-- PROJECT-SPECIFIC RULES END -->
