# LQCC 0.7.1

**Lightweight Queryable Context Compression** 是一个本地优先的 `.capsule` 上下文字典，用来解决长期 AI 对话的上下文膨胀问题。

LQCC 会把完整可见历史保存在本地，从中抽取可检索的上下文字典，并在下一次 AI 对话时只输出当前任务需要的小型恢复包。

## 0.7.1 已完成

- no-SQL packed `.capsule` 单文件格式
- Linux、Windows、macOS 都能用的 Python CLI
- 一键入门命令：`lqcc quick chat.md`
- 终端菜单：`lqcc` 或 `lqcc menu`
- 本地 HTTP daemon，用于自动写入和检索
- OpenAI-compatible 非流式 proxy，用于自动记录请求和回复
- 命令 wrapper，可以把命令输出写成 tool context
- 不读取完整历史即可 search / resume
- PDF、图片、文本、代码、二进制附件 sidecar
- 完整历史导出和 capsule 校验
- 给 Codex、Claude Code、Cursor 等 agent 使用的 reader skill

## 安装

测试版安装（TestPyPI）：

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple lqcc
```

源码安装：

从 TestPyPI 安装：

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple lqcc
```

从源码安装：

```bash
git clone https://github.com/zjnbwxq/lqcc.git
cd lqcc
python -m pip install -e ".[multimodal]"
```

检查：

```bash
lqcc --version
```

应该看到：

```text
lqcc 0.7.1
```

## 最快使用方式

```bash
lqcc quick examples/demo_chat.md
```

它会创建 `examples/demo_chat.capsule`，并直接打印一个可以复制到新 AI 对话里的小型恢复包。

## 普通手动流程

```bash
lqcc build chat.md -o project.capsule --title "My Project"
lqcc search project.capsule "我们决定了什么？"
lqcc resume project.capsule --task "继续这个项目" --budget 800
lqcc verify project.capsule
```

## 终端菜单

```bash
lqcc
```

或者：

```bash
lqcc menu
```

菜单可以完成 build、resume、search、append、attach、verify、启动 daemon、启动 proxy。

## 本地 daemon

当其他工具或 agent 需要自动写入和读取 capsule 时，用 daemon：

```bash
lqcc daemon project.capsule --port 8765
```

接口：

```text
GET  /health
GET  /stats
POST /append
POST /append-many
POST /resume
POST /search
POST /get
POST /attach
```

示例：

```bash
curl -X POST http://127.0.0.1:8765/append \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Decision: keep active context small."}'
```

## OpenAI-compatible proxy

当 API 客户端希望通过 LQCC 自动记录消息时，用 proxy：

```bash
export OPENAI_API_KEY="your-key"
lqcc proxy project.capsule \
  --upstream https://api.openai.com/v1/chat/completions \
  --context-mode auto \
  --port 8765
```

然后把客户端的 endpoint 指向：

```text
http://127.0.0.1:8765/v1/chat/completions
```

上下文模式：

```text
pass    只记录消息，原样转发请求
resume  用 capsule 恢复包 + 最近消息转发
auto    请求较小时 pass，请求变大后自动 resume
```

当前限制：0.7.1 暂不支持流式 proxy 响应。请使用非流式请求。

## 命令 wrapper

用 `wrap` 把命令输出记录为 tool context：

```bash
lqcc wrap project.capsule -- python -m pytest
```

它会记录命令开始、退出码、stdout、stderr。

## Agent reader skill

见：

```text
reader-skill/SKILL.md
reader-skill/SKILL.zh-CN.md
```

这个 skill 会告诉 agent：先用 `lqcc resume`，不够再用 `lqcc search` 或 `lqcc get`，不要让用户粘贴完整历史。

## 范围

LQCC 0.7.1 处理可见文本和文件产物。它不会保存隐藏 chain-of-thought。它还没有浏览器插件。浏览器支持、桌面 UI、更强多模态索引、稳定 v1.0 格式保证是后续路线图。

## License

MIT.
