---
title: "Learn Claude Code: 12 Sessions to Build an AI Agent Harness from Scratch"
mathjax: true
toc: true
categories:
  - Study
tags:
  - Agent
  - LLM
  - Claude Code
---

[Learn Claude Code](https://github.com/anthropics/learn-claude-code) is a teaching repository that reverse-engineers how **Claude Code** (Anthropic's AI coding agent) works internally. It distills the harness engineering into 12 progressive Python sessions — from a bare `while` loop to a full multi-agent autonomous team. It also ships a Next.js web app for interactive learning.

Core philosophy: *"The model IS the agent. Not a framework. Not a prompt chain. The intelligence comes from the model; the code is just the vehicle."*

## 0 What Is a Harness?

A **harness** is the code that wraps around an LLM, giving it tools, context, memory, and execution environment. Claude Code itself is a harness. This repo teaches you to build one from zero.

```
Harness = Tools + Context Management + Memory + Permissions + Execution Environment
Agent  = LLM + Harness
```

## 1 The 12 Sessions — Progressive Complexity

The sessions are grouped into 5 layers, each building on the previous:

```
Layer 1: Tools & Execution     [s01, s02]      — The core loop
Layer 2: Planning               [s03, s04, s05, s07] — Structure & knowledge
Layer 3: Memory                 [s06]           — Infinite sessions
Layer 4: Concurrency            [s08]           — Background execution
Layer 5: Collaboration          [s09-s12]       — Multi-agent teams
```

Every session is a **self-contained Python file** (~200-500 lines) that you can run directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-xxx
python agents/s01_agent_loop.py
```

### s01 — The Agent Loop

*"One loop & Bash is all you need."*

The minimal viable agent — a `while` loop that calls the LLM, checks for tool calls, executes them, and feeds results back:

```python
while stop_reason == "tool_use":
    response = client.messages.create(model=MODEL, messages=messages, tools=tools)
    for block in response.content:
        if block.type == "tool_use":
            result = execute_tool(block.name, block.input)
            messages.append({"role": "user", content: [{"type": "tool_result", ...}]})
    stop_reason = response.stop_reason
```

One tool: `bash` (shell commands, 120s timeout). That's the entire kernel. Everything else is built on top.

### s02 — Tool Dispatch

*"Adding a tool means adding one handler."*

The loop stays exactly the same. New tools are added to a dispatch map:

```python
TOOL_HANDLERS = {
    "bash":       handle_bash,
    "read_file":  handle_read_file,
    "write_file": handle_write_file,
    "edit_file":  handle_edit_file,
}
output = TOOL_HANDLERS[tool_name](**kwargs)
```

Key insight: scalable capabilities don't require changing the loop.

### s03 — TodoWrite (Planning)

*"An agent without a plan drifts."*

Adds a `TodoManager` with structured task tracking:

```
[ ] pending  →  [>] in_progress  →  [x] completed
```

Constraint: only one task can be `in_progress` at a time. If the agent hasn't updated todos for 3+ rounds, the harness injects a **nag reminder** into the conversation. This forces sequential, visible planning.

### s04 — Subagents

*"Break big tasks down; each subtask gets a clean context."*

The `task` tool spawns a fresh agent with `messages = []` (empty history). The subagent runs independently, then returns only a text summary. Parent context stays clean.

```
Parent:  [full conversation history + task tool]
  ↓ spawn
Child:   [empty messages + prompt only, NO task tool (prevents recursion)]
  ↓ returns summary
Parent:  [receives short summary, context uncontaminated]
```

### s05 — Skill Loading

*"Load knowledge when you need it, not upfront."*

Two-layer injection:
- **Layer 1** (always in system prompt): skill metadata — name + description (~100 tokens each)
- **Layer 2** (on-demand): full `SKILL.md` body injected via `tool_result` when `load_skill(name)` is called

The agent sees the skill catalog cheaply, then loads the full reference only when needed. This prevents system prompt bloat.

### s06 — Context Compaction

*"Context will fill up; you need a way to make room."*

Three-layer compression strategy:

| Layer | Trigger | Action |
|-------|---------|--------|
| **Micro** | Every turn | Replace old tool results with `[Previous: used {tool_name}]` |
| **Auto** | Token threshold (~50k) | Archive transcript to `.transcripts/`, LLM summarizes, replace all with summary |
| **Manual** | Agent calls `compact` tool | Same as auto, but agent-initiated |

This enables **infinite sessions** — the agent can work for hours without running out of context.

### s07 — Task System

*"Break big goals into small tasks, order them, persist to disk."*

File-based task board: each task is a JSON file in `.tasks/task_{id}.json`:

```json
{
  "id": "task_1",
  "subject": "Implement auth",
  "status": "in_progress",
  "blockedBy": [],
  "blocks": ["task_3"],
  "owner": "lead"
}
```

Dependency resolution: completing `task_1` automatically removes it from `task_3.blockedBy`. Tasks survive context compression because they live on disk, not in conversation history.

### s08 — Background Tasks

*"Run slow operations in the background; the agent keeps thinking."*

`BackgroundManager` spawns daemon threads for long-running shell commands. Returns immediately with a `task_id`. Notifications are drained and injected before each LLM call:

```
Agent: background_run("npm test")  →  "task_bg_1 started"
Agent: [continues working on other things]
...
[Before next LLM call, harness injects]:
<background-results>
  bg_1 completed: "All 42 tests passed"
</background-results>
```

### s09 — Agent Teams

*"When the task is too big for one, delegate to teammates."*

File-based message bus with JSONL inboxes per teammate. The lead agent spawns persistent named agents running in daemon threads:

```
Lead Agent
  ├── spawn_teammate("frontend-dev", "Build React components")
  ├── spawn_teammate("backend-dev", "Build API endpoints")
  └── broadcast("Use TypeScript everywhere")
          ↓                    ↓
   .team/inbox_frontend-dev.jsonl    .team/inbox_backend-dev.jsonl
```

Each teammate has its own agent loop, reads its inbox, does work, and can message back. 9 tools for the lead (spawn, send_message, read_inbox, broadcast, etc.)

### s10 — Team Protocols

*"Teammates need shared communication rules."*

Two FSM protocols built on the same **request-id correlation** pattern:

**Shutdown Protocol:**
```
Lead  →  shutdown_request(request_id)  →  Teammate
Lead  ←  shutdown_response(request_id, approved: true)  ←  Teammate
```

**Plan Approval Protocol:**
```
Teammate  →  plan_approval(request_id, plan)  →  Lead
Teammate  ←  plan_approval_response(request_id, approved: true)  ←  Lead
```

Both use the same pattern: send a message with `request_id`, wait for response with matching `request_id`. One pattern, all team negotiation.

### s11 — Autonomous Agents

*"Teammates scan the board and claim tasks themselves."*

Teammates don't wait for assignments — they **poll the task board** and self-assign:

```python
def scan_unclaimed_tasks():
    # Find .tasks/task_*.json where status=pending and owner=None
    return unclaimed

def claim_task(task_id, agent_name):
    # Atomic claim with lock (prevents race conditions)
    task.owner = agent_name
    task.status = "in_progress"
```

IDLE cycle: teammates poll every 5s for up to 60s looking for unclaimed work. Identity re-injection ensures the agent remembers who it is after context compression.

### s12 — Worktree Isolation

*"Each works in its own directory, no interference."*

`WorktreeManager` creates git worktrees (isolated directory copies of the repo), one per task:

```
.worktrees/
├── index.json           # {name, path, branch, task_id, status}
├── auth-refactor/       # git worktree for task_1
├── api-endpoints/       # git worktree for task_2
└── test-suite/          # git worktree for task_3
```

Tasks bind to worktrees: `task_1 → worktree auth-refactor`. Multiple teammates can execute in parallel without file conflicts. `EventBus` provides append-only JSONL lifecycle events for visibility.

## 2 The Capstone: s_full.py

`s_full.py` (~1200 lines) combines mechanisms from s01-s11 into one runnable agent. It's NOT a teaching session — it's the reference implementation showing how everything integrates:

```
Before each LLM call:
  1. micro_compact()          — s06 Layer 1
  2. drain background queue   — s08
  3. check inbox              — s09
  4. inject notifications     — system message

Tool dispatch: 25+ tools across all mechanisms

REPL commands: /compact, /tasks, /team, /inbox
```

## 3 The Web Platform

The repo includes a **Next.js interactive learning app** (`/web/`) with:

| Page | Purpose |
|------|---------|
| **Home** | Hero + learning path overview with 5 color-coded layers |
| **Timeline** (`/timeline`) | Visual progression through all 12 sessions |
| **Session Viewer** (`/s01`...`/s12`) | Source code with syntax highlighting + annotations |
| **Diff View** (`/s02/diff`) | Side-by-side diff between adjacent sessions |
| **Compare** (`/compare`) | Compare any two sessions |
| **Layers** (`/layers`) | Architecture layers breakdown |

Tech stack: Next.js 16 + React 19 + Tailwind CSS v4 + Framer Motion. Supports **three languages** (English, Chinese, Japanese) via `[locale]` routing.

The `scripts/extract-content.ts` pre-build step extracts Python source code into structured JSON for the web viewer — keeping the web app in sync with the agent code.

## 4 Skills System

On-demand knowledge modules in `/skills/`:

| Skill | Purpose |
|-------|---------|
| `agent-builder` | How to design agents for any domain (with reference code) |
| `code-review` | Code review checklists and criteria |
| `pdf` | PDF processing workflows |
| `mcp-builder` | Building MCP servers for agent capabilities |

Each skill has a `SKILL.md` with YAML frontmatter (name, description, tags) and reference files. The agent loads them via `load_skill("agent-builder")` when needed (s05 pattern).

## 5 Architecture Mental Model

The 12 sessions map to a layered architecture:

```
┌─────────────────────────────────────────────┐
│  Layer 5: Collaboration                      │
│  [s09 Teams] [s10 Protocols] [s11 Autonomy] │
│  [s12 Worktree Isolation]                    │
├─────────────────────────────────────────────┤
│  Layer 4: Concurrency                        │
│  [s08 Background Tasks]                      │
├─────────────────────────────────────────────┤
│  Layer 3: Memory                             │
│  [s06 Three-Layer Compaction]                │
├─────────────────────────────────────────────┤
│  Layer 2: Planning & Coordination            │
│  [s03 TodoWrite] [s04 Subagents]            │
│  [s05 Skills]    [s07 Task System]           │
├─────────────────────────────────────────────┤
│  Layer 1: Tools & Execution                  │
│  [s01 Agent Loop] [s02 Tool Dispatch]        │
└─────────────────────────────────────────────┘
```

Each layer is independent — you can use s01-s06 without ever touching teams. But when you need multi-agent, s09-s12 build cleanly on top.

## 6 Key Patterns

**Pattern 1 — The Universal Agent Loop** (every session):
```python
while stop_reason == "tool_use":
    response = LLM(messages, tools)
    for tool_call in response:
        result = dispatch[tool_call.name](**tool_call.input)
        messages.append(tool_result(result))
```

**Pattern 2 — File-Based State** (s07, s09, s11, s12):
Tasks, inboxes, worktree index — all persisted as JSON/JSONL files. Survives context compression, process restarts, and agent replacement.

**Pattern 3 — Request-ID Correlation** (s10):
Every cross-agent handshake uses `{request_id, type, payload}`. Response matches `request_id`. One pattern for shutdown, plan approval, and any future protocol.

**Pattern 4 — Identity Re-injection** (s11):
After context compression, the agent might forget who it is. `make_identity_block(name, role)` re-injects identity as the first message. Agent stays coherent across compressions.

**Pattern 5 — Layered Injection** (s05, s06):
Cheap metadata always present → expensive content loaded on demand. Applies to both skills (s05) and context management (s06).

## 7 Running It

```bash
git clone https://github.com/anthropics/learn-claude-code
cd learn-claude-code
pip install -r requirements.txt  # anthropic>=0.25, python-dotenv

# Set API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-xxx, MODEL_ID=claude-sonnet-4-6

# Run any session
python agents/s01_agent_loop.py    # Minimal agent
python agents/s09_agent_teams.py   # Multi-agent team
python agents/s_full.py            # Everything combined

# Web learning platform
cd web && npm install && npm run dev
# Open http://localhost:3000
```

Supports multiple providers via `ANTHROPIC_BASE_URL`:
- Anthropic Claude (default)
- MiniMax-M2.5 (80.2% SWE-bench)
- GLM-5 by Zhipu (77.8%)
- Kimi-k2.5 by Moonshot (76.8%)
- DeepSeek-chat (73.0%)

## 8 Takeaway

This repo proves that an AI coding agent is not magic — it's a **well-designed harness**. The 12 sessions show that:

1. **The core is trivial**: a while loop + tool dispatch (~50 lines)
2. **Planning gives direction**: TodoWrite + subagents prevent drift
3. **Memory enables persistence**: compaction + file-based tasks survive any context limit
4. **Teams enable scale**: persistent agents + message bus + protocols
5. **Autonomy emerges**: task board polling + self-claim = agents that find their own work

The model provides intelligence. The harness provides opportunity. Build great harnesses.
