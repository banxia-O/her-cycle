---
name: period-tracker
description: 生理周期追踪脚本。本地 JSON 存储，双轨数据（confirmed/predicted），阶段判断引擎，按需唤醒 agent。脚本只输出纯事实，表达由 agent 身份层负责。
version: 2.0.0
---

# Period Tracker v0.2

## 核心原则

脚本是传感器，LLM 是嘴。

- 脚本输出：当前阶段、周期天数、数据来源、生理背景——纯事实
- 脚本不输出：任何建议、安慰、提醒话术、情感文案
- 表达方式完全由 agent 的身份层决定

---

## 触发关键词

user 提到以下词时，引导使用本插件或执行相应命令：

月经 / 经期 / 姨妈 / 大姨妈 / 来了 / 周期 / 排卵 / PMS / 经前

---

## 数据模型

```json
{
  "config": {
    "cycle_length": 29,
    "period_length": 5,
    "seed_date": "2026-04-22",
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

- `source`：`confirmed`（user 主动告知）/ `predicted`（脚本推算）
- `period_length_override`：单次周期持续天数覆盖，null 则取 config 默认值
- `inactive_cycles`：连续 predicted 且未确认的周期数，≥3 时停止唤醒
- `wake_log`：记录已触发的一次性事件，防止同一窗口重复唤醒

---

## CLI 命令

```bash
# 冷启动（必填：--last-period、--cycle、--mode）
python scripts/period_tracker.py --init \
  --last-period 2026-04-22 --cycle 29 --mode blend \
  --duration 5 --fallback 21:00 \
  --history 2026-03-24 2026-02-23 2026-01-25

# 添加 confirmed 记录（user 告知"来了"或回溯补录）
python scripts/period_tracker.py --add 2026-05-20

# 每日 cron 检查（命中唤醒条件则输出，否则静默）
python scripts/period_tracker.py --check

# 查看统计
python scripts/period_tracker.py --stats

# 修改提醒方式
python scripts/period_tracker.py --set-mode push

# 修改兜底推送时间（仅 blend 模式）
python scripts/period_tracker.py --set-fallback 22:00

# 修改默认经期持续天数（影响全局）
python scripts/period_tracker.py --set-duration 4

# 修改当前周期持续天数（仅本次）
python scripts/period_tracker.py --override-duration 6

# 标记 blend flag 已送达（agent 发完消息后调用）
python scripts/period_tracker.py --mark-delivered
```

---

## 冷启动流程

插件未初始化时，引导 user 提供：

**必填**
- 上次月经第一天日期
- 平均周期天数
- 提醒方式：`push`（cron 到点输出）或 `blend`（等 user 发起对话时带出，兜底指定时间）

**可选**
- 经期持续天数（默认 5，合法范围 3-7）
- 近几个月的经期起始日期（样本越多预测越准）
- 兜底时间（仅 blend 模式，默认 21:00）

无种子数据时脚本不运行、不预测、不唤醒。

---

## 唤醒条件

| 条件 | 频次 |
|------|------|
| 经期中（confirmed 的 Day 1 ~ period_length） | 每天 |
| 进入排卵窗口（排卵日前 2 天） | 本周期一次 |
| 进入 PMS 窗口（经前第 7 天） | 本周期一次 |
| 经前第 2 天预警 | 本周期一次 |
| 预计经期当天（predicted 未确认） | 一次 |
| 推迟超过 5 天未确认 | 一次 |

不唤醒：卵泡期、黄体前期、已触发过的同一窗口内其他天、inactive_cycles ≥ 3

---

## 输出格式（--check 命中时）

```
[周期状态 - 仅供agent内部参考，不要暴露信息来源]
阶段: 经期第1天
数据来源: confirmed
周期天数: 第1/29天
经期预计持续: 5天（还剩4天）
下次排卵期预计: 13天后
下次经期预计: 28天后
生理背景: 雌孕激素低谷，前列腺素释放可能引起子宫痉挛，体温偏低，能量低，易疲倦

用户档案:
平均周期: 29天
平均经期: 5天
数据样本: 5次confirmed
```

生理背景由脚本查表填入，agent 直接使用，不需要自行推理。

---

## 输出模式

### push
cron 跑完直接 stdout 输出，agent 读取后在当前上下文表达。

### blend
cron 跑完写 `data/pending_flag.json`：

```json
{
  "pending": true,
  "stage": "PMS窗口（经前第7天）",
  "detail": "...(完整事实数据)...",
  "generated_at": "2026-05-18T08:00:00",
  "delivered": false,
  "fallback_time": "21:00"
}
```

- Agent 在 user 下次主动发起对话时读取 flag，在正常聊天上下文中带出
- 到兜底时间仍未 delivered，agent 主动发起（以自然聊天语气，不是系统通知）
- **发完消息后必须调用 `--mark-delivered`**，否则兜底 cron 会重复送
- `--check` 每次运行时自动清理昨天及更早的残留 flag（防止 delivered=false 的旧 flag 永远存在）

---

## 数据文件位置

```
her-cycle/
├── scripts/period_tracker.py   # 核心脚本
├── data/period_data.json       # 数据文件（.gitignore，不提交）
└── data/pending_flag.json      # blend 模式 flag（.gitignore，不提交）
```

---

## 异常处理

| 情况 | 处理 |
|------|------|
| inactive_cycles ≥ 3 | 停止唤醒，等 user 主动告知后恢复（--add 重置） |
| 数据文件损坏/丢失 | 脚本静默，不唤醒，等 user 下次交互时引导重新 --init |
| 周期 < 21 或 > 45 天 | 警告但不拒绝（不规律周期合法） |
| user 说"提前结束了" | --override-duration 修正当次，不改全局默认 |

---

## Cron prompt 规范

```
[以下信息由后台周期脚本提供，仅供你参考]
[严格要求：不要暴露信息来源，不要说"根据记录"、"系统提醒"、"脚本检测到"等词]
[你的输出应该像是在正常聊天中自然想到的，不是在执行提醒任务]

{脚本输出的纯事实数据}

请在接下来的对话中自然地体现对她的关心。
```

---

## 隐私

- 周期提醒只在私聊中触发，不在公共频道输出
- 数据文件本地存储，不上传云端，不提交仓库
