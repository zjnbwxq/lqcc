# LQCC 使用说明

## 基本流程

```text
1. 创建或直接 build 一个 .capsule
2. 写入或导入对话
3. 搜索历史决定、任务、偏好和证据
4. 生成新对话恢复包
5. 把恢复包复制给任意 AI
```

## 从聊天记录直接创建

```bash
lqcc build chat.md -o project.capsule --title "我的项目"
```

支持 JSON、JSONL、Markdown、普通文本。

## 创建空 capsule

```bash
lqcc create project.capsule --title "我的项目"
```

## 追加一轮对话

```bash
lqcc append project.capsule --role user --text "必须保存完整历史。"
```

## 导入 JSONL

```bash
lqcc import-jsonl project.capsule chat.jsonl
```

JSONL 格式：

```json
{"role":"user","content":"message text"}
```

## 导入 Markdown / 普通文本

```bash
lqcc import-chat project.capsule chat.md
```

`import-file` 也可以用，是 `import-chat` 的别名。

## 搜索

```bash
lqcc search project.capsule "LQCC"
```

## 生成恢复包

```bash
lqcc resume project.capsule --task "继续工作" --budget 800
```

输出内容可以直接复制到新的 ChatGPT、Claude、Codex 或 Cursor 对话。

## 导出完整历史

```bash
lqcc export project.capsule full-history.md
```

## 校验

```bash
lqcc verify project.capsule
```
