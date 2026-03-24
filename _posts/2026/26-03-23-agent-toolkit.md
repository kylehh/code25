---
title: "NVIDIA Agent Toolkit vs OpenClaw: Building Agents"
mathjax: true
toc: true
categories:
  - Study
tags:
  - LLM
  - Agent
---

After GTC 2026, I did a deep dive into how NVIDIA Agent Toolkit (NAT) and OpenClaw each approach agent creation. NAT is declarative (YAML-driven), while OpenClaw is composable (Plugin + Skill + Agent config). NemoClaw bridges both as an OpenClaw plugin that orchestrates NAT workflows inside OpenShell sandboxes.

## 1 NVIDIA Agent Toolkit (NAT)

NAT uses **YAML configuration** to define agents. Three building blocks: **LLM**, **Functions** (tools), and **Workflow** (agent type).

### 1.1 ReAct Agent Example

```yaml
# config.yml
llms:
  nim_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    temperature: 0.0

functions:
  wikipedia_search:
    _type: wiki_search
    max_results: 3

workflow:
  _type: react_agent
  tool_names: [wikipedia_search]
  llm_name: nim_llm
  verbose: true
```

Run it:
```bash
pip install nvidia-nat
nat run --config config.yml
```

### 1.2 How Functions Are Defined

The YAML `_type: wiki_search` is just a reference. The actual implementation lives in Python with a **two-layer design**: user config params (YAML) vs LLM runtime params (function signature).

```python
# 1. Config class — maps to YAML parameters
class WikiSearchToolConfig(FunctionBaseConfig, name="wiki_search"):
    """Tool that retrieves relevant contexts from wikipedia search."""
    max_results: int = 2   # ← YAML `max_results: 3` maps here

# 2. Register with decorator, binding config type + framework
@register_function(
    config_type=WikiSearchToolConfig,
    framework_wrappers=[LLMFrameworkEnum.LANGCHAIN]
)
async def wiki_search(tool_config: WikiSearchToolConfig, builder: Builder):
    from langchain_community.document_loaders import WikipediaLoader

    # 3. The actual tool function — this is what the LLM calls
    async def _wiki_search(question: str) -> str:
        search_docs = await WikipediaLoader(
            query=question,
            load_max_docs=tool_config.max_results
        ).aload()
        return "\n\n---\n\n".join([
            f'<Document source="{doc.metadata["source"]}" '
            f'page="{doc.metadata.get("page", "")}"/>\n'
            f'{doc.page_content}\n</Document>'
            for doc in search_docs
        ])

    # 4. Wrap with FunctionInfo — extracts signature for LLM tool schema
    yield FunctionInfo.from_fn(
        _wiki_search,
        description="This tool retrieves relevant contexts from wikipedia search...",
    )
```

Key design: NAT separates **user configuration** (YAML → `FunctionBaseConfig`) from **LLM runtime parameters** (function signature → `FunctionInfo.from_fn()`).

| Layer | Source | Example |
|-------|--------|---------|
| User config params | YAML `max_results: 3` → `WikiSearchToolConfig` | Controls search depth |
| LLM runtime params | Function signature `question: str` → auto-extracted by `FunctionInfo` | LLM passes at inference time |
| Return value | `str` — formatted XML document snippets | Fed back into ReAct loop |

### 1.3 Supported Agent Types

| Type | Description |
|------|-------------|
| `react_agent` | ReAct loop: Reason → Act → Observe |
| `tool_calling` | Direct function calling via LLM |
| `router` | Routes to sub-agents based on intent |
| `reasoning` | Chain-of-thought before acting |
| `rewoo` | Plan all steps first, then execute |
| `mixture_of_agents` | Multiple agents collaborate |

### 1.4 Architecture

NAT's core is a **type registry** system. Every component (LLM, function, agent, evaluator) registers via:

```python
# register_workflow.py
register_llm_client()      # LLM providers
register_function()         # Tools
register_agent()            # Agent workflows
register_telemetry_exporter()
register_auth_provider()
```

Agent base class:
```python
class AgentBaseConfig(FunctionBaseConfig):
    workflow_alias: str | None
    llm_name: LLMRef
    verbose: bool
    description: str
```

## 2 OpenClaw Agent System

OpenClaw uses a **three-layer architecture**:

| Layer | Purpose | Format |
|-------|---------|--------|
| **Skill** | Describe tool capabilities (documentation) | Markdown `SKILL.md` |
| **Plugin** | Register executable tools at runtime | TypeScript `index.ts` |
| **Agent** | Configure AI instance with tools/skills | JSON `openclaw.json` |

### 2.1 Creating a Skill (Simplest)

A Skill is a markdown file that tells the agent how to use external tools:

```markdown
# skills/wiki-search/SKILL.md
---
name: wiki-search
description: Search Wikipedia for information
metadata:
  { "openclaw": { "emoji": "📖" } }
---

# Wikipedia Search
Use this skill to search Wikipedia articles...
```

Skills are **documentation-driven** — they inject context into the agent's prompt. No executable code needed.

### 2.2 Creating a Plugin (Executable Tool)

When you need actual tool execution, create a Plugin:

```
extensions/wiki-search/
├── package.json
├── openclaw.plugin.json
└── index.ts
```

**openclaw.plugin.json:**
```json
{
  "id": "wiki-search",
  "name": "Wikipedia Search",
  "description": "Search Wikipedia articles"
}
```

**index.ts:**
```typescript
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

export default {
  id: "wiki-search",
  register(api: OpenClawPluginApi) {
    api.registerTool(
      (ctx) => ({
        name: "wiki_search",
        description: "Search Wikipedia",
        input: {
          type: "object" as const,
          properties: {
            query: { type: "string", description: "Search query" },
          },
          required: ["query"],
        },
        async execute(input: { query: string }) {
          const resp = await fetch(
            `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(input.query)}&limit=3&format=json`
          );
          return { results: await resp.json() };
        },
      }),
      { names: ["wiki_search"] }
    );
  },
};
```

Plugin API provides multiple registration methods:

```typescript
api.registerTool(factory, { names })      // Agent tools
api.registerChannel({ plugin })           // Messaging channels
api.registerHook(events, handler)         // Lifecycle hooks
api.registerProvider(provider)            // Auth providers
api.registerService(service)              // Background services
api.registerCli({ register })            // CLI commands
api.registerHttpHandler(handler)          // HTTP endpoints
api.registerGatewayMethod(name, handler)  // Gateway methods
```

### 2.3 Configuring an Agent

Wire skills and plugins together in `openclaw.json`:

```json
{
  "agents": {
    "list": [
      {
        "id": "research-agent",
        "workspace": "~/.openclaw/workspace",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "skills": ["wiki-search", "github"],
        "tools": { "allow": ["wiki_search", "bash"] }
      }
    ]
  },
  "plugins": {
    "entries": {
      "wiki-search": { "enabled": true }
    }
  }
}
```

Each agent's workspace contains identity files:
- `SOUL.md` — Agent identity and tone
- `USER.md` — User profile
- `AGENTS.md` — Instructions and skill roster
- `memory/` — Persistent memory

## 3 NemoClaw: The Bridge

NemoClaw connects NAT and OpenClaw. It is itself an **OpenClaw Plugin** that:

1. Registers as a plugin via `api.registerCommand()` and `api.registerProvider()`
2. Uses a **Blueprint** (`blueprint.yaml`) to define sandbox + inference config
3. Deploys OpenClaw inside **OpenShell** sandboxes with security policies

**blueprint.yaml:**
```yaml
version: "0.1.0"
profiles: [default, ncp, nim-local, vllm]

components:
  sandbox:
    image: "ghcr.io/nvidia/openshell-community/sandboxes/openclaw:latest"
  inference:
    profiles:
      default:
        provider_type: "nvidia"
        endpoint: "https://integrate.api.nvidia.com/v1"
        model: "nvidia/nemotron-3-super-120b-a12b"
```

**NemoClaw Plugin entry (TypeScript):**
```typescript
export default function register(api: OpenClawPluginApi): void {
  api.registerCommand({
    name: "nemoclaw",
    description: "NemoClaw sandbox management",
    handler: (ctx) => handleSlashCommand(ctx, api),
  });
  api.registerProvider(registeredProviderForConfig(...));
}
```

**Blueprint Runner (Python)** orchestrates the lifecycle:
```python
# runner.py actions: plan, apply, status, rollback
def load_blueprint() -> dict:
    bp_file = Path(os.environ.get("NEMOCLAW_BLUEPRINT_PATH", ".")) / "blueprint.yaml"
    return yaml.safe_load(bp_file)
```

## 4 Side-by-Side Comparison

| Dimension | NAT | OpenClaw |
|-----------|-----|----------|
| **Definition** | YAML config + Python | TypeScript plugin + JSON config |
| **Tool Registration** | `functions:` in YAML | `api.registerTool()` in TS |
| **Agent Types** | 6 built-in (ReAct, Router, etc.) | Generic agent, composed via Skills/Tools |
| **LLM Config** | `llms:` block, NIM endpoint | `model:` in agent config |
| **Deployment** | `nat run` or NemoClaw blueprint | OpenClaw server + plugin loader |
| **Sandbox** | Via NemoClaw + OpenShell | Native `sandboxed` flag |
| **Extensibility** | Register new `_type` in registry | Plugin API with 8+ register methods |
| **State/Memory** | External (configurable) | Built-in workspace memory system |

## 5 Key Takeaway

- **NAT is declarative** — define *what* agent type and *which* tools in YAML, the framework handles orchestration.
- **OpenClaw is composable** — register tools via plugins, describe capabilities via skills, configure agents via JSON. More flexible but more assembly required.
- **NemoClaw** glues them together: OpenClaw agent UX + NAT inference optimization + OpenShell security sandbox. This is the NVIDIA reference stack for enterprise agent deployment.
