---
title: "Nanobot, OpenClaw, and NAT: Three Agent Frameworks, One MCP Bridge"
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
  - Agent
  - Architecture
  - MCP
---

A deep-dive into three agent frameworks — **Nanobot** (ultra-lightweight Python), **OpenClaw** (full-featured TypeScript), and **NVIDIA Agent Toolkit** (enterprise YAML-driven) — and how MCP protocol unifies them into a composable agent ecosystem.

## 1 The Three Frameworks at a Glance

| Dimension | Nanobot | OpenClaw | NAT |
|-----------|---------|----------|-----|
| **Language** | Python | TypeScript (Node.js) | Python (monorepo, 35+ packages) |
| **Positioning** | Ultra-lightweight personal AI assistant | Full-featured personal AI platform | Enterprise agent dev/deploy/optimize framework |
| **Lines of Code** | ~4,000 core | Large monorepo, 55+ skills | 35+ packages, enterprise-scale |
| **Config Format** | JSON | JSON/YAML | YAML |
| **Default Model** | Any (via LiteLLM) | Claude Opus 4.5 (200k ctx) | NVIDIA NIM (Nemotron) |
| **Channels** | 12+ (Telegram, Discord, WhatsApp...) | 12+ (same + Signal, iMessage, Teams) | CLI / FastAPI / FastMCP |
| **Tool System** | 10 built-in + MCP | 55+ skills + plugin SDK | Type registry + YAML config |
| **MCP Role** | Native MCP client | MCP via `mcporter` skill | MCP client + FastMCP server |
| **Security** | Optional workspace restriction | Docker + Landlock + seccomp sandbox | Via NemoClaw/OpenShell |
| **Deployment** | CLI / Gateway | CLI + macOS/iOS/Android apps + Docker | CLI / FastAPI / MCP server |

The relationship: **Nanobot is a 99%-lighter Python reimagining of OpenClaw**. NAT is orthogonal — it's about building, evaluating, and optimizing agent workflows, not about chat channels or user interfaces.

## 2 Nanobot: Ultra-Lightweight Agent in ~4000 Lines

### 2.1 Architecture

```
nanobot/
├── agent/           # Core agent logic
│   ├── loop.py      # Agent main loop (max 40 iterations)
│   ├── context.py   # System prompt builder
│   ├── memory.py    # Token-based memory consolidation
│   ├── subagent.py  # Background task execution
│   └── tools/       # Built-in tools + MCP integration
│       ├── base.py       # Tool interface (name, description, parameters, execute)
│       ├── registry.py   # Dynamic tool registry
│       ├── filesystem.py # read_file, write_file, edit_file, list_dir
│       ├── shell.py      # exec (with dangerous command blocking)
│       ├── web.py        # web_search, web_fetch
│       ├── message.py    # Send to chat channels
│       ├── spawn.py      # Background subagents
│       ├── cron.py       # Scheduled tasks
│       └── mcp.py        # MCP server integration
├── bus/             # Async message bus (inbound/outbound queues)
├── channels/        # 12+ chat channel adapters
├── providers/       # 27+ LLM providers via LiteLLM
├── session/         # JSONL-based session persistence
├── config/          # Pydantic config schema
└── cli/             # CLI commands (agent, gateway, onboard)
```

### 2.2 Execution Flow

```
User Message → Channel → MessageBus (inbound queue)
  → AgentLoop._dispatch() (per-session lock, cross-session concurrent)
    → Build context: [system_prompt + memory + history + message]
    → _run_agent_loop():
        1. Get tool definitions from ToolRegistry
        2. provider.chat() → LLM response
        3. If tool_calls: execute all concurrently → add results → loop
        4. If no tool_calls: break
    → Save session (append-only for cache efficiency)
    → Schedule memory consolidation if threshold exceeded
  → OutboundMessage → MessageBus → Channel → User
```

### 2.3 Key Design Decisions

- **Decoupled**: Channels, Bus, and Agent are independent async components
- **Append-only sessions**: Never truncate message history (LLM cache friendly)
- **Lazy MCP**: Connects to MCP servers on first message, not at startup
- **Token-based memory**: When context grows too large, LLM consolidates recent messages into `MEMORY.md` and `HISTORY.md`
- **Concurrent tool execution**: All tool calls in a single LLM response run via `asyncio.gather`

### 2.4 Tool Definition Pattern

Every tool inherits from the `Tool` base class with four properties:

```python
class Tool(ABC):
    @property
    def name(self) -> str: ...              # e.g. "read_file"
    @property
    def description(self) -> str: ...       # For LLM prompt
    @property
    def parameters(self) -> dict: ...       # JSON Schema
    async def execute(self, **kwargs) -> str: ...  # Implementation
```

Tools are registered in `ToolRegistry`, which handles schema generation (OpenAI format), parameter validation/casting, and concurrent execution.

## 3 OpenClaw: Full-Featured Personal AI Platform

### 3.1 Architecture

OpenClaw is the "big sibling" that Nanobot was inspired by. It adds:

| Feature | OpenClaw | Nanobot |
|---------|----------|---------|
| Native apps | macOS, iOS, Android | None |
| Plugin SDK | 8+ register methods (tool, channel, hook, service, CLI, HTTP...) | None |
| Skills | 55+ bundled (GitHub, coding-agent, canvas, mcporter...) | Skills loader (simpler) |
| Security | Docker + Landlock + seccomp via OpenShell | Optional workspace restriction |
| Agent types | Multi-agent + subagents + model fallback chains | Single agent + subagent |
| Memory | SQLite vector search + full transcripts | Token-based consolidation + JSONL |
| UI | Control UI + TUI + Canvas/A2UI | CLI + Markdown rendering |
| LLM fallback | Primary → fallback chain with auth profile rotation | Single provider |

### 3.2 Three-Layer Agent Definition

OpenClaw uses a composable architecture:

**Layer 1 — Skill** (documentation-driven):
```markdown
# skills/wiki-search/SKILL.md
---
name: wiki-search
description: Search Wikipedia for information
---
# Wikipedia Search
Use this skill to search Wikipedia articles...
```

**Layer 2 — Plugin** (executable tool):
```typescript
export default {
  id: "wiki-search",
  register(api: OpenClawPluginApi) {
    api.registerTool((ctx) => ({
      name: "wiki_search",
      description: "Search Wikipedia",
      input: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
      async execute(input) {
        const resp = await fetch(`https://en.wikipedia.org/w/api.php?...${input.query}`);
        return { results: await resp.json() };
      },
    }), { names: ["wiki_search"] });
  },
};
```

**Layer 3 — Agent config** (wiring):
```json
{
  "agents": { "list": [{
    "id": "research-agent",
    "model": "nvidia/nemotron-3-super-120b-a12b",
    "skills": ["wiki-search", "github"],
    "tools": { "allow": ["wiki_search", "bash"] }
  }]}
}
```

### 3.3 Execution Flow

```
Message → Channel Plugin → Gateway (WebSocket control plane)
  → Session Queue (per-session serialization)
    → runReplyAgent()
      → Resolve session metadata
      → Load transcript history
      → Build memory context (vector search)
      → runAgentTurnWithFallback()
        → Select model (primary or fallback chain)
        → runEmbeddedPiAgent()
          → Build system prompt (tools + skills + context)
          → pi-ai library (LLM call)
          → Tool call loop (execute → return → continue)
        → If model fails → try next fallback
      → Parse response, apply reply directives
      → Block streaming (chunked delivery to channel)
    → Persist transcript + update metadata
  → Channel sends response
```

### 3.4 ACP and MCP Support

- **ACP (Agent Communication Protocol)**: OpenClaw's own protocol for agent-to-agent communication (`/src/acp/`)
- **MCP**: Supported via the `mcporter` skill — bridges external MCP servers as OpenClaw tools
- **OpenAI-compatible API**: Optional `/v1/chat/completions` endpoint

## 4 NVIDIA Agent Toolkit (NAT): Enterprise Agent Framework

### 4.1 Architecture

NAT is a 35+ package monorepo focused on the full agent lifecycle:

```
packages/
├── nvidia_nat_core          # Core: builder, runner, config, tools, CLI
├── Framework Integrations:
│   ├── nvidia_nat_langchain     # LangChain/LangGraph
│   ├── nvidia_nat_llama_index   # LlamaIndex
│   ├── nvidia_nat_crewai        # CrewAI
│   └── nvidia_nat_adk           # Google ADK
├── Protocol:
│   ├── nvidia_nat_mcp           # MCP client
│   ├── nvidia_nat_fastmcp       # MCP server (FastMCP)
│   └── nvidia_nat_a2a           # Agent-to-Agent
├── Observability:
│   ├── nvidia_nat_opentelemetry
│   ├── nvidia_nat_profiler      # Token-level profiling
│   └── nvidia_nat_phoenix
├── Optimization:
│   ├── nvidia_nat_eval          # Evaluation
│   ├── nvidia_nat_config_optimizer  # Hyper-parameter tuning
│   ├── nvidia_nat_data_flywheel    # Trajectory collection
│   └── nvidia_nat_nemo_customizer  # Model fine-tuning
└── Infrastructure:
    ├── nvidia_nat_redis, nvidia_nat_s3, nvidia_nat_mysql
    └── nvidia_nat_rag, nvidia_nat_mem0ai
```

### 4.2 YAML-Driven Agent Definition

```yaml
# workflow.yml — a complete agent definition
llms:
  nim_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    temperature: 0.0
    max_tokens: 1024

function_groups:
  calculator:
    _type: calculator

functions:
  current_datetime:
    _type: current_datetime

workflow:
  _type: react_agent
  tool_names: [calculator, current_datetime]
  llm_name: nim_llm
  verbose: true
```

Everything is resolved via a **type registry** — `_type` maps to a registered Python class. New components are registered via entry points:

```python
@register_function(config_type=WikiSearchToolConfig, framework_wrappers=[...])
async def wiki_search(tool_config, builder):
    async def _search(question: str) -> str:
        ...
    yield FunctionInfo.from_fn(_search, description="...")
```

### 4.3 FastMCP Server — The Integration Key

The `nvidia_nat_fastmcp` package can expose any NAT workflow as an MCP server:

```bash
nat fastmcp server run --config_file workflow.yml
# Listening on http://localhost:9902/mcp (streamable-http)
```

Under the hood, `tool_converter.py` does:
1. Extract input schemas from NAT Functions/Workflows (Pydantic → JSON Schema)
2. Build dynamic Python function signatures from schema fields
3. Create async wrappers that invoke the workflow via `SessionManager`
4. Register with FastMCP via `mcp.tool(name=..., description=...)(wrapper)`

Supported transports: **streamable-http** (default, production), **SSE** (streaming).

### 4.4 What Makes NAT Different

NAT's unique value isn't just agent execution — it's the **full lifecycle**:

| Phase | NAT Capability |
|-------|---------------|
| **Build** | YAML config, 8+ framework integrations, type registry |
| **Deploy** | CLI, FastAPI (`/v1/chat/completions`), FastMCP server |
| **Observe** | OpenTelemetry tracing, token-level profiling, Phoenix/Weave |
| **Evaluate** | LLM-as-judge, regex match, semantic similarity, custom evaluators |
| **Optimize** | Prompt tuning (Optuna), config optimization, data flywheel |
| **Fine-tune** | DPO via OpenPipe, NeMo Customizer, trajectory-based RL |

Output format: **ATIF** (Agent Trajectory Interchange Format) — records every step, tool call, and metric for analysis and training.

## 5 Integration: The MCP Bridge

All three frameworks can work together via **MCP (Model Context Protocol)**. NAT acts as the "agent brain" publishing workflows as MCP tools, while Nanobot/OpenClaw act as the "user interface" layer.

### 5.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    NeMo Agent Toolkit (NAT)                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ YAML Config   │  │ ReAct/Router  │  │ Eval / Finetune  │  │
│  │ Workflows     │  │ Agent Logic   │  │ Data Flywheel    │  │
│  └──────┬───────┘  └──────┬────────┘  └──────────────────┘  │
│         │                 │                                   │
│    FastMCP Server     FastAPI Server                         │
│    :9902/mcp          :8000/v1/chat/completions              │
└─────────┬─────────────────┬──────────────────────────────────┘
          │  MCP Protocol   │  OpenAI-compatible API
          │                 │
    ┌─────┴──────┐    ┌────┴──────┐
    │            │    │           │
┌───▼────────┐ ┌▼────▼──────┐ ┌─▼──────────────┐
│  Nanobot   │ │  OpenClaw  │ │  NemoClaw      │
│  (轻量)    │ │  (全功能)   │ │  (安全沙盒)    │
│            │ │            │ │                │
│ MCP native │ │ mcporter   │ │ OpenClaw       │
│ client     │ │ skill      │ │ + OpenShell    │
│            │ │            │ │ + Nemotron     │
│ Python     │ │ TypeScript │ │ Container      │
│ 12+ 通道   │ │ 12+ 通道   │ │ 12+ 通道       │
│ 10 tools   │ │ 55+ skills │ │ 55+ skills     │
└────────────┘ └────────────┘ └────────────────┘
```

### 5.2 Nanobot + NAT (MCP Bridge)

**Step 1**: Start NAT FastMCP server:
```bash
nat fastmcp server run --config_file workflow.yml
# http://localhost:9902/mcp
```

**Step 2**: Configure nanobot's `config.json`:

```json
{
  "tools": {
    "mcpServers": {
      "nat-calculator": {
        "type": "streamableHttp",
        "url": "http://localhost:9902/mcp",
        "toolTimeout": 60
      }
    }
  }
}
```

Or use **stdio** transport (nanobot auto-launches NAT as subprocess):

```json
{
  "tools": {
    "mcpServers": {
      "nat-calculator": {
        "type": "stdio",
        "command": "nat",
        "args": ["fastmcp", "server", "run", "--config_file", "/path/to/workflow.yml"],
        "toolTimeout": 60
      }
    }
  }
}
```

**What happens automatically**:
1. Nanobot connects to NAT MCP server (lazy, on first message)
2. Calls `list_tools()` to discover available tools
3. Wraps each tool as `mcp_nat-calculator_<toolname>` via `MCPToolWrapper`
4. `_normalize_schema_for_openai()` converts MCP JSON Schema to OpenAI format
5. Tools registered in `ToolRegistry` — LLM can call them like any native tool

### 5.3 OpenClaw + NAT (mcporter Skill)

```bash
# In OpenClaw, add a NAT MCP server
mcporter add nat-agent --url http://localhost:9902/mcp --transport streamable-http

# List available tools
mcporter list

# Agent automatically discovers and uses NAT tools
```

### 5.4 NAT as a Complete Agent (Single Tool)

Instead of exposing individual NAT tools, expose the entire workflow as one tool:

```yaml
# NAT config — whole agent as a single MCP tool
general:
  front_end:
    _type: fastmcp
    port: 9902
    tool_names: [research_agent]

functions:
  research_agent:
    _type: react_agent
    tool_names: [wikipedia_search, web_fetch]
    llm_name: nim_llm
    description: "A research agent that searches Wikipedia and the web"

llms:
  nim_llm:
    _type: nim
    model_name: meta/llama-3.1-70b-instruct
```

Now Nanobot/OpenClaw sees a single `mcp_nat_research_agent` tool. When called, NAT runs the full ReAct loop internally.

### 5.5 Multiple NAT Agents in Parallel

```json
{
  "tools": {
    "mcpServers": {
      "nat-research": { "url": "http://localhost:9902/mcp", "toolTimeout": 120 },
      "nat-code":     { "url": "http://localhost:9903/mcp", "toolTimeout": 120 },
      "nat-data":     { "url": "http://localhost:9904/mcp", "toolTimeout": 120 }
    }
  }
}
```

The front-end LLM (Claude, GPT, etc.) orchestrates which NAT agent to call based on the user's intent.

## 6 Compatibility Matrix

| Aspect | Nanobot ↔ NAT | OpenClaw ↔ NAT |
|--------|---------------|----------------|
| **Transport** | stdio / sse / streamable-http | streamable-http via mcporter |
| **Tool Schema** | Auto-normalized (`_normalize_schema_for_openai`) | Plugin SDK handles conversion |
| **Tool Naming** | `mcp_<server>_<tool>` prefix | mcporter namespace |
| **Timeout** | `toolTimeout` config | mcporter config |
| **Error Handling** | Errors → string → LLM retries | Plugin error propagation |
| **Auth** | `headers` field for bearer tokens | mcporter auth management |
| **Filtering** | `enabledTools: ["tool1", "tool2"]` | mcporter `include` / tool overrides |

## 7 When to Use What

| Scenario | Recommended Stack |
|----------|-------------------|
| **Quick prototype / personal use** | **Nanobot + NAT** — simplest, Python full-stack, zero code changes |
| **Production / enterprise** | **OpenClaw + NAT** — full features + NAT eval/finetune pipeline |
| **Security-sensitive** | **NemoClaw + NAT** — sandbox isolation + NVIDIA models + optimization |
| **NAT agent dev/debug** | **NAT CLI** (`nat run`) — no frontend framework needed |
| **Multi-channel chat with smart tools** | **Nanobot/OpenClaw** frontend + NAT agent backend via MCP |
| **Continuous agent improvement** | **NAT** alone — eval → optimize → finetune → redeploy loop |

## 8 Key Takeaway

The **MCP protocol** is the glue. It decouples "where the user talks" (Nanobot, OpenClaw, NemoClaw) from "how the agent thinks" (NAT workflows). This means:

- **NAT agents can be developed, evaluated, and fine-tuned independently** — swap models, add tools, retrain — without touching the frontend.
- **Frontend frameworks stay lightweight** — they handle channels, UI, memory, and security, while NAT handles the heavy agent logic.
- **Zero code changes needed** — both sides already speak MCP. Just configure a URL.

The three frameworks form a spectrum: **Nanobot** (minimal, fast) → **OpenClaw** (full-featured) → **NemoClaw** (enterprise-secured), all plugging into **NAT** as the agent intelligence layer.
