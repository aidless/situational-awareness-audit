#!/usr/bin/env python3
"""
端到端自测 —— 用合成判定者验证「实验能不能测出我想测的东西」。

这不是在验证脚本写得对不对（那是 kappa.py --selftest 的事），而是在验证
**实验设计有没有判别力**：如果真实判定者按预注册预期分化（纯数字类一致、
需自造定义类不一致），这套流程能不能把分化显示出来？若连合成的、强弱已知的
分化都显示不出来，真实数据出来也无从解读。

合成数据只写入内存与报告字符串，不落盘到 interrater/ratings/，报告头写明 SYNTHETIC。

用法: python selftest_pipeline.py [packet_dir]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kappa  # noqa: E402

# 预注册假设: 这两个类型应当高一致（数据是别人发布的标准序列）
CLEAN = {"quantitative_trend", "capability_gain_decomposition"}
# 这两个类型应当低一致（判定前提是审计者自造的定义）
MURKY = {"conversion_factor", "methodological_recommendation"}

ROTATE = ["mechanical", "contested", "unjudgeable"]


def synth_ratings(items, judges):
    """按类型注入已知强度的分歧。

    CLEAN: 三人同值 mechanical（完全一致）
    MURKY: 三人轮转三档（完全不一致）
    其余: 两人 contested、一人 unjudgeable（部分一致）
    """
    rows = []
    for it in items:
        t = it["claim_type"]
        if t in CLEAN:
            vals = ["mechanical"] * len(judges)
        elif t in MURKY:
            vals = [ROTATE[i % 3] for i in range(len(judges))]
        else:
            vals = ["contested"] * (len(judges) - 1) + ["unjudgeable"]
        for j, v in zip(judges, vals):
            rows.append({"item": it["item"], "judge": j, "verdict": "",
                         "judgeability": v, "confidence": "3",
                         "reason": "R4" if v == "unjudgeable" else "", "note": "SYNTHETIC"})
    return rows


def stratum_agreement(items, rows, judges):
    mat = {}
    for r in rows:
        mat.setdefault(r["item"], {})[r["judge"]] = r["judgeability"]
    out = {}
    for it in items:
        vs = {mat[it["item"]].get(j) for j in judges}
        out.setdefault(it["claim_type"], []).append(1 if len(vs) == 1 else 0)
    return {k: sum(v) / len(v) for k, v in out.items()}


def main():
    root = Path(__file__).resolve().parent
    pdir = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((root / "packets").glob("*/"))[-1]
    mp = json.loads((pdir / "_map.json").read_text(encoding="utf-8"))
    items = mp["items"]
    judges = ["J-syn1", "J-syn2", "J-syn3"]

    rows = synth_ratings(items, judges)
    agree = stratum_agreement(items, rows, judges)

    print("=" * 66)
    print("SYNTHETIC —— 以下数据由脚本生成，不是人类判定，不得用于任何实际结论")
    print("=" * 66)
    print(f"包: {pdir.name} · 条目 {len(items)} · 合成判定者 {len(judges)}")
    print()
    print(f"{'断言类型':34} {'应然':6} {'实测一致率'}")
    for t in sorted(agree, key=lambda x: -agree[x]):
        want = "高" if t in CLEAN else ("低" if t in MURKY else "中")
        print(f"{t:34} {want:6} {agree[t]:.0%}")

    out = kappa.report(Path("SYNTHETIC.csv"), rows, mp)
    print()
    print(out)

    clean = [v for k, v in agree.items() if k in CLEAN]
    murky = [v for k, v in agree.items() if k in MURKY]
    ok = bool(clean) and bool(murky) and min(clean) > max(murky)
    print()
    print(f"判别力检查: CLEAN 最低 {min(clean):.0%} vs MURKY 最高 {max(murky):.0%} → "
          f"{'PASS（流程能显示分化）' if ok else 'FAIL（流程看不出分化，设计需重做）'}")

    # 对照项检查: 合成数据里对照项被三档轮转, 应被判为「不一致」
    ctrl = [i["item"] for i in items if i.get("role") == "control"]
    if ctrl:
        vs = {r["judgeability"] for r in rows if r["item"] == ctrl[0]}
        print(f"对照项 {ctrl[0]}: 三人取值 {sorted(vs)} → "
              f"{'不一致（流程可暴露该条的可判定性争议）' if len(vs) > 1 else '一致（合成数据未注入分歧）'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
