---
title: Nanobot 源码深度解析 - Agent 架构与运行机制
mathjax: true
toc: true
categories:
  - Study
tags:
  - Agent
  - LLM
  - Architecture
---

[Nanobot](https://github.com/HKUDS/nanobot) 是香港大学数据科学实验室 (HKU Data Science Lab) 发布的超轻量级 AI Agent 框架，核心代码仅约 4000 行。本文从源码角度深入分析其架构设计和运行机制。

## 0 整体架构

```
nanobot/
├── agent/           # 🧠 核心 agent 逻辑
│   ├── loop.py      # Agent 主循环
│   ├── context.py   # Prompt 构建器
│   ├── memory.py    # 持久化记忆
│   ├── skills.py    # Skills 加载器
│   ├── subagent.py  # 后台任务
│   └── tools/       # 内置工具
├── skills/          # 🎯 内置 skills
├── channels/        # 📱 聊天渠道 (Telegram, Discord...)
├── bus/             # 🚌 消息路由
├── providers/       # 🤖 LLM providers
└── session/         # 💬 会话管理
```

核心流程：
```
User Message → MessageBus → AgentLoop → ContextBuilder → LLM → Tool Execution → Response
```

## 1 MD 文件读取机制 (context.py)

### 1.1 Bootstrap Files 定义

```python
class ContextBuilder:
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
```

这四个文件在**每次构建 prompt 时**都会被读取。

### 1.2 System Prompt 构建流程

```python
def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
    parts = [self._get_identity()]  # 1. 基础身份

    bootstrap = self._load_bootstrap_files()  # 2. 读取 MD 文件
    if bootstrap:
        parts.append(bootstrap)

    memory = self.memory.get_memory_context()  # 3. 长期记忆
    if memory:
        parts.append(f"# Memory\n\n{memory}")

    always_skills = self.skills.get_always_skills()  # 4. always=true 的 skills
    if always_skills:
        always_content = self.skills.load_skills_for_context(always_skills)
        parts.append(f"# Active Skills\n\n{always_content}")

    skills_summary = self.skills.build_skills_summary()  # 5. Skills 列表
    if skills_summary:
        parts.append(f"# Skills\n\n{skills_summary}")

    return "\n\n---\n\n".join(parts)
```

### 1.3 读取时机总结

| 文件 | 读取时机 | 加载方式 |
|------|----------|----------|
| `SOUL.md` | 每次 prompt 构建 | 完整加载到 system prompt |
| `USER.md` | 每次 prompt 构建 | 完整加载到 system prompt |
| `AGENTS.md` | 每次 prompt 构建 | 完整加载到 system prompt |
| `TOOLS.md` | 每次 prompt 构建 | 完整加载到 system prompt |
| `MEMORY.md` | 每次 prompt 构建 | 完整加载到 system prompt |
| `HISTORY.md` | **不自动加载** | 需要 grep 搜索 |
| `SKILL.md` | 启动时扫描 | 按需读取（read_file） |

## 2 Agent Loop 核心逻辑 (loop.py)

### 2.1 主循环

```python
async def run(self) -> None:
    self._running = True
    await self._connect_mcp()  # 连接 MCP servers
    
    while self._running:
        msg = await self.bus.consume_inbound()  # 等待消息
        
        if msg.content.strip().lower() == "/stop":
            await self._handle_stop(msg)
        else:
            task = asyncio.create_task(self._dispatch(msg))
```

### 2.2 消息处理流程

```python
async def _process_message(self, msg: InboundMessage, ...):
    # 1. 获取/创建 session
    session = self.sessions.get_or_create(msg.session_key)
    
    # 2. 设置 tool context (channel, chat_id)
    self._set_tool_context(msg.channel, msg.chat_id, ...)
    
    # 3. 获取历史消息
    history = session.get_history(max_messages=self.memory_window)
    
    # 4. 构建完整 messages
    initial_messages = self.context.build_messages(
        history=history,
        current_message=msg.content,
        media=msg.media,
        channel=msg.channel, 
        chat_id=msg.chat_id,
    )
    
    # 5. 运行 agent loop
    final_content, tools_used, all_msgs = await self._run_agent_loop(
        initial_messages, on_progress=_bus_progress
    )
    
    # 6. 保存到 session
    self._save_turn(session, all_msgs, ...)
    self.sessions.save(session)
```

### 2.3 Tool 执行循环

```python
async def _run_agent_loop(self, initial_messages, on_progress=None):
    messages = initial_messages
    iteration = 0
    
    while iteration < self.max_iterations:  # 默认 40 次
        iteration += 1
        
        # 调用 LLM
        response = await self.provider.chat(
            messages=messages,
            tools=self.tools.get_definitions(),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        
        if response.has_tool_calls:
            # 执行所有 tool calls
            for tool_call in response.tool_calls:
                result = await self.tools.execute(
                    tool_call.name, 
                    tool_call.arguments
                )
                messages = self.context.add_tool_result(
                    messages, tool_call.id, tool_call.name, result
                )
        else:
            # 没有 tool call，返回最终结果
            final_content = response.content
            break
    
    return final_content, tools_used, messages
```

**关键点**：LLM 自己决定是否调用工具，nanobot 只负责执行和返回结果。

## 3 Skills 加载机制 (skills.py)

### 3.1 Skills 搜索顺序

```python
def list_skills(self, filter_unavailable: bool = True):
    skills = []
    
    # 1. Workspace skills (最高优先级)
    if self.workspace_skills.exists():
        for skill_dir in self.workspace_skills.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills.append({...})
    
    # 2. Built-in skills (不覆盖同名 workspace skill)
    if self.builtin_skills.exists():
        for skill_dir in self.builtin_skills.iterdir():
            if not any(s["name"] == skill_dir.name for s in skills):
                skills.append({...})
```

**优先级**：`workspace/skills/` > `nanobot/skills/` (内置)

### 3.2 依赖检查

```python
def _check_requirements(self, skill_meta: dict) -> bool:
    requires = skill_meta.get("requires", {})
    
    # 检查命令行工具
    for b in requires.get("bins", []):
        if not shutil.which(b):
            return False
    
    # 检查环境变量
    for env in requires.get("env", []):
        if not os.environ.get(env):
            return False
    
    return True
```

### 3.3 Always Skills

```python
def get_always_skills(self) -> list[str]:
    """获取 always=true 的 skills，自动加载到 context"""
    result = []
    for s in self.list_skills(filter_unavailable=True):
        meta = self.get_skill_metadata(s["name"])
        skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
        if skill_meta.get("always") or meta.get("always"):
            result.append(s["name"])
    return result
```

在 SKILL.md frontmatter 中设置 `always: true`，该 skill 会自动加载到每次对话的 context 中。

## 4 Memory 系统 (memory.py)

### 4.1 双层记忆架构

```python
class MemoryStore:
    def __init__(self, workspace: Path):
        self.memory_file = workspace / "memory" / "MEMORY.md"   # 长期记忆
        self.history_file = workspace / "memory" / "HISTORY.md"  # 事件日志
```

| 文件 | 用途 | 加载方式 |
|------|------|----------|
| `MEMORY.md` | 长期事实（偏好、项目上下文） | **每次加载到 context** |
| `HISTORY.md` | 事件日志（时间戳格式） | **不加载**，用 grep 搜索 |

### 4.2 自动整理机制

当 session 消息数超过 `memory_window`（默认 100）时，触发自动整理：

```python
# loop.py
unconsolidated = len(session.messages) - session.last_consolidated
if unconsolidated >= self.memory_window:
    asyncio.create_task(self._consolidate_memory(session))
```

### 4.3 整理过程（LLM 驱动）

```python
async def consolidate(self, session, provider, model, ...):
    # 1. 准备要整理的消息
    old_messages = session.messages[session.last_consolidated:-keep_count]
    
    # 2. 构建 prompt
    prompt = f"""Process this conversation and call save_memory tool.
    
## Current Long-term Memory
{current_memory}

## Conversation to Process
{conversation_lines}"""
    
    # 3. 调用 LLM，使用 save_memory tool
    response = await provider.chat(
        messages=[...],
        tools=_SAVE_MEMORY_TOOL,  # 特殊的整理工具
        model=model,
    )
    
    # 4. 解析结果并保存
    args = response.tool_calls[0].arguments
    self.append_history(args["history_entry"])      # 追加到 HISTORY.md
    self.write_long_term(args["memory_update"])     # 更新 MEMORY.md
```

**关键**：记忆整理本身也是 LLM 驱动的，通过 `save_memory` tool 返回结构化结果。

## 5 SOUL.md vs USER.md 优先级

从 `_load_bootstrap_files()` 可以看到加载顺序：

```python
BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
```

在 system prompt 中的位置：
```
1. Identity (nanobot 基础身份)
2. AGENTS.md (Agent 行为规则)
3. SOUL.md (AI 人格定义)
4. USER.md (用户偏好)
5. TOOLS.md (工具使用说明)
6. MEMORY.md (长期记忆)
7. Active Skills
8. Skills Summary
```

**LLM 通常更重视靠后的内容**，所以实际优先级：
```
USER.md > SOUL.md > AGENTS.md > Identity
```

但这不是绝对的，取决于具体指令的明确程度。

## 6 什么会触发文件更新？

| 触发条件 | 更新的文件 | 触发方式 |
|----------|-----------|----------|
| 用户说"记住这个" | `MEMORY.md` | LLM 调用 write_file/edit_file |
| 会话过长自动整理 | `HISTORY.md`, `MEMORY.md` | 后台 consolidate 任务 |
| 用户修改偏好 | `USER.md` | LLM 调用 edit_file |
| **SOUL.md** | **不会自动更新** | 需用户明确要求 |

## 7 Runtime Context 注入

每条用户消息前会注入运行时上下文：

```python
@staticmethod
def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    tz = time.strftime("%Z") or "UTC"
    lines = [f"Current Time: {now} ({tz})"]
    if channel and chat_id:
        lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
    return "[Runtime Context — metadata only, not instructions]\n" + "\n".join(lines)
```

这让 agent 知道当前时间和消息来源，但标记为 "metadata only" 防止被当作指令。

## 8 Key Takeaways

1. **Prompt 构建**：每次对话都重新读取所有 MD 文件，确保最新状态
2. **Skills 懒加载**：只加载 `always=true` 的 skills，其他按需读取
3. **Memory 双层**：MEMORY.md 始终加载，HISTORY.md 用 grep 搜索
4. **LLM 驱动**：工具调用、记忆整理都由 LLM 决定
5. **优先级**：USER.md > SOUL.md，但都不会自动更新
6. **Session 隔离**：每个 channel:chat_id 独立 session

整个设计非常简洁，核心就是：**构建 context → 调用 LLM → 执行 tools → 循环**。
