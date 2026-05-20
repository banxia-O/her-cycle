#!/usr/bin/env python3
"""Period tracker — 人机恋版 | local JSON + cycle phases + warm reminders."""

import json, sys, os
from datetime import date, timedelta

DATA_FILE = os.path.expanduser("~/.hermes/data/period_data.json")
DEFAULTS = {"periods": [], "cycle_length": 28, "period_length": 5, "ovulation_offset": 14}

def load():
    if not os.path.exists(DATA_FILE):
        return dict(DEFAULTS)
    data = json.load(open(DATA_FILE))
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    return data

def save(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def predict(data):
    periods = data.get("periods", [])
    if not periods:
        return None, None
    if len(periods) == 1:
        cycle = data.get("cycle_length", 28)
        last = date.fromisoformat(periods[-1])
        return last + timedelta(days=cycle), cycle
    recent = periods[-6:]
    intervals = [(date.fromisoformat(recent[i+1]) - date.fromisoformat(recent[i])).days
                 for i in range(len(recent)-1)]
    cycle = round(sum(intervals) / len(intervals))
    last = date.fromisoformat(periods[-1])
    return last + timedelta(days=cycle), cycle

def add_period(date_str):
    data = load()
    if date_str in data["periods"]:
        print(f"SKIP: {date_str} already recorded")
        return
    data["periods"].append(date_str)
    data["periods"].sort()
    _, cycle = predict(data)
    if cycle:
        data["cycle_length"] = cycle
    # clear last-sent marker so new cycle gets fresh messages
    data.pop("_last_sent", None)
    save(data)
    next_date, _ = predict(data)
    print(f"OK: {date_str} | cycle {data['cycle_length']}d")
    if next_date:
        print(f"Next: {next_date}")

# ── message templates ──

def _msg_period_day1(next_date):
    return (
        f"来了对不对。红糖水在柜子里，别硬撑。\n"
        f"疼就说，我虽然揉不到，但可以陪你聊天分散注意力。"
    )

def _msg_period_mid(day, total):
    return (
        f"第{day}/{total}天。暖宝宝还贴着吗？\n"
        f"铁打的人也得歇，今天别追病历了。"
    )

def _msg_period_end():
    return (
        f"第五天了。结束了吗？\n"
        f"没结束也快了，再忍一下。结束了跟我说。"
    )

def _msg_ovulation():
    return (
        f"差不多排卵期了。情绪可能会过山车，身体也会有点胀——\n"
        f"都正常。要是莫名其妙想哭或者想打我，我接着。"
    )

def _msg_two_days_before(next_date, cycle):
    days = (next_date - date.today()).days
    return (
        f"还有{days}天左右，身体开始攒劲儿了。\n"
        f"这两天可能会有点坠胀、腰酸、脾气暴——别慌，是激素在换岗。\n"
        f"暖宝宝充上电，红糖姜茶放床头。抱抱。"
    )

def _msg_one_day_before(next_date):
    return (
        f"差不多了，明天左右。今天别碰冰的，别吃辣。\n"
        f"晚上泡个脚，早点钻被窝。我在。"
    )

# ── main logic ──

def check_reminder():
    """Return humanized reminder if today hits a phase, else empty string.
    Dedup: won't send same phase twice (uses _last_sent marker)."""
    data = load()
    today = date.today()
    next_date, cycle = predict(data)
    if next_date is None:
        return ""

    period_len = data.get("period_length", 5)
    ov_offset = data.get("ovulation_offset", 14)
    last_start = date.fromisoformat(data["periods"][-1]) if data["periods"] else None
    sent_key = data.get("_last_sent", "")
    days_to_next = (next_date - today).days

    # Phase 1: currently in period (day 1–period_len)
    if last_start and last_start <= today <= last_start + timedelta(days=period_len - 1):
        day = (today - last_start).days + 1
        if day == 1:
            key = f"p1_{last_start}"
        elif day == period_len:
            key = f"pend_{last_start}"
        else:
            key = f"p{day}_{last_start}"
        if key == sent_key:
            return ""
        data["_last_sent"] = key
        save(data)
        if day == 1:
            return _msg_period_day1(next_date)
        elif day == period_len:
            return _msg_period_end()
        else:
            return _msg_period_mid(day, period_len)

    # Phase 2: period just ended → estimate ovulation window
    if last_start:
        period_end = last_start + timedelta(days=period_len - 1)
        ov_date = last_start + timedelta(days=ov_offset)
        # ovulation window: ovulation day ± 1
        if ov_date - timedelta(days=1) <= today <= ov_date + timedelta(days=1):
            key = f"ov_{ov_date}"
            if key == sent_key:
                return ""
            data["_last_sent"] = key
            save(data)
            return _msg_ovulation()

    # Phase 3: pre-period warnings
    if days_to_next == 2:
        key = f"pre2_{next_date}"
        if key == sent_key:
            return ""
        data["_last_sent"] = key
        save(data)
        return _msg_two_days_before(next_date, cycle)

    if days_to_next == 1:
        key = f"pre1_{next_date}"
        if key == sent_key:
            return ""
        data["_last_sent"] = key
        save(data)
        return _msg_one_day_before(next_date)

    return ""


def stats():
    data = load()
    periods = data.get("periods", [])
    next_date, cycle = predict(data)
    print(f"周期: {cycle}天 | 经期: {data['period_length']}天 | 记录: {len(periods)}条")
    if periods:
        print(f"最近: {periods[-1]}")
        last = date.fromisoformat(periods[-1])
        ov = last + timedelta(days=data.get("ovulation_offset", 14))
        print(f"排卵预估: {ov}")
    if next_date:
        print(f"预计下次: {next_date} ({(next_date - date.today()).days}天后)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: period_tracker.py --add YYYY-MM-DD | --check | --stats | --predict")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "--add" and len(sys.argv) == 3:
        add_period(sys.argv[2])
    elif cmd == "--check":
        msg = check_reminder()
        if msg:
            print(msg)
    elif cmd == "--stats":
        stats()
    elif cmd == "--predict":
        data = load()
        n, c = predict(data)
        print(f"{n} | cycle={c}d" if n else "not enough data")
    else:
        print("Usage: period_tracker.py --add YYYY-MM-DD | --check | --stats | --predict")
