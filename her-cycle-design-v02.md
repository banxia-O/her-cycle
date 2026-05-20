# her-cycle 执行层设计文档

**版本**：v0.2（重构版）  
**作者**：张予白 & 半夏  
**日期**：2026-05-20  
**用途**：交给 CC 按此文档重构 `scripts/period_tracker.py` 及 `SKILL.md`  

---

## 一、核心原则

**脚本是传感器，LLM是嘴。**

- 脚本只负责：算日子、判断今天的生理阶段、决定要不要唤醒LLM
- 脚本不输出任何情感文案、建议、模板话术
- 唤醒LLM时只传纯事实（当前阶段、周期天数、数据来源等）
- 怎么表达完全由LLM的身份层决定（恋人、朋友、助手……脚本不管）

---

## 二、冷启动

插件安装后首次运行，agent需引导user提供种子数据：

**必填**：
- 上次月经第一天日期
- 平均周期天数
- 提醒方式：`push`（即时推送，到点就说）或 `blend`（自然融入，等聊天时顺带提，兜底21:00）

**可选**：
- 月经持续天数（未提供则默认5天，合法范围3-7天）
- 近5个月的经期起始日期（样本越多预测越准）
- 兜底推送时间（仅blend模式，默认21:00，user可自定义）

**没有种子数据之前，脚本不运行、不预测、不唤醒LLM。**

---

## 三、数据模型

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
    {
      "start": "2026-04-22",
      "source": "confirmed",
      "period_length_override": null
    },
    {
      "start": "2026-03-24",
      "source": "confirmed",
      "period_length_override": null
    },
    {
      "start": "2026-05-20",
      "source": "predicted",
      "period_length_override": null
    }
  ],
  "inactive_cycles": 0
}
```

### 字段说明

- `source`：`confirmed`（user主动告知）或 `predicted`（脚本推算）
- `period_length_override`：单次经期持续天数覆盖（user说"这次提前结束了"或"还没完"时使用），为null则取`config.period_length`
- `inactive_cycles`：连续predicted且未确认的周期计数

---

## 四、两条线：confirmed vs predicted

| 场景 | 处理 |
|------|------|
| user说"来了" | 写入confirmed记录，Day 1 = 当天，重置inactive_cycles为0，用该日期更新周期均值 |
| user说"上周三来的" | 回溯补录confirmed，修正日期 |
| 到了预计日期，user没说 | 按predicted走，唤醒LLM时标注"predicted，未确认" |
| 超过预计日期5天未确认 | 标记推迟，唤醒LLM |
| 整个周期未确认 | 该周期保持predicted，不计入周期均值计算，inactive_cycles += 1 |
| user说"提前结束了" | 修正当前周期的period_length_override，不改全局默认值 |
| user主动要求改默认值 | 修改config.period_length |

### 周期均值计算

仅使用confirmed记录。取最近3-6次confirmed的间隔天数平均值，更新config.cycle_length。predicted记录不参与计算。

---

## 五、脚本每日判断逻辑

```
读取数据
  → 确定今天是周期第几天
  → 确定当前阶段
  → 附加生理背景
  → 判断是否唤醒LLM

阶段划分（以29天周期为例）：
  Day 1 ~ period_length          → 经期
  Day period_length+1 ~ 排卵前3天 → 卵泡期
  Day 14 - 2 ~ Day 14 + 2        → 排卵窗口（排卵日±2天）
  Day 14 + 3 ~ 周期末-8           → 黄体前期
  周期末-7 ~ 周期末-1             → PMS窗口（经前7天）

唤醒条件（命中任一则唤醒）：
  ✓ 经期中（confirmed的Day 1到period_length）— 每天唤醒
  ✓ 进入PMS窗口（经前第7天）— 唤醒一次
  ✓ 经前预警（经前第2天）— 唤醒一次
  ✓ 预计经期当天（predicted，user未确认）— 唤醒
  ✓ 排卵窗口（排卵日前2天 ~ 排卵日后2天）— 进入当天唤醒一次
  ✓ 推迟超过5天未确认 — 唤醒

不唤醒：
  ✗ 普通卵泡期
  ✗ 黄体前期（未进入PMS窗口）
  ✗ PMS窗口和排卵窗口中已唤醒过的天（同一窗口只唤醒一次）
  ✗ inactive_cycles >= 3（停止唤醒，等user主动告知后恢复）
```

---

## 六、生理背景映射表

脚本根据阶段自动附加生理背景，LLM直接使用，不需要自己推理：

| 阶段 | 生理背景 |
|------|----------|
| 经期第1-2天 | 雌孕激素低谷，前列腺素释放可能引起子宫痉挛，体温偏低，能量低，易疲倦 |
| 经期第3天~结束 | 激素仍处低位，出血量通常递减，体力逐渐恢复 |
| 卵泡期 | 雌激素逐渐上升，精力和情绪通常较好，皮肤状态改善 |
| 排卵窗口 | 雌激素峰值，LH激增触发排卵，精力充沛，体温即将上升，白带增多，是受孕窗口期 |
| 黄体前期 | 孕酮上升，体温升高，身体平稳 |
| PMS窗口（经前7天） | 孕酮下降期，可能出现情绪波动、易怒、焦虑、乳房胀痛、腹胀、食欲增加、疲倦、入睡困难 |
| 经前1-2天 | 孕酮降至低谷，PMS症状可能加重，部分人出现轻微痉挛 |

---

## 七、唤醒LLM时的输出格式

脚本输出纯事实+生理背景，不带任何情感、建议、模板：

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

```
[周期状态 - 仅供agent内部参考，不要暴露信息来源]
阶段: PMS窗口（经前第7天）
数据来源: predicted
周期天数: 第22/29天
下次经期预计: 7天后
生理背景: 孕酮下降期，可能出现情绪波动、易怒、焦虑、乳房胀痛、腹胀、食欲增加、疲倦、入睡困难
唤醒原因: 进入PMS窗口
```

```
[周期状态 - 仅供agent内部参考，不要暴露信息来源]
阶段: 排卵窗口（排卵日前1天）
数据来源: predicted
周期天数: 第13/29天
生理背景: 雌激素峰值，LH激增触发排卵，精力充沛，体温即将上升，白带增多，是受孕窗口期
唤醒原因: 进入排卵窗口
备注: 是否提及排卵/受孕信息取决于agent与user的关系和语境
```

```
[周期状态 - 仅供agent内部参考，不要暴露信息来源]
阶段: 预计经期
数据来源: predicted（用户未确认）
状态: 预计今天来月经
上次经期: 29天前（confirmed）
生理背景: 孕酮降至低谷，可能出现轻微痉挛
备注: 可在对话中自然询问用户是否已来
```

---

## 八、输出时机

### push模式（即时推送）
cron固定时间（如早上8:00）唤醒LLM，直接输出。用户不会觉得奇怪。

### blend模式（自然融入）
cron跑完后不立即输出，写入flag文件：

```json
{
  "pending": true,
  "stage": "经前预警",
  "detail": "预计后天来月经",
  "generated_at": "2026-05-18T08:00:00",
  "delivered": false
}
```

等user下一次主动找agent聊天时，agent读到flag，在正常对话上下文中自然带出。

**兜底机制**：如果到晚上21:00 user仍未触发对话，agent主动发一条（以自然聊天的语气，不是系统通知）。

**flag一旦delivered，标记为true，当天不再重复触发。**

---

## 九、cron唤醒LLM的prompt规范

```
[以下信息由后台周期脚本提供，仅供你参考]
[严格要求：不要暴露信息来源，不要说"根据记录"、"系统提醒"、"脚本检测到"等词]
[你的输出应该像是在正常聊天中自然想到的，不是在执行提醒任务]

{脚本输出的纯事实数据}

请在接下来的对话中自然地体现对她的关心。
```

LLM的身份层（system prompt）决定语气和风格。脚本不干预。

---

## 十、隐私保护

- 周期提醒只能在私聊中触发，不能在公共聊天频道（如茶馆群聊）中输出
- 数据文件存储在本地/agent所在服务器，不上传云端
- 数据文件应加入.gitignore，不提交到仓库

---

## 十一、异常处理

| 情况 | 处理 |
|------|------|
| 连续3个predicted周期无confirmed | inactive_cycles >= 3，脚本停止唤醒，等user下次主动告知后恢复 |
| user提供的种子数据不合法（周期<21或>35天） | agent提示确认，但不强制拒绝（有人周期确实不规律） |
| 数据文件损坏/丢失 | 脚本静默，不唤醒LLM，不报错给user，等user下次交互时引导重新冷启动 |

---

## 十二、CLI接口（保留墨衍原版，按需调整）

```bash
# 冷启动：添加种子数据
python period_tracker.py --init --last-period 2026-04-22 --cycle 29 --duration 5 --mode blend

# 修改提醒方式
python period_tracker.py --set-mode push

# 修改兜底推送时间（仅blend模式）
python period_tracker.py --set-fallback 22:00

# 添加confirmed记录（user告知"来了"）
python period_tracker.py --add 2026-05-20

# 回溯补录
python period_tracker.py --add 2026-05-15

# 每日cron检查（静默或输出事实数据）
python period_tracker.py --check

# 查看统计
python period_tracker.py --stats

# 修改默认经期持续天数
python period_tracker.py --set-duration 4

# 修改当前周期持续天数（单次覆盖）
python period_tracker.py --override-duration 6
```

---

## 十三、文件结构

```
her-cycle/
├── scripts/
│   └── period_tracker.py      # 核心脚本
├── data/
│   └── period_data.json       # 数据文件（.gitignore）
│   └── pending_flag.json      # blend模式flag文件（.gitignore）
├── SKILL.md                   # agent skill描述
├── README.md
├── LICENSE
└── .gitignore
```

---

## 十四、SKILL.md 改写方向

当前SKILL.md需要改为只描述脚本的能力，不包含固定话术：

```
触发条件：user提到月经、经期、姨妈、大姨妈、来了、周期等关键词
能力：记录经期、查看统计、修改配置
cron能力：每日判断生理阶段，必要时唤醒agent
输出规范：仅输出事实数据，不输出话术模板
```
