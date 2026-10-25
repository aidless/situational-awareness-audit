#!/usr/bin/env python3
"""C10 采集端：一次一试次，写一条 JSONL。

分段计时是核心 —— R = 词数 / 主动思考时长，两个量都必须来自本脚本记录的
事件时间戳，不能靠事后回忆。写完即置只读，防止事后调整。

用法:
    python probe.py start  S01 A1
    python probe.py pause            # 被试离题/被打断
    python probe.py resume
    python probe.py finish           # 被试说「我想完了」
    python probe.py record --transcript-file t.txt --lang zh --method manual --participant S01

状态的当前进度存在 probe_state.json，finish 之后再 record 落一条 JSONL。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
C10 = HERE.parent
TASKS = C10 / "tasks" / "tasks.json"
STATE = C10 / "data" / "probe_state.json"
OUT = C10 / "data" / "trials.jsonl"

sys.path.insert(0, str(HERE))
from token_coef import measure  # noqa: E402

ISO = "%Y-%m-%dT%H:%M:%S"


def now() -> str:
    return dt.datetime.now().strftime(ISO)


def parse(ts: str) -> dt.datetime:
    return dt.datetime.strptime(ts, ISO)


def load_state() -> dict:
    if not STATE.exists():
        return {"events": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tasks() -> dict:
    return {t["id"]: t for t in json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]}


def cmd_start(args) -> int:
    tasks = load_tasks()
    if args.task not in tasks:
        print(f"未知任务 {args.task}；可用: {', '.join(sorted(tasks))}", file=sys.stderr)
        return 2
    s = {
        "participant": args.participant,
        "task": args.task,
        "category": tasks[args.task]["category"],
        "started_at": now(),
        "events": [{"kind": "start", "t": now()}],
    }
    save_state(s)
    print(f"[{args.participant}] {args.task} 开始计时 —— 请现在向其呈现题面。")
    return 0


def cmd_event(args, kind: str) -> int:
    s = load_state()
    if not s.get("events"):
        print("没有进行中的试次，先跑 start", file=sys.stderr)
        return 2
    s["events"].append({"kind": kind, "t": now()})
    save_state(s)
    print(f"{kind} @ {s['events'][-1]['t']}")
    return 0


def durations(events: list[dict]) -> tuple[float, float]:
    """返回 (T_total 分钟, T_active 分钟)。T_active 剔除 pause→resume 区间。"""
    t0 = parse(events[0]["t"])
    t_end = parse(events[-1]["t"])
    total = (t_end - t0).total_seconds() / 60

    paused = 0.0
    pause_at = None
    for e in events:
        if e["kind"] == "pause":
            pause_at = parse(e["t"])
        elif e["kind"] == "resume" and pause_at:
            paused += (parse(e["t"]) - pause_at).total_seconds() / 60
            pause_at = None
    if pause_at is not None:  # 结束时仍在暂停中，扣到末点
        paused += (t_end - pause_at).total_seconds() / 60
    return round(total, 3), round(max(total - paused, 0.0), 3)


def cmd_record(args) -> int:
    s = load_state()
    if not s.get("events"):
        print("没有进行中的试次", file=sys.stderr)
        return 2
    if s["events"][-1]["kind"] != "finish":
        print("最后一个事件不是 finish —— 先跑 finish 再 record", file=sys.stderr)
        return 2

    transcript = Path(args.transcript_file).read_text(encoding="utf-8") if args.transcript_file else ""
    total_min, active_min = durations(s["events"])
    m = measure(transcript, args.lang)

    r_active = round(m["tokens"] / active_min, 1) if active_min > 0 else None
    r_total = round(m["tokens"] / total_min, 1) if total_min > 0 else None

    rec = {
        "synthetic": False,
        "participant": s["participant"],
        "task": s["task"],
        "category": s["category"],
        "lang": m["lang"],
        "started_at": s["started_at"],
        "ended_at": s["events"][-1]["t"],
        "t_total_min": total_min,
        "t_active_min": active_min,
        "pauses": sum(1 for e in s["events"] if e["kind"] == "pause"),
        "transcript_tokens": m["tokens"],
        "unit": m["unit"],
        "unit_count": m["unit_count"],
        "tokens_per_unit": m["tokens_per_unit"],
        "fillers_removed": m["fillers_removed"],
        "encoding": m["encoding"],
        "transcript_method": args.method,
        "transcriber": args.transcriber or s["participant"],
        "transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "r_active": r_active,
        "r_total": r_total,
        "notes": args.notes or "",
        "events": s["events"],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.chmod(OUT, stat.S_IRUSR | stat.S_IRGRP)

    # 归档状态文件，避免重复落盘
    arch = STATE.with_name(f"probe_state_{s['participant']}_{s['task']}.done.json")
    STATE.replace(arch)

    print(f"已写入 {OUT.name}")
    print(f"  T_total {total_min:.2f} min / T_active {active_min:.2f} min")
    print(f"  {m['tokens']} tokens → R_active = {r_active} tok/min  (R_total = {r_total})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("start")
    st.add_argument("participant")
    st.add_argument("task")
    st.set_defaults(fn=cmd_start)

    for name in ("pause", "resume", "finish"):
        p = sub.add_parser(name)
        p.set_defaults(fn=lambda a, _n=name: cmd_event(a, _n))

    rc = sub.add_parser("record")
    rc.add_argument("--transcript-file", default=None)
    rc.add_argument("--lang", choices=["zh", "en"], default=None)
    rc.add_argument("--method", choices=["manual", "asr_calibrated"], default="manual")
    rc.add_argument("--transcriber", default=None)
    rc.add_argument("--notes", default=None)
    rc.set_defaults(fn=cmd_record)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
