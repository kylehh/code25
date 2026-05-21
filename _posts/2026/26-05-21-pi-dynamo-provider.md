---
title: "pi-dynamo-provider: Wiring Pi Agents into Dynamo's Observability Stack"
mathjax: true
toc: true
categories:
  - Study
tags:
  - Agent
  - LLM
  - Dynamo
  - Observability
  - Tracing
---

[pi-dynamo-provider](https://github.com/NVIDIA-dev/pi-dynamo-provider) is a small (~650 LOC TypeScript) Pi extension that registers a `dynamo` model provider — letting Pi's agentic CLI run against an [NVIDIA Dynamo](https://github.com/ai-dynamo/dynamo) OpenAI-compatible endpoint, while teeing every LLM request and tool call into Dynamo's agent trace sink.

Core idea: **make a Pi agent run visible — and benchmarkable — inside Dynamo's tracing infrastructure, without patching either side's core.**

```
Harness boundary stays clean:
  Pi side                                Dynamo side
  ─────────────                          ──────────────
  ExtensionAPI only                      Public agent-trace surface
  No pi-mono patches                     No Pi-specific shims
            └──── pi-dynamo-provider ────┘
                  (this repo, ~650 lines)
```

## 0 Why This Bridge Exists

Pi is an agentic coding CLI that talks to LLMs and runs tools. Dynamo is an inference serving system with a built-in agent-trace sink, a Mooncake-replay benchmark harness, and Perfetto visualization. They were built independently, and the two halves of an agent task — *the reasoning trace* (LLM calls) and *the action trace* (tool executions) — live on opposite sides of the wire.

Without a bridge, a Dynamo trace shows isolated LLM requests with no idea they belong to the same agent task. With the bridge, **one Dynamo trace renders both LLM spans and Pi tool spans on the same trajectory** — joinable, replayable, profilable.

## 1 What's in the Repo

Three source files in `src/`:

| File | Responsibility |
|---|---|
| `index.ts` | Extension entrypoint. Calls `readDynamoConfig`, discovers models via `/v1/models`, registers the `dynamo` provider with Pi, wires the tool-event relay |
| `dynamo-provider.ts` | Builds `nvext.agent_context` from `DYN_AGENT_*` and `PI_SUBAGENT_*` env vars. Wraps `streamSimple` to inject metadata on every chat-completions request. Adds `x-request-id` if absent |
| `tool-relay.ts` | ZMQ PUSH publisher for Pi tool events. Connects to a Dynamo-bound PULL endpoint. Wire format: `[topic, seq_be_u64, msgpack(AgentTraceRecord)]` |

Plus three helper scripts:

- `scripts/install-dynamo.sh` — clones Dynamo, builds Python bindings, sets up a `uv` venv
- `scripts/launch-agg-agent.sh` — boots Dynamo frontend + one SGLang worker with agent tracing and ZMQ tool ingest enabled
- `scripts/integration-smoke.sh` — out-of-band end-to-end check; boots Dynamo + mocker, sends one real chat completion, asserts `nvext.agent_context` round-trips into the trace JSONL

That's it. The public API is a re-export of `dynamo-provider` and `tool-relay` from `index.ts` — no other surface.

## 2 The Two Channels

pi-dynamo-provider runs two independent data paths that converge in Dynamo's trace sink:

```
                  HTTP /v1/chat/completions
                  + nvext.agent_context (in request body)
  ┌──────┐        ───────────────────────────►  ┌────────────────────┐
  │  Pi  │ ── pi-dynamo-provider ──►            │   Dynamo frontend  │
  │      │                                      │   + worker         │
  │      │ ── tool_start/end/error ──►          │   (vLLM / SGLang)  │
  └──────┘        ───────────────────────────►  └─────────┬──────────┘
                  ZMQ PUSH (msgpack AgentTrace)           │
                  → Dynamo PULL ingest                    ▼
                                              agent trace JSONL
                                              (LLM + tool spans,
                                               joined by trajectory_id)
                                                          │
                                                          ▼
                                              Perfetto · Mooncake replay
                                              · benchmark harness
```

**Channel A — chat completions over HTTP.** Standard OpenAI-compatible POST, but the body carries an extra `nvext.agent_context` object that Dynamo records on `request_end`.

**Channel B — tool events over ZMQ PUSH.** Pi emits `tool_start` / `tool_end` / `tool_error` events to a Dynamo-bound PULL endpoint. The wire frame is three parts: a topic string, a big-endian 64-bit sequence number, and a msgpacked `AgentTraceRecord`.

Why ZMQ and not HTTP? Dynamo owns the bind side; multiple Pi processes, subagents, or tool workers can all `connect` as PUSH producers without competing for the local endpoint. Tool tracing is **best-effort, not durable** — the publisher's bounded queue drops events when full. This is correct: trace data must never back-pressure Pi.

## 3 The agent_context Schema

Every chat-completions request gets a payload like:

```json
{
  "nvext": {
    "agent_context": {
      "session_type_id": "pi_coding_agent",
      "session_id": "pi-demo-001",
      "trajectory_id": "<pi-session-id>",
      "parent_trajectory_id": "<optional-parent>",
      "phase": "reasoning"
    }
  }
}
```

These field names are not arbitrary — they match ATIF, the schema Dynamo's converter and benchmark stack join on. The `phase: "reasoning"` value tags the LLM call as an agent reasoning step (versus synthesis, grading, etc.); adding new phase values requires Dynamo-side coordination.

Existing `nvext` fields are preserved, and `x-request-id` is added only when the caller didn't already set one.

## 4 Subagent Trajectory Linking

The repo's most opinionated bit of logic lives in `dynamo-provider.ts`'s subagent bridge. The problem it solves:

When a tool like [`pi-subagents`](https://github.com/nicobailon/pi-subagents) spawns a child Pi process, the child inherits the parent's `process.env` — including `DYN_AGENT_TRAJECTORY_ID`. Without intervention, parent and child emit **identical** `trajectory_id` values, and the parent/child distinction collapses in the trace.

The bridge detects `PI_SUBAGENT_CHILD=1` and rewrites the agent context:

```text
parent process:                       trajectory_id = root-traj
                                      parent_trajectory_id = (unset)

pi-subagents spawns child with env:
  DYN_AGENT_TRAJECTORY_ID=root-traj   (inherited verbatim)
  PI_SUBAGENT_CHILD=1
  PI_SUBAGENT_RUN_ID=run-1
  PI_SUBAGENT_CHILD_AGENT=researcher
  PI_SUBAGENT_CHILD_INDEX=2

child after applySubagentBridge:
                                      trajectory_id = run-1:researcher:2
                                      parent_trajectory_id = root-traj
```

Three rules make this robust:

1. **Manual override always wins.** Setting `DYN_AGENT_PARENT_TRAJECTORY_ID` explicitly disables the bridge.
2. **One-way knowledge flow.** pi-dynamo-provider knows about `PI_SUBAGENT_*` env vars; pi-subagents has no idea this bridge exists. Don't propose pi-subagents changes for problems solvable here.
3. **process.env gets mutated.** Any subagents the child itself spawns inherit the corrected parent → child chain. Nested chains stay attributable instead of collapsing back to the root.

When `PI_SUBAGENT_CHILD` isn't set, this code path is inert.

## 5 Env-Var Naming Contract

The repo enforces a deliberately narrow env-var namespace policy:

| Prefix | Direction | Examples |
|---|---|---|
| `DYNAMO_*` | client config (we read) | `DYNAMO_BASE_URL`, `DYNAMO_API_KEY` |
| `DYN_AGENT_*` | dynamo agent context (we read + emit) | `DYN_AGENT_SESSION_ID`, `DYN_AGENT_TRAJECTORY_ID`, `DYN_AGENT_TOOL_EVENTS_ZMQ_ENDPOINT` |
| `PI_SUBAGENT_*` | pi-subagents bookkeeping (we read only) | `PI_SUBAGENT_CHILD`, `PI_SUBAGENT_RUN_ID`, `PI_SUBAGENT_CHILD_AGENT`, `PI_SUBAGENT_CHILD_INDEX` |
| `OPENAI_BASE_URL` | OpenAI-compatibility fallback | only consulted when `DYNAMO_BASE_URL` is unset |

No new prefixes. New variables must justify which existing namespace they belong in.

## 6 Architecture Invariants

The CLAUDE.md spells out four invariants that the codebase defends:

1. **One-way knowledge flow.** Bridge knowledge lives here, not in pi-subagents.
2. **No `pi-mono` core patches.** Everything goes through Pi's public `ExtensionAPI`. If you want a Pi core change, find a different angle here first.
3. **Dynamo owns the ZMQ bind side.** We're a PUSH connect-side producer. Don't try to bind.
4. **Trace data is best-effort.** No retry loops, no persistent queues, no back-pressure on Pi. Bounded-queue drops are correct.

These constraints are what keep the extension small and the integration robust across upstream churn on both sides.

## 7 Verifying the Effect

Four layers, from cheap to thorough:

### Layer 1 — Build & unit smoke

```bash
npm install
npm run check     # tsc strict + exactOptionalPropertyTypes + noUncheckedIndexedAccess
npm test          # vitest
npm run build
./scripts/integration-smoke.sh   # boots Dynamo + mocker, asserts agent_context round-trip
```

The integration smoke covers two cases: top-level `agent_context` and the pi-subagents bridge. Trace envelope assertions only — mocker output is intentionally garbage.

### Layer 2 — Real end-to-end trace inspection

```bash
./scripts/install-dynamo.sh
./scripts/launch-agg-agent.sh --gpu 0     # serves zai-org/GLM-4.7-Flash by default

# In another shell, use the env block the launcher prints:
export DYNAMO_BASE_URL=http://127.0.0.1:18083/v1
export DYNAMO_API_KEY=dummy
export DYN_AGENT_SESSION_TYPE_ID=pi_coding_agent
export DYN_AGENT_SESSION_ID=verify-001
export DYN_AGENT_TOOL_EVENTS_ZMQ_ENDPOINT=tcp://127.0.0.1:20390

pi --model dynamo/zai-org/GLM-4.7-Flash \
   -p "Run the tests in this folder, fix the smallest bug, and rerun the tests."
```

After it finishes, inspect the trace JSONL:

| Check | How | Pass criterion |
|---|---|---|
| LLM requests carry agent_context | `jq -r 'select(.event_type=="request_end")\|.agent_context' trace.jsonl` | Every record has `session_id=verify-001`, consistent `trajectory_id` |
| Tool events captured | `jq -r '.event_type' trace.jsonl \| sort \| uniq -c` | Both `request_end` and `tool_start`/`tool_end` present |
| Tool events share trajectory | join trajectory_id across both event types | Identical IDs |
| `x-request-id` preserved | grep `x_request_id` | Every `request_end` has one |
| Causal ordering | `tool_start` timestamps fall after the triggering LLM `request_end` | No tool-precedes-call inversions |

Then render in Perfetto:

```bash
cd $DYNAMO_DIR && source .venv/bin/activate
python benchmarks/agent_trace/convert_to_perfetto.py \
   trace.jsonl --include-markers --separate-stage-tracks \
   --output trace.perfetto.json
# Drop into https://ui.perfetto.dev/
```

Expected: `dynamo.llm` spans and `dynamo.agent.tool` spans nested on the same trajectory lane.

### Layer 3 — Negative paths (the extension stays inert when it should)

```bash
# Tool relay endpoint unset → events drop silently, no errors
unset DYN_AGENT_TOOL_EVENTS_ZMQ_ENDPOINT
pi --model dynamo/<model> -p "..."

# Dynamo unreachable → streamSimple fails cleanly, doesn't hang Pi
DYNAMO_BASE_URL=http://127.0.0.1:1 pi --model dynamo/default -p "ok"
```

Subagent bridge isolated test:

```bash
PI_SUBAGENT_CHILD=1 \
PI_SUBAGENT_RUN_ID=run-x \
PI_SUBAGENT_CHILD_AGENT=researcher \
PI_SUBAGENT_CHILD_INDEX=2 \
DYN_AGENT_TRAJECTORY_ID=root-traj \
pi --model dynamo/<model> -p "ok"
```

Expect `trajectory_id == "run-x:researcher:2"` and `parent_trajectory_id == "root-traj"` in the trace.

### Layer 4 — Overhead (optional)

Same prompt + seed, 30 runs each, compare:

- Tool relay off (unset `DYN_AGENT_TOOL_EVENTS_ZMQ_ENDPOINT`)
- Tool relay on

Measure Pi wall time and Dynamo-side TTFT / TPOT. ZMQ PUSH is non-blocking with a bounded queue; the expected gap is **< 1%**. If it's larger, suspect msgpack or serialization on the hot path.

## 8 Downstream: What the Trace Enables

Once the trace exists, it unlocks Dynamo's analysis surface — none of which lives in pi-dynamo-provider itself:

- **Perfetto visualization** — `benchmarks/agent_trace/convert_to_perfetto.py` for time-line debugging
- **Mooncake replay** — `cargo run -p dynamo-bench --bin agent_trace_to_mooncake` converts the trace to Mooncake-style JSONL with `hash_ids` for KV cache reuse simulation
- **`python -m dynamo.replay`** — replays the synthesized trace through Dynamo's mocker (offline) or live mock runtime (online) to benchmark scheduler/router/cache behavior under different worker counts, router modes, and arrival speedup ratios

The replay path is the one I'd reach for to do *parameter sweeps without burning real GPU hours* — but it depends entirely on pi-dynamo-provider being the trace producer upstream.

## 9 Takeaway

pi-dynamo-provider is a textbook case of a **good integration layer**:

1. **Tiny surface** (~650 LOC, three files, two re-exports).
2. **No upstream patches.** Everything expressible through Pi's `ExtensionAPI` and Dynamo's public trace sink. Neither side knows about the other.
3. **Two channels, one trace.** HTTP body annotations carry reasoning context; ZMQ PUSH carries action events. Both land in the same JSONL.
4. **Best-effort, never blocking.** Trace failures degrade silently. Pi is never held hostage by observability.
5. **Schema discipline.** ATIF field names are immovable because downstream tools join on them. The repo's CLAUDE.md is explicit about what to leave alone.

The lesson generalizes: when bridging two evolving systems, the integration layer's job isn't to add features — it's to *speak both dialects fluently while staying invisible to each*. That's what makes pi-dynamo-provider a 650-line repo instead of a 6,500-line one.
