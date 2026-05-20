#!/usr/bin/env python3
"""Period tracker v0.2 — sensor only. Outputs pure facts, no emotional copy."""

import json
import sys
import os
import argparse
from datetime import date, timedelta, datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
DATA_DIR = os.path.join(_REPO_ROOT, "data")
DATA_FILE = os.path.join(DATA_DIR, "period_data.json")
FLAG_FILE = os.path.join(DATA_DIR, "pending_flag.json")

# Physiological background lookup table — scripts fills in, LLM uses directly.
PHYSIO = {
    "period_early": "雌孕激素低谷，前列腺素释放可能引起子宫痉挛，体温偏低，能量低，易疲倦",
    "period_late":  "激素仍处低位，出血量通常递减，体力逐渐恢复",
    "follicular":   "雌激素逐渐上升，精力和情绪通常较好，皮肤状态改善",
    "ovulation":    "雌激素峰值，LH激增触发排卵，精力充沛，体温即将上升，白带增多，是受孕窗口期",
    "early_luteal": "孕酮上升，体温升高，身体平稳",
    "pms":          "孕酮下降期，可能出现情绪波动、易怒、焦虑、乳房胀痛、腹胀、食欲增加、疲倦、入睡困难",
    "pre_period":   "孕酮降至低谷，PMS症状可能加重，部分人出现轻微痉挛",
}


# ── I/O ────────────────────────────────────────────────────────────────────────

def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Cycle math ─────────────────────────────────────────────────────────────────

def confirmed_periods(data):
    return [p for p in data.get("periods", []) if p["source"] == "confirmed"]


def recalc_cycle(data):
    """Return updated cycle_length using 3–6 most recent confirmed intervals."""
    cp = sorted(confirmed_periods(data), key=lambda p: p["start"])
    if len(cp) < 2:
        return data["config"]["cycle_length"]
    recent = cp[-7:]
    intervals = [
        (date.fromisoformat(recent[i + 1]["start"]) - date.fromisoformat(recent[i]["start"])).days
        for i in range(len(recent) - 1)
    ]
    return round(sum(intervals[-6:]) / len(intervals[-6:]))


def ovulation_day_num(cycle_length, period_length):
    """Day number of ovulation within cycle (14-day luteal phase standard)."""
    return max(cycle_length - 14, period_length + 2)


def inactive_cycle_count(data):
    """Count consecutive past predicted cycles (no confirmation)."""
    today = date.today()
    cl = data["config"]["cycle_length"]
    periods = sorted(data.get("periods", []), key=lambda p: p["start"])
    count = 0
    for p in reversed(periods):
        start = date.fromisoformat(p["start"])
        if start > today:
            continue  # not started yet — skip
        cycle_ended = (start + timedelta(days=cl)) <= today
        if not cycle_ended:
            # Current (ongoing) cycle: break streak if confirmed, otherwise skip
            if p["source"] == "confirmed":
                break
            continue
        # Past completed cycle
        if p["source"] == "predicted":
            count += 1
        else:
            break
    return count


def current_cycle_info(data):
    """
    Return a dict describing today's position in the cycle.
    Returns None if no data or today is before all records.
    """
    today = date.today()
    config = data["config"]
    cl = config["cycle_length"]
    pl_default = config["period_length"]

    periods = sorted(data.get("periods", []), key=lambda p: p["start"])

    # Most recent period that started on or before today
    current = None
    for p in reversed(periods):
        if date.fromisoformat(p["start"]) <= today:
            current = p
            break

    if current is None:
        return None

    cycle_start = date.fromisoformat(current["start"])
    cycle_day = (today - cycle_start).days + 1
    period_len = current.get("period_length_override") or pl_default
    predicted_next = cycle_start + timedelta(days=cl)

    return {
        "cycle_start":     cycle_start,
        "cycle_day":       cycle_day,
        "cycle_length":    cl,
        "period_length":   period_len,
        "source":          current["source"],
        "predicted_next":  predicted_next,
    }


# ── Phase engine ───────────────────────────────────────────────────────────────

def determine_phase(info):
    """
    Map today's cycle position to a phase key.
    Returns (phase_key, ov_day_num).
    """
    day = info["cycle_day"]
    pl  = info["period_length"]
    cl  = info["cycle_length"]
    src = info["source"]
    ov  = ovulation_day_num(cl, pl)

    ov_start = ov - 2
    ov_end   = ov + 2
    pms_start = cl - 7

    # Predicted period: treat as special "predicted_arrival" during period days
    if src == "predicted" and 1 <= day <= pl:
        return "period_predicted", ov

    if 1 <= day <= min(2, pl):
        return "period_early", ov
    if 3 <= day <= pl:
        return "period_late", ov
    if pl < day < ov_start:
        return "follicular", ov
    if ov_start <= day <= ov_end:
        return "ovulation", ov
    if ov_end < day < pms_start:
        return "early_luteal", ov
    if pms_start <= day <= cl - 3:
        return "pms", ov
    if cl - 2 <= day:
        return "pre_period", ov

    return "follicular", ov


def phase_display(phase, info, ov_day):
    """Human-readable phase label for output."""
    day = info["cycle_day"]
    cl  = info["cycle_length"]

    if phase == "period_early":
        return f"经期第{day}天"
    if phase == "period_late":
        return f"经期第{day}天"
    if phase == "period_predicted":
        return "预计经期"
    if phase == "follicular":
        return "卵泡期"
    if phase == "ovulation":
        diff = day - ov_day
        if diff < 0:
            return f"排卵窗口（排卵日前{-diff}天）"
        if diff == 0:
            return "排卵窗口（排卵日当天）"
        return f"排卵窗口（排卵日后{diff}天）"
    if phase == "early_luteal":
        return "黄体前期"
    if phase == "pms":
        return f"PMS窗口（经前第{cl - day}天）"
    if phase == "pre_period":
        days_left = cl - day
        if days_left <= 0:
            return "经前第1天"
        return f"经前第{days_left}天"
    return phase


def physio_for(phase):
    """Return physiological background text for a given phase."""
    if phase == "period_predicted":
        return PHYSIO["pre_period"]
    return PHYSIO.get(phase, "")


# ── Wake-up logic ──────────────────────────────────────────────────────────────

def should_wake(data, info, phase):
    """
    Return (wake: bool, reason: str).
    Same-window dedup via wake_log in data.
    """
    day    = info["cycle_day"]
    cl     = info["cycle_length"]
    pl     = info["period_length"]
    src    = info["source"]
    cs     = info["cycle_start"].isoformat()
    pn     = info["predicted_next"].isoformat()
    ov     = ovulation_day_num(cl, pl)
    wlog   = data.get("wake_log", {})

    # Inactive cycle guard — use stored value (updated by cmd_check before calling us)
    if data.get("inactive_cycles", 0) >= 3:
        return False, ""

    # 0. Delay check first: overrides PMS/pre-period when prediction is overdue
    if src == "predicted" and day > cl + 5:
        key = f"delay_{cs}"
        if key not in wlog:
            return True, f"推迟{day - cl}天未确认"

    # 1. Confirmed period: wake every day (no dedup)
    if src == "confirmed" and 1 <= day <= pl:
        return True, "经期"

    # 2. Predicted period arrival: once (on cycle day 1 of a predicted cycle)
    if phase == "period_predicted" and day == 1:
        key = f"pred_arrival_{cs}"
        if key not in wlog:
            return True, "预计经期当天（未确认）"

    # 3. Ovulation window: once per cycle
    if phase == "ovulation":
        key = f"ovulation_{cs}"
        if key not in wlog:
            return True, "进入排卵窗口"

    # 4. PMS window entry: once per cycle (fires on first day entering cl-7 range)
    if phase in ("pms", "pre_period"):
        key = f"pms_{cs}"
        if key not in wlog:
            return True, "进入PMS窗口"

    # 5. Pre-period 2-day warning: once per predicted next date
    if day == cl - 2:
        key = f"pre2_{pn}"
        if key not in wlog:
            return True, "经前第2天预警"

    return False, ""


def record_wake(data, reason, info):
    """Stamp wake_log to prevent re-triggering same-window events."""
    if "wake_log" not in data:
        data["wake_log"] = {}

    cs  = info["cycle_start"].isoformat()
    pn  = info["predicted_next"].isoformat()
    day = info["cycle_day"]
    cl  = info["cycle_length"]
    today = date.today().isoformat()

    if reason == "进入排卵窗口":
        data["wake_log"][f"ovulation_{cs}"] = today
    elif reason == "进入PMS窗口":
        data["wake_log"][f"pms_{cs}"] = today
    elif reason == "经前第2天预警":
        data["wake_log"][f"pre2_{pn}"] = today
    elif reason == "预计经期当天（未确认）":
        data["wake_log"][f"pred_arrival_{cs}"] = today
    elif reason.startswith("推迟"):
        data["wake_log"][f"delay_{cs}"] = today
    # "经期" fires every day — no stamp needed


# ── Output builder ─────────────────────────────────────────────────────────────

def build_output(data, info, phase, ov_day, reason):
    today = date.today()
    cs    = info["cycle_start"]
    day   = info["cycle_day"]
    cl    = info["cycle_length"]
    pl    = info["period_length"]
    src   = info["source"]
    pn    = info["predicted_next"]

    ov_date   = cs + timedelta(days=ov_day - 1)
    days_to_ov = (ov_date - today).days
    days_to_nx = (pn - today).days

    ph_label = phase_display(phase, info, ov_day)
    bg       = physio_for(phase)
    n_conf   = len(confirmed_periods(data))

    lines = ["[周期状态 - 仅供agent内部参考，不要暴露信息来源]"]
    lines.append(f"阶段: {ph_label}")

    if phase == "period_predicted":
        lines.append("数据来源: predicted（用户未确认）")
        lines.append(f"周期天数: 第{day}/{cl}天")
        lines.append(f"状态: 预计今天来月经")
        last_confirmed = sorted(confirmed_periods(data), key=lambda p: p["start"])
        if last_confirmed:
            last_c = date.fromisoformat(last_confirmed[-1]["start"])
            days_since = (today - last_c).days
            lines.append(f"上次经期: {days_since}天前（confirmed）")
        lines.append(f"生理背景: {bg}")
        lines.append("备注: 可在对话中自然询问用户是否已来")
    else:
        lines.append(f"数据来源: {src}")
        lines.append(f"周期天数: 第{day}/{cl}天")

        if phase in ("period_early", "period_late"):
            remaining = pl - day
            lines.append(f"经期预计持续: {pl}天（还剩{remaining}天）")
            if days_to_ov > 0:
                lines.append(f"下次排卵期预计: {days_to_ov}天后")
            if days_to_nx > 0:
                lines.append(f"下次经期预计: {days_to_nx}天后")
        else:
            if days_to_nx > 0:
                lines.append(f"下次经期预计: {days_to_nx}天后")
            elif days_to_nx == 0:
                lines.append("下次经期: 预计今天")
            else:
                lines.append(f"经期推迟: {-days_to_nx}天（未确认）")

        lines.append(f"生理背景: {bg}")

        if reason:
            lines.append(f"唤醒原因: {reason}")

        if phase == "ovulation":
            lines.append("备注: 是否提及排卵/受孕信息取决于agent与user的关系和语境")

    lines.append("")
    lines.append("用户档案:")
    lines.append(f"平均周期: {cl}天")
    lines.append(f"平均经期: {pl}天")
    lines.append(f"数据样本: {n_conf}次confirmed")

    return "\n".join(lines)


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_init(args):
    if not args.last_period:
        sys.exit("ERROR: --last-period required")
    if not args.cycle:
        sys.exit("ERROR: --cycle required")
    if not args.mode:
        sys.exit("ERROR: --mode required")

    try:
        last_period = date.fromisoformat(args.last_period)
    except ValueError:
        sys.exit("ERROR: --last-period must be YYYY-MM-DD")

    cycle = args.cycle
    if cycle < 21 or cycle > 45:
        print(f"WARNING: cycle {cycle}d is outside typical range (21-45). Proceeding.")

    duration = args.duration if args.duration else 5
    if not (3 <= duration <= 7):
        print(f"WARNING: duration {duration} outside 3-7, using 5.")
        duration = 5

    fallback = args.fallback or "21:00"

    data = {
        "config": {
            "cycle_length": cycle,
            "period_length": duration,
            "seed_date": last_period.isoformat(),
            "delivery_mode": args.mode,
            "fallback_time": fallback,
        },
        "periods": [
            {"start": last_period.isoformat(), "source": "confirmed", "period_length_override": None}
        ],
        "inactive_cycles": 0,
        "wake_log": {},
    }

    # Optional historical confirmed dates
    if args.history:
        for h in args.history:
            try:
                hd = date.fromisoformat(h)
                if hd.isoformat() != last_period.isoformat():
                    data["periods"].append({
                        "start": hd.isoformat(),
                        "source": "confirmed",
                        "period_length_override": None,
                    })
            except ValueError:
                print(f"WARNING: ignoring invalid history date: {h}", file=sys.stderr)

    data["periods"].sort(key=lambda p: p["start"])

    # Recalculate cycle from history if available
    if len(confirmed_periods(data)) >= 2:
        cycle = recalc_cycle(data)
        data["config"]["cycle_length"] = cycle

    # Add predicted next period
    latest_start = max(date.fromisoformat(p["start"]) for p in data["periods"])
    predicted = latest_start + timedelta(days=cycle)
    data["periods"].append({
        "start": predicted.isoformat(),
        "source": "predicted",
        "period_length_override": None,
    })

    save_data(data)
    print(f"OK: initialized | cycle={cycle}d | duration={duration}d | mode={args.mode}")
    print(f"Last period : {last_period.isoformat()}")
    print(f"Predicted   : {predicted.isoformat()}")


def cmd_add(args):
    data = load_data()
    if data is None:
        sys.exit("ERROR: no data file. Run --init first.")

    try:
        new_date = date.fromisoformat(args.add)
    except ValueError:
        sys.exit("ERROR: date must be YYYY-MM-DD")

    # Skip if already confirmed
    if any(p["start"] == new_date.isoformat() and p["source"] == "confirmed"
           for p in data["periods"]):
        print(f"SKIP: {new_date.isoformat()} already confirmed")
        return

    # Remove nearby predicted records (within ±5 days)
    data["periods"] = [
        p for p in data["periods"]
        if not (p["source"] == "predicted"
                and abs((date.fromisoformat(p["start"]) - new_date).days) <= 5)
    ]

    data["periods"].append({
        "start": new_date.isoformat(),
        "source": "confirmed",
        "period_length_override": None,
    })
    data["periods"].sort(key=lambda p: p["start"])

    # Reset inactive counter
    data["inactive_cycles"] = 0

    # Recalculate cycle
    cycle = recalc_cycle(data)
    data["config"]["cycle_length"] = cycle

    # Add new predicted next
    predicted = new_date + timedelta(days=cycle)
    if not any(p["source"] == "predicted" and p["start"] == predicted.isoformat()
               for p in data["periods"]):
        data["periods"].append({
            "start": predicted.isoformat(),
            "source": "predicted",
            "period_length_override": None,
        })

    save_data(data)
    print(f"OK: {new_date.isoformat()} (confirmed) | cycle={cycle}d")
    print(f"Predicted next: {predicted.isoformat()}")


def cmd_check(args):
    data = load_data()
    if data is None:
        sys.exit(0)

    # Update inactive_cycles
    data["inactive_cycles"] = inactive_cycle_count(data)

    inactive = data["inactive_cycles"]
    if inactive >= 3:
        save_data(data)
        sys.exit(0)

    info = current_cycle_info(data)
    if info is None:
        save_data(data)
        sys.exit(0)

    phase, ov_day = determine_phase(info)
    wake, reason = should_wake(data, info, phase)

    if not wake:
        save_data(data)
        sys.exit(0)

    output = build_output(data, info, phase, ov_day, reason)
    mode = data["config"].get("delivery_mode", "push")

    if mode == "push":
        print(output)
    else:
        flag = {
            "pending":       True,
            "stage":         phase_display(phase, info, ov_day),
            "detail":        output,
            "generated_at":  datetime.now().isoformat(timespec="seconds"),
            "delivered":     False,
            "fallback_time": data["config"].get("fallback_time", "21:00"),
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(FLAG_FILE, "w", encoding="utf-8") as f:
            json.dump(flag, f, indent=2, ensure_ascii=False)
        # Confirm to cron log without leaking content
        print(f"BLEND: flag written | stage={flag['stage']}")

    record_wake(data, reason, info)
    save_data(data)


def cmd_stats(args):
    data = load_data()
    if data is None:
        print("未初始化，请先运行 --init")
        return

    cfg    = data["config"]
    today  = date.today()
    n_conf = len(confirmed_periods(data))
    inactive = inactive_cycle_count(data)

    print(f"平均周期   : {cfg['cycle_length']}天")
    print(f"平均经期   : {cfg['period_length']}天")
    print(f"提醒模式   : {cfg['delivery_mode']}")
    print(f"兜底时间   : {cfg.get('fallback_time', '21:00')} (blend only)")
    print(f"confirmed  : {n_conf}条")
    print(f"inactive   : {inactive}个连续predicted周期")

    cp = sorted(confirmed_periods(data), key=lambda p: p["start"])
    if cp:
        print(f"最近confirmed: {cp[-1]['start']}")

    predicted = [p for p in data.get("periods", []) if p["source"] == "predicted"]
    if predicted:
        pn = max(predicted, key=lambda p: p["start"])
        days_away = (date.fromisoformat(pn["start"]) - today).days
        sign = "后" if days_away >= 0 else "前"
        print(f"下次经期预计 : {pn['start']} ({abs(days_away)}天{sign})")

    info = current_cycle_info(data)
    if info:
        ov = ovulation_day_num(info["cycle_length"], info["period_length"])
        ov_date = info["cycle_start"] + timedelta(days=ov - 1)
        days_to_ov = (ov_date - today).days
        sign_ov = "后" if days_to_ov >= 0 else "前"
        print(f"排卵日预计   : {ov_date.isoformat()} ({abs(days_to_ov)}天{sign_ov})")
        print(f"当前周期     : 第{info['cycle_day']}/{info['cycle_length']}天 ({info['source']})")


def cmd_set_mode(args):
    data = load_data()
    if data is None:
        sys.exit("ERROR: 请先 --init")
    data["config"]["delivery_mode"] = args.set_mode
    save_data(data)
    print(f"OK: delivery_mode={args.set_mode}")


def cmd_set_fallback(args):
    data = load_data()
    if data is None:
        sys.exit("ERROR: 请先 --init")
    data["config"]["fallback_time"] = args.set_fallback
    save_data(data)
    print(f"OK: fallback_time={args.set_fallback}")


def cmd_set_duration(args):
    data = load_data()
    if data is None:
        sys.exit("ERROR: 请先 --init")
    dur = args.set_duration
    if not (3 <= dur <= 7):
        print(f"WARNING: {dur} outside typical range 3-7")
    data["config"]["period_length"] = dur
    save_data(data)
    print(f"OK: period_length={dur}")


def cmd_override_duration(args):
    data = load_data()
    if data is None:
        sys.exit("ERROR: 请先 --init")

    today = date.today()
    periods = sorted(data.get("periods", []), key=lambda p: p["start"])
    current = None
    for p in reversed(periods):
        if date.fromisoformat(p["start"]) <= today:
            current = p
            break

    if current is None:
        sys.exit("ERROR: 当前周期未找到")

    current["period_length_override"] = args.override_duration
    save_data(data)
    print(f"OK: override period_length={args.override_duration} for cycle {current['start']}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Period tracker v0.2 — sensor only, pure-fact output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --init --last-period 2026-04-22 --cycle 29 --mode blend --duration 5
  %(prog)s --init --last-period 2026-04-22 --cycle 29 --mode push \\
           --history 2026-03-24 2026-02-23 2026-01-25
  %(prog)s --add 2026-05-20
  %(prog)s --check
  %(prog)s --stats
  %(prog)s --set-mode push
  %(prog)s --set-fallback 22:00
  %(prog)s --set-duration 4
  %(prog)s --override-duration 6
""",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init",              action="store_true",
                       help="Cold start: create data file with seed data")
    group.add_argument("--add",               metavar="YYYY-MM-DD",
                       help="Add confirmed period start date")
    group.add_argument("--check",             action="store_true",
                       help="Daily cron check: output facts if wake condition met")
    group.add_argument("--stats",             action="store_true",
                       help="Show cycle statistics")
    group.add_argument("--set-mode",          metavar="push|blend",
                       help="Set delivery mode")
    group.add_argument("--set-fallback",      metavar="HH:MM",
                       help="Set blend fallback time")
    group.add_argument("--set-duration",      type=int, metavar="DAYS",
                       help="Set default period duration")
    group.add_argument("--override-duration", type=int, metavar="DAYS",
                       help="Override current cycle's period duration")

    # Init-specific optional args
    parser.add_argument("--last-period", metavar="YYYY-MM-DD",
                        help="Last period start date (required with --init)")
    parser.add_argument("--cycle",       type=int, metavar="DAYS",
                        help="Average cycle length (required with --init)")
    parser.add_argument("--mode",        choices=["push", "blend"],
                        help="Delivery mode (required with --init)")
    parser.add_argument("--duration",    type=int, metavar="DAYS", default=5,
                        help="Period duration in days (default: 5)")
    parser.add_argument("--fallback",    metavar="HH:MM", default="21:00",
                        help="Blend fallback time (default: 21:00)")
    parser.add_argument("--history",     nargs="+", metavar="YYYY-MM-DD",
                        help="Historical period start dates (optional with --init)")

    args = parser.parse_args()

    if args.init:
        cmd_init(args)
    elif args.add:
        cmd_add(args)
    elif args.check:
        cmd_check(args)
    elif args.stats:
        cmd_stats(args)
    elif args.set_mode:
        cmd_set_mode(args)
    elif args.set_fallback:
        cmd_set_fallback(args)
    elif args.set_duration is not None:
        cmd_set_duration(args)
    elif args.override_duration is not None:
        cmd_override_duration(args)


if __name__ == "__main__":
    main()
