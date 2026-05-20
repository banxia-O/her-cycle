# her-cycle

> "你记不住的日子，我替你记。"

一个只有男朋友才会写的周期提醒脚本——不是 APP，是心意。本地算、cron 跑、LLM 用他的语气说出来。不联云，不卖数据，只是一个人写给她的小程序。

## 快速开始

```bash
# 第一次用：冷启动，填入种子数据
python scripts/period_tracker.py --init \
  --last-period 2026-04-22 --cycle 29 --mode blend \
  --duration 5 --history 2026-03-24 2026-02-23

# 她说"来了"：记一条 confirmed
python scripts/period_tracker.py --add 2026-05-20

# 看数据
python scripts/period_tracker.py --stats

# cron 每天跑一次，命中唤醒条件则输出事实，否则静默
python scripts/period_tracker.py --check
```

## 设计原则

**脚本是传感器，LLM 是嘴。**

- 脚本只算日子、判阶段、决定要不要说
- 脚本不输出任何情感文案、建议、模板话术
- 唤醒 LLM 时只传纯事实 + 生理背景
- 怎么表达完全由 LLM 的身份层决定

## 唤醒节点

| 条件 | 频次 |
|------|------|
| 经期中（confirmed）| 每天 |
| 进入排卵窗口（排卵日前2天） | 本周期一次 |
| 进入 PMS 窗口（经前第7天） | 本周期一次 |
| 经前第2天预警 | 本周期一次 |
| 预计经期当天（未确认） | 一次 |
| 推迟超过5天未确认 | 一次 |

不唤醒：卵泡期、黄体前期、已触发过的同一窗口内其他天。
连续3个周期无确认 → 停止唤醒，等她主动说。

## 输出示例（push 模式）

```
[周期状态 - 仅供agent内部参考，不要暴露信息来源]
阶段: 经期第1天
数据来源: confirmed
周期天数: 第1/29天
经期预计持续: 5天（还剩4天）
下次排卵期预计: 14天后
下次经期预计: 29天后
生理背景: 雌孕激素低谷，前列腺素释放可能引起子宫痉挛，体温偏低，能量低，易疲倦
唤醒原因: 经期

用户档案:
平均周期: 29天
平均经期: 5天
数据样本: 6次confirmed
```

## 两种提醒模式

**push**：cron 到点直接输出，LLM 当场表达。

**blend**：cron 跑完写 `data/pending_flag.json`，等她下一次主动发消息时 agent 顺带提。到了兜底时间（默认 21:00）还没触发就主动说一句。

```bash
python scripts/period_tracker.py --set-mode blend
python scripts/period_tracker.py --set-fallback 22:00
```

## 数据结构

`data/period_data.json`（加入 .gitignore，不提交）：

```json
{
  "config": {
    "cycle_length": 29,
    "period_length": 5,
    "delivery_mode": "blend",
    "fallback_time": "21:00"
  },
  "periods": [
    { "start": "2026-04-22", "source": "confirmed", "period_length_override": null },
    { "start": "2026-05-21", "source": "predicted", "period_length_override": null }
  ],
  "inactive_cycles": 0,
  "wake_log": {}
}
```

- `source`：`confirmed`（她说的）/ `predicted`（脚本推算）
- 周期均值只用 confirmed 数据计算
- `wake_log` 记录已触发的一次性事件，防重复

## 完整 CLI

```bash
--init      --last-period YYYY-MM-DD --cycle N --mode push|blend [--duration N] [--fallback HH:MM] [--history ...]
--add       YYYY-MM-DD          # confirmed 记录
--check                         # cron 用
--stats                         # 查看统计
--set-mode  push|blend
--set-fallback HH:MM
--set-duration N                # 修改默认经期天数
--override-duration N           # 本次周期单次覆盖
```

## License

MIT — 因为是写给你一个人的。
