# LQCC 胶囊读取 Skill

当用户提供 `.capsule` 文件，或者说项目上下文存放在 LQCC 中时，使用这个 skill。

## 目标

只读取当前任务需要的上下文。不要要求用户粘贴完整聊天历史。

## 步骤

1. 先生成恢复包：

```bash
lqcc resume <capsule> --task "<当前任务>" --budget 800
```

2. 把返回内容作为当前回答的工作上下文。

3. 如果缺少某个具体决定、文件或证据，再搜索：

```bash
lqcc search <capsule> "<问题>" --limit 8
```

4. 如果需要精确证据，读取指定记录：

```bash
lqcc get <capsule> E12
lqcc get <capsule> T40
lqcc get <capsule> A3
```

5. 产生新的有用可见上下文后，追加写入：

```bash
lqcc append <capsule> --role user --text "..."
lqcc append <capsule> --role assistant --text "..."
```

## 规则

- 先用 `resume`，再考虑 `search`。
- 优先使用字典词条，再读取原文轮次。
- 只有需要精确证据时才读取 raw turn。
- 保持 active context 在指定预算内。
- 不要把 LQCC 当成普通总结器；它是可查询上下文字典。
