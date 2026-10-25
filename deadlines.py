#!/usr/bin/env python3
"""
判定台历 —— 从 claims.yaml 机械生成到期时间表。

为什么需要它: 手写的「13 条集中到期」错了, 实为 12 条。到期条数是可机械导出
的量, 不该由人记 —— 凡手抄必漂移。任何在正文里出现的到期条数, 都应来自本脚本
输出而非记忆。

用法:
  python deadlines.py                  打印台历
  python deadlines.py --write          同时写入 data/schedule.md
  python deadlines.py --asof 2027-01-01  以指定日期计算剩余天数(便于回看)
"""
import argparse
import hashlib
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAIMS = ROOT / "data" / "claims.yaml"
SCHEDULE = ROOT / "data" / "schedule.md"

DEC_ORDER = {"high": 3, "medium": 2, "low": 1}


def load():
    import yaml
    with open(CLAIMS, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build(doc):
    by_due = defaultdict(list)
    excluded = []
    for c in doc["claims"]:
        if c.get("excluded_from_scoring"):
            excluded.append(c)
            continue
        by_due[str(c["due"])].append(c)
    return by_due, excluded


def render(doc, asof, relative=True):
    by_due, excluded = build(doc)
    total = sum(len(v) for v in by_due.values())
    lines = []
    lines.append(f"计分断言 {total} 条 · 排除 {len(excluded)} 条 · "
                 f"表内合计 {total + len(excluded)} 条")
    lines.append("")
    if relative:
        lines.append("| 到期日 | 条数 | 距今 | 断言 | 最高可判定性 |")
        lines.append("|---|---|---|---|---|")
    else:
        lines.append("| 到期日 | 条数 | 断言 | 最高可判定性 |")
        lines.append("|---|---|---|---|")
    for due in sorted(by_due):
        cs = by_due[due]
        top = max((c.get("decisiveness", "low") for c in cs), key=lambda d: DEC_ORDER.get(d, 0))
        ids = " ".join(c["id"] for c in cs)
        if relative:
            days = (date.fromisoformat(due) - asof).days
            span = f"{days} 天" if days >= 0 else f"已过 {-days} 天"
            lines.append(f"| {due} | {len(cs)} | {span} | {ids} | {top} |")
        else:
            lines.append(f"| {due} | {len(cs)} | {ids} | {top} |")
    if excluded:
        lines.append("")
        lines.append("排除条目不进入上表，不参与校准分数: "
                     + " / ".join(f"{c['id']}（{c.get('due')}）" for c in excluded))
    return "\n".join(lines), by_due, excluded, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 data/schedule.md")
    ap.add_argument("--asof", default=None, help="基准日期 YYYY-MM-DD, 默认今天")
    args = ap.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    doc = load()
    body, by_due, excluded, total = render(doc, asof)

    print(body)
    print()
    print("最近三个时点:")
    upcoming = [d for d in sorted(by_due) if d >= asof.isoformat()][:3]
    for d in upcoming:
        print(f"  {d}  {len(by_due[d])} 条  {' '.join(c['id'] for c in by_due[d])}")

    if args.write:
        # 落盘版本不含「距今」列 —— 否则每天都会 diff，CI 就无法用它检查漂移
        body_abs, _, _, _ = render(doc, asof, relative=False)
        digest = hashlib.sha256(CLAIMS.read_bytes()).hexdigest()
        head = (f"# 判定台历\n\n> 本文件由 `deadlines.py --write` 生成，请勿手工编辑。\n"
                f"> claims.yaml sha256 `{digest[:16]}…` · 基准日 {asof.isoformat()}\n"
                f">\n> CI 会重新生成并比对，手抄的到期条数一旦漂移就会变红。\n\n")
        SCHEDULE.write_text(head + body_abs + "\n", encoding="utf-8")
        print(f"\n已写入 {SCHEDULE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
