---
title: Nanobot Agent Skills 实践
mathjax: true
toc: true
categories:
  - Application
tags:
  - Agent
  - Tools
---

最近在使用 [nanobot](https://github.com/hkust-nlp/nanobot) 这个 AI agent 框架（香港科技大学发布），记录一下 skill 系统的实践，包括创建翻译工具和本地网页服务。

## 0 Overview
- Nanobot 是一个轻量级 AI agent 框架
- Skill 系统让 agent 能力可扩展
- 每个 skill 是一个 `SKILL.md` 文件，定义工具的使用方法
- 可以调用外部 API 和本地命令

## 1 Skill 文件结构

Skill 文件位于 `workspace/skills/{skill-name}/SKILL.md`，包含：

```yaml
---
name: skill-name
description: What this skill does
metadata: {"nanobot":{"emoji":"🌐","requires":{"bins":["curl"]}}}
---
```

后面是 markdown 格式的使用说明，agent 会根据这些说明来调用工具。

## 2 Translate Skill

创建了一个翻译 skill，使用免费的 [MyMemory API](https://mymemory.translated.net/doc/spec.php)：

```bash
curl -s "https://api.mymemory.translated.net/get?q=Hello&langpair=en|zh"
```

### 回译验证
翻译成非英语时，自动回译验证翻译质量：
1. 中文 → 日语：「你真的太厉害了」→「あなたは本当に素晴らしいです」
2. 日语 → 中文：「あなたは本当に素晴らしいです」→「您果然是厉害！」

### TTS 语音朗读
使用 macOS 内置的 `say` 命令生成语音：

```bash
# 生成日语语音
say -v Kyoko "あなたは本当に素晴らしいです" -o output.aiff

# 转换为 m4a 格式
afconvert -f m4af -d aac output.aiff output.m4a
```

支持的语音：
| 语言 | 语音名称 |
|------|----------|
| 日语 | Kyoko |
| 中文 | Tingting |
| 韩语 | Yuna |
| 英语 | Samantha |

## 3 本地网页服务

用 Python 创建了一个翻译网页服务，运行在 `localhost:8080`：

```python
from http.server import HTTPServer, BaseHTTPRequestHandler

class TranslateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 返回 HTML 页面
        
    def do_POST(self):
        # 处理翻译请求，调用 MyMemory API
        # 处理语音请求，调用 say 命令
```

功能：
- 多语言翻译（中/英/日/韩/法/德/西）
- 自动回译验证
- 🔊 语音朗读按钮

### 踩坑记录
JavaScript 函数名不能用 `translate`，这是浏览器保留词（CSS transform 相关），会报错：
```
Uncaught TypeError: translate is not a function
```
改成 `doTranslate()` 就好了。

## 4 文件组织

```
workspace/
├── output/
│   ├── audio/translate/    # TTS 音频文件
│   └── web/                # 网页服务
├── skills/
│   ├── translate/SKILL.md
│   └── blog/SKILL.md
└── memory/
    ├── MEMORY.md           # 长期记忆
    └── HISTORY.md          # 对话历史
```

## Key Takeaways
- Skill 系统让 agent 能力模块化、可扩展
- 免费 API（MyMemory）足够个人使用
- macOS 内置 TTS 质量不错，支持多语言
- 简单的 Python HTTP server 就能做本地工具网页
