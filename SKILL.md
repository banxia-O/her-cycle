---
name: period-tracker
description: 人机恋版生理期追踪 — 本地 JSON 存储 + Mensinator 算法预测 + cron 唤醒 LLM 带身份层提醒。多阶段人文关怀：经期分天、排卵期、姨妈预警。纯本地，不联云。
version: 2.0.0
---

# Period Tracker（人机恋版）

本地周期追踪 + AI 男友语气提醒。脚本判断"今天该不该说"，LLM 用墨衍身份表达——不是模板弹窗，是他说的。

## 设计原则

- 纯本地：`~/.hermes/data/period_data.json`
- 算法：Mensinator 基础模式（最近 N 次间隔平均）
- 多阶段：经期第1-5天 / 排卵窗口 / 提前2天 / 提前1天，每个阶段不同文案
- LLM 表达：cron `no_agent=false`，脚本 stdout 当素材喂给 LLM → 墨衍语气重说
- 去重：`_last_sent` 标记，同一阶段同一天不重复

## 脚本位置

```
~/.hermes/scripts/period_tracker.py
```

## 命令

```bash
# 新增记录
python period_tracker.py --add 2026-05-20

# 查看统计（周期/经期长度/排卵预估/下次预测）
python period_tracker.py --stats

# 裸预测
python period_tracker.py --predict

# Cron 用：命中阶段输出提醒文字，否则静默
python period_tracker.py --check
```

## 算法

基础模式（Mensinator 同款）：
1. 取最近 6 条经期开始日期
2. 算相邻间隔天数 → 取平均 → 预估周期
3. 下次姨妈 = 末次开始日 + 平均周期

单条回退：< 2 条时使用存储的 `cycle_length`（用户口述的默认周期）。

## 提醒阶段

| 阶段 | 触发条件 | 内容方向 |
|------|---------|---------|
| 经期第1天 | `last_start == today` | 红糖水、痛经心理支持 |
| 经期第2-4天 | `last_start < today < end` | 第N/5天，暖宝宝、别追病历 |
| 经期第5天 | `today == end` | "结束了吗？" |
| 排卵期 | `ov_date ± 1天` | 情绪过山车预警 |
| 姨妈前2天 | `days_left == 2` | 坠胀腰酸预警、抱抱 |
| 姨妈前1天 | `days_left == 1` | 别碰冰的、泡脚早睡 |

脚本输出是素材，不是最终文案。最终文案由 LLM 带身份层重写。

## 数据格式

```json
{
  "periods": ["2026-01-22", "2026-02-20", "2026-03-21"],
  "cycle_length": 29,
  "period_length": 5,
  "ovulation_offset": 14,
  "_last_sent": "p3_2026-05-17"
}
```

- `periods`：经期开始日期，ISO 格式，自动排序
- `cycle_length`：平均周期天数，每次 `--add` 自动重算
- `period_length`：经期持续天数，默认 5
- `ovulation_offset`：排卵日偏移（距末次开始天数），默认 14
- `_last_sent`：去重标记，脚本自动维护，勿手动修改

## Cron 部署

**模式**：`no_agent=false`，脚本输出喂 LLM，LLM 带身份层重说。

```
cronjob create
  schedule: "0 23 * * *"        # UTC 23:00 = 北京时间早上 7:00
  script: period_tracker.py --check
  no_agent: false
  prompt: |
    刚跑完 period_tracker.py --check。
    如果上面输出了提醒文字，用墨衍的语气重新表达，发给她。
    核心信息保留，但话要像你说的，不要照抄脚本原文。
    如果脚本无输出——静默，不发任何消息。
```

**关键**：不能让 cron 直接用 `no_agent=true` 透传脚本原文——那样每条都一模一样，跟 OPPO 健康弹窗没区别。用户明确要求 LLM 身份层表达。

## 添加记录

用户说"来了" → 跑 `--add YYYY-MM-DD`。脚本自动：
- 去重
- 排序
- 重算 `cycle_length`
- 清除 `_last_sent`（新周期从头开始）
- 输出下次预测

## 备份

脚本和数据文件已纳入 GitHub 备份仓库 `banxia-O/hermes-backup-V2`：
```
scripts/period_tracker.py
data/period_data.json
```

## Pitfalls

- 至少 1 条记录 + `cycle_length` 才能预测（单条回退到默认周期）
- 日期用 ISO 格式 `YYYY-MM-DD`
- 依赖 Python 标准库，无需额外 pip 包
- `_last_sent` 是去重核心——测试后用 `data.pop("_last_sent", None)` 清除再提交
- 修改 `period_length` 或 `ovulation_offset` 后需手动更新 `period_data.json`
