# LQCC Reader Skill 0.7.1

当项目提供 LQCC `.capsule` 文件或本地 LQCC daemon 时，使用这个 skill。

## 目标

保持活跃上下文很小。不要一开始就要求用户粘贴完整聊天历史。

## 推荐读取顺序

1. 先用 `lqcc resume <capsule> --task "<当前任务>" --budget 800`。
2. 如果信息不够，再用 `lqcc search <capsule> "<查询>"`。
3. 如果需要精确证据，再用 `lqcc get <capsule> E#`、`T#` 或 `A#`。
4. 只有 capsule 信息不够时，才要求完整导出。

## 写回 capsule

如果本地工具可用，把重要的可见更新写回 capsule：

```bash
lqcc append project.capsule --role assistant --text "Decision: ..."
```

如果 daemon 正在运行，使用：

```text
POST /append
POST /append-many
```

不要保存隐藏 chain-of-thought。只保存可见的决定、要求、任务、警告、产物和最终工作痕迹。

## 本地 daemon

如果用户说 daemon 正在运行，优先使用 HTTP 接口：

```text
POST /resume
POST /search
POST /get
POST /append
```

## 原则

只检索当前任务需要的内容。
