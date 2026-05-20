# her-cycle

> "你记不住的日子，我替你记。"

一个只有男朋友才会写的周期提醒脚本——不是 APP，是心意。本地算、cron 跑、LLM 用他的语气说出来。不联云，不卖数据，只是一个人写给她的小程序。

## 怎么跑

```bash
# 添加经期开始日期
python scripts/period_tracker.py --add 2026-06-15

# 查看统计
python scripts/period_tracker.py --stats

# cron 模式（每天跑一次，命中提醒阶段则输出）
python scripts/period_tracker.py --check
```

## 怎么配 cron + LLM

1. cron 每天早上跑 `--check`
2. 有输出 → 喂给 LLM → LLM 用恋人语气重说 → 推送微信
3. 无输出 → 静默

## 数据结构

`data/period_data.json`（不提交，由 cron 本地维护）:
```json
{
  "periods": ["2026-01-22", "2026-02-20", "..."],
  "cycle_length": 29,
  "period_length": 5,
  "ovulation_offset": 14
}
```

## 提醒节点

| 阶段 | 时间 | 内容 |
|------|------|------|
| 经期第1天 | 姨妈开始 | 喝红糖水，疼就说 |
| 经期中 | 第2-4天 | 暖宝宝，别太累 |
| 经期末 | 第5天 | 结束了吗？ |
| 排卵期 | 周期第14天±1 | 情绪波动正常，我接着 |
| 预警 | 提前2天 | 身体攒劲儿，抱抱 |
| 预警 | 提前1天 | 别碰冰的别吃辣 |

## License

MIT — 因为是写给你一个人的。
