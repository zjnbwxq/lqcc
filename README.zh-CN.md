# LQCC

**Lightweight Queryable Context Compression**，面向长期 AI 对话的轻量级可查询上下文压缩。

LQCC 把长对话保存在本地 `.capsule` 文件里，整理成一本可检索的上下文字典，然后为下一次 AI 对话生成一个很小的任务恢复包。

完整可见历史仍然本地保存；模型只拿当前任务需要的那一小部分上下文。

## 现在已经能做什么

- 单文件 `.capsule` 格式，运行时不依赖 SQLite。
- 本地 Python CLI。
- 导入 JSONL、JSON、Markdown、普通文本聊天记录。
- 持续追加新的对话轮次。
- 自动抽取上下文字典词条：`DECISION`、`REQUIREMENT`、`TASK`、`PREFERENCE`、`WARNING`、`FACT`、`TRACE`、`ARTIFACT`。
- 在 capsule 里搜索历史决定、任务、偏好和证据。
- 按 token 预算生成新对话恢复包。
- 添加 PDF、图片、文本、二进制文件等附件。
- 导出完整历史为 Markdown 或 JSONL。
- 校验 capsule 完整性。

LQCC 本地运行，不需要 API key。

## 安装

源码安装：

```bash
python -m pip install -e .
```

可选多模态依赖：

```bash
python -m pip install -e '.[multimodal]'
```

基础 CLI 只依赖 Python 标准库。可选依赖用于更好的压缩和文件 sidecar。

## 快速开始

创建 capsule：

```bash
lqcc create project.capsule --title "My project"
```

也可以从聊天记录直接生成：

```bash
lqcc build chat.md -o project.capsule --title "My project"
```

追加对话：

```bash
lqcc append project.capsule --role user --text "项目叫 LQCC。"
lqcc append project.capsule --role assistant --text "LQCC 把上下文保存在本地 .capsule 文件里。"
```

导入已有聊天记录：

```bash
lqcc import-chat project.capsule chat.md
```

搜索上下文字典：

```bash
lqcc search project.capsule "我们为什么不用 SQL？"
```

生成新对话恢复包：

```bash
lqcc resume project.capsule \
  --task "继续实现 Python CLI" \
  --budget 800
```

添加附件：

```bash
lqcc attach project.capsule paper.pdf
lqcc attach project.capsule screenshot.png
```

导出完整历史：

```bash
lqcc export project.capsule full-history.md
```

校验文件：

```bash
lqcc verify project.capsule
```

## 输入格式

### JSONL

```jsonl
{"role":"user","content":"我们需要一本可查询的上下文字典。"}
{"role":"assistant","content":"完整原文仍然无损保存。"}
```

```bash
lqcc import-jsonl project.capsule chat.jsonl
```

### JSON

支持消息列表，或包含 `messages` 字段的对象：

```json
[
  {"role": "user", "content": "项目叫 LQCC。"},
  {"role": "assistant", "content": "已记录。"}
]
```

```bash
lqcc import-chat project.capsule chat.json --format json
```

### Markdown / 普通文本

```text
User: 项目叫 LQCC。
Assistant: LQCC 把上下文保存在 .capsule 文件里。
```

```bash
lqcc import-chat project.capsule chat.md
```

如果文本没有角色标记，默认会作为一个 `user` turn 导入，也可以用 `--default-role` 修改。

## 核心命令

```text
lqcc build               从聊天记录直接创建 .capsule
lqcc create              创建空的 .capsule
lqcc append              追加一轮可见对话
lqcc import-jsonl        导入 JSONL 消息
lqcc import-chat         导入 JSON、JSONL、Markdown 或普通文本
lqcc search              搜索词条、附件和原文证据
lqcc resume              为新 AI 对话生成小型恢复包
lqcc attach              添加文件附件和 sidecar 信息
lqcc get                 读取 E#、T#、A# 元数据/证据
lqcc extract-attachment  按 A# 恢复附件原始字节
lqcc add-entry           手动添加或修正权威词条
lqcc new-session         在同一个 capsule 中开启新会话分支
lqcc export              导出完整历史
lqcc inspect             查看存储和 token 统计
lqcc compact             重新打包并清理旧尾部索引
lqcc verify              校验索引、原文块、附件和 hash
```

## 平台支持

Python CLI 支持：

- Linux
- macOS Intel
- macOS Apple Silicon
- Windows

`.capsule` 文件本身跨平台。

## 当前限制

- 暂时不做浏览器插件。
- 不捕获隐藏 chain-of-thought，只保存可见对话和公开工作痕迹。
- 当前字典抽取是本地确定性规则，够用但不是最终版本。
- 多模态目前是原始文件保存 + 轻量 sidecar，更深入的图片/音频理解放在后续版本。

## 文档

- [CLI guide](docs/CLI.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Capsule format](docs/FORMAT.md)
- [Roadmap](ROADMAP.md)

## License

MIT.
