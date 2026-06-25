# LQCC 0.7.1 使用说明

## 一键使用

```bash
lqcc quick chat.md
```

这个命令会创建 `.capsule`，导入聊天，并打印可以复制到新 AI 对话里的恢复包。

## 终端菜单

```bash
lqcc
```

或者：

```bash
lqcc menu
```

适合不想记命令的用户。

## 手动流程

```bash
lqcc build chat.md -o project.capsule --title "Project"
lqcc search project.capsule "我们决定了什么？"
lqcc resume project.capsule --task "继续这个项目" --budget 800
lqcc verify project.capsule
```

## 自动写入：daemon

```bash
lqcc daemon project.capsule --port 8765
```

常用接口：

```text
POST /append
POST /append-many
POST /resume
POST /search
POST /get
```

示例：

```bash
curl -X POST http://127.0.0.1:8765/append \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Decision: active context must stay small."}'
```

## 自动记录 API 对话：proxy

```bash
export OPENAI_API_KEY="your-key"
lqcc proxy project.capsule \
  --upstream https://api.openai.com/v1/chat/completions \
  --context-mode auto \
  --port 8765
```

然后把兼容 OpenAI API 的客户端 endpoint 改成：

```text
http://127.0.0.1:8765/v1/chat/completions
```

模式：

```text
pass    记录，但原样转发
resume  用 capsule 恢复包 + 最近消息转发
auto    请求变长后自动切到 resume
```

0.7.1 暂不支持流式 proxy。

## 命令输出记录：wrap

```bash
lqcc wrap project.capsule -- python -m pytest
```

它会把命令、退出码、stdout、stderr 写入 capsule。

## 限制

- 不支持隐藏 chain-of-thought
- 还没有浏览器插件
- 0.7.1 的 `.capsule` 格式还不是 1.0 稳定格式
