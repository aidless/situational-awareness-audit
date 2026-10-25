#!/usr/bin/env python3
"""C10 分析端：从试次 JSONL 出判定。

关键设计约束（全部来自已封存的 C10 协议，不得放松）：

1. 判定用**被试层面聚合值**。同一被试做多题不独立，若把全部试次合并取中位数，
   多做几题的被试会被加权。故先在被试内取中位数，再跨被试取中位数。
2. 方向是 **in_range** —— 过快与过慢同样破坏作者的换算，不是单向。
3. 任务类别间若差异超过 3 倍，「人类思维速率」须按任务类型拆分（协议明文）。
4. 离散裁决: 四分位距 > 中位数 → ambiguous（说明这不是一个稳定的类量）。
5. **任何 synthetic 记录在场时拒绝输出判定**。这条是硬闸门：模拟数据只能验管线。

用法:
    python analyze.py data/trials.jsonl
    python analyze.py data/trials.jsonl --json
    python analyze.py --self-test
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
from pathlib import Path

HIT = (50.0, 200.0)
PARTIAL_OUTER = (35.0, 285.0)  # [35,50) ∪ (200,285]
CATEGORY_SPLIT_RATIO = 3.0
BOOTSTRAP_N = 10_000
SEED = 20261024


def verdict_of(median: float) -> str:
    lo, hi = HIT
    if lo <= median <= hi:
        return "hit"
    plo, phi = PARTIAL_OUTER
    if plo <= median < lo or hi < median <= phi:
        return "partial"
    return "miss"


def quartiles(xs: list[float]) -> tuple[float, float, float]:
    s = sorted(xs)
    if len(s) == 1:
        return s[0], s[0], s[0]
    q = st.quantiles(s, n=4, method="inclusive")
    return q[0], st.median(s), q[2]


def participant_medians(trials: list[dict]) -> dict[str, float]:
    """先在被试内取中位数 —— 这一步是整个脚本最重要的正确性约束。"""
    by_p: dict[str, list[float]] = {}
    for t in trials:
        if t.get("r_active") is None:
            continue
        by_p.setdefault(t["participant"], []).append(float(t["r_active"]))
    return {p: st.median(v) for p, v in by_p.items() if v}


def bootstrap_ci(values: list[float], n: int = BOOTSTRAP_N, seed: int = SEED) -> tuple[float, float]:
    if len(values) < 2:
        v = values[0] if values else float("nan")
        return v, v
    rng = random.Random(seed)
    meds = []
    for _ in range(n):
        meds.append(st.median([rng.choice(values) for _ in values]))
    meds.sort()
    return meds[int(0.025 * n)], meds[int(0.975 * n) - 1]


def analyze(trials: list[dict]) -> dict:
    synthetic = [t for t in trials if t.get("synthetic")]
    real = [t for t in trials if not t.get("synthetic")]

    out: dict = {
        "n_trials": len(real),
        "n_trials_synthetic_excluded": len(synthetic),
        "n_participants": 0,
        "threshold_band": list(HIT),
        "verdict": "pending",
        "reason": "",
    }

    if synthetic:
        out["reason"] = (
            f"存在 {len(synthetic)} 条 synthetic 记录，本文件只用于验证管线，"
            "拒绝输出判定。这是硬闸门，不提供绕过参数。"
        )
        return out

    if not real:
        out["reason"] = "无真实试次"
        return out

    pm = participant_medians(real)
    out["n_participants"] = len(pm)
    if len(pm) < 12:
        out["reason"] = f"被试仅 {len(pm)} 人，低于协议 S1 要求的 12 人；以下数值仅供参考，不构成判定。"

    vals = list(pm.values())
    q1, med, q3 = quartiles(vals)
    iqr = q3 - q1
    lo, hi = bootstrap_ci(vals)

    out.update(
        median_r=round(med, 2),
        q1=round(q1, 2),
        q3=round(q3, 2),
        iqr=round(iqr, 2),
        ci95=[round(lo, 2), round(hi, 2)],
        unit="tokens/min (participant-median aggregated)",
    )

    if len(pm) >= 12:
        if iqr > med:
            out["verdict"] = "ambiguous"
            out["reason"] = (
                f"四分位距 {iqr:.1f} 超过中位数 {med:.1f} —— 『人类思维速率』不是一个稳定的类量。"
            )
        else:
            out["verdict"] = verdict_of(med)
            out["reason"] = f"被试层面中位数 {med:.1f} 落在判定带的哪一档。"
    else:
        out["verdict"] = "pending"

    # 分任务类别
    by_cat: dict[str, list[float]] = {}
    for t in real:
        if t.get("r_active") is not None:
            by_cat.setdefault(t["category"], []).append(float(t["r_active"]))
    cat_stats = {}
    for c, v in by_cat.items():
        cq1, cm, cq3 = quartiles(v)
        cat_stats[c] = {"n": len(v), "median": round(cm, 1), "q1": round(cq1, 1), "q3": round(cq3, 1)}
    out["by_category"] = cat_stats

    if len(cat_stats) >= 2:
        meds = [v["median"] for v in cat_stats.values() if v["median"] > 0]
        if meds:
            ratio = max(meds) / min(meds)
            out["category_max_ratio"] = round(ratio, 2)
            out["category_split_required"] = ratio > CATEGORY_SPLIT_RATIO

    # 下界（用 T_total 而非 T_active）
    lb = [float(t["r_total"]) for t in real if t.get("r_total") is not None]
    if lb:
        out["median_r_lower_bound"] = round(st.median(lb), 1)

    return out


def render(res: dict) -> str:
    lines = []
    lines.append("C10 · 人类思维速率（tokens/min）")
    lines.append("=" * 46)
    lines.append(f"试次 {res['n_trials']}  被试 {res['n_participants']}  判定带 {res['threshold_band']}")
    if res.get("n_trials_synthetic_excluded"):
        lines.append(f"剔除 synthetic 记录 {res['n_trials_synthetic_excluded']} 条")

    if res["verdict"] == "pending" or "median_r" not in res:
        lines.append("")
        lines.append(f"判定: {res['verdict'].upper()}")
        lines.append(f"原因: {res['reason']}")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"中位数  {res['median_r']:.1f}")
    lines.append(f"Q1–Q3   {res['q1']:.1f} – {res['q3']:.1f}   (IQR {res['iqr']:.1f})")
    lines.append(f"95% CI  [{res['ci95'][0]:.1f}, {res['ci95'][1]:.1f}]  (bootstrap, 按被试聚类)")
    if "median_r_lower_bound" in res:
        lines.append(f"下界    {res['median_r_lower_bound']:.1f}  (用 T_total，含停顿)")
    lines.append("")

    if res.get("by_category"):
        lines.append("分任务类别:")
        for c, v in sorted(res["by_category"].items()):
            lines.append(f"  {c:<10} n={v['n']:<3} 中位数 {v['median']:<8.1f} (Q1 {v['q1']:.1f}, Q3 {v['q3']:.1f})")
        if res.get("category_split_required"):
            lines.append(
                f"  ⚠ 类别间最大比值 {res['category_max_ratio']}× > {CATEGORY_SPLIT_RATIO}× —— "
                "按协议，『人类思维速率』须按任务类型拆分报告，不得作为单一数字引用。"
            )
        lines.append("")

    lines.append(f"判定: {res['verdict'].upper()}")
    lines.append(f"原因: {res['reason']}")
    return "\n".join(lines)


def self_test() -> int:
    ok = True

    def chk(name: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {name}: {got!r}" + ("" if good else f" 期望 {want!r}"))

    print("判定带边界")
    chk("49.9", verdict_of(49.9), "partial")
    chk("50", verdict_of(50), "hit")
    chk("200", verdict_of(200), "hit")
    chk("201", verdict_of(201), "partial")
    chk("34.9", verdict_of(34.9), "miss")
    chk("285", verdict_of(285), "partial")
    chk("286", verdict_of(286), "miss")

    print("一致性: 唯一分母")
    # 若合并全部试次取中位数，多做几题的被试会被加权 —— 该断言即为此而设
    fake = (
        [{"participant": "P1", "category": "analytic", "r_active": 60.0, "r_total": 55.0}] * 10
        + [{"participant": "P2", "category": "analytic", "r_active": 400.0, "r_total": 380.0}] * 2
    )
    pm = participant_medians(fake)
    chk("被试层面中位数(P1=60,P2=400)", st.median(list(pm.values())), 230.0)
    chk("合并试次中位数(会被 P1 加权)", st.median([f["r_active"] for f in fake]), 60.0)
    print("  → 两者相差 3.8 倍，故必须用被试层面聚合；合并口径会把结果拉向 hit。")

    print("synthetic 硬闸门")
    res = analyze([{"participant": "S00", "category": "analytic", "r_active": 100.0, "synthetic": True}])
    chk("synthetic 在场 → pending", res["verdict"], "pending")
    chk("不产出中位数", "median_r" in res, False)

    print("样本量闸门")
    small = [{"participant": f"P{i}", "category": "analytic", "r_active": 100.0, "r_total": 90.0} for i in range(5)]
    chk("5 人 → pending", analyze(small)["verdict"], "pending")

    print("离散裁决")
    wide = []
    for i in range(12):
        v = 20.0 if i < 4 else (100.0 if i < 8 else 900.0)
        wide.append({"participant": f"P{i}", "category": "analytic", "r_active": v, "r_total": v})
    chk("离散过大 → ambiguous", analyze(wide)["verdict"], "ambiguous")

    print()
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("需要试次 JSONL 路径，或 --self-test")

    trials = [json.loads(l) for l in Path(args.path).read_text(encoding="utf-8").splitlines() if l.strip()]
    res = analyze(trials)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
