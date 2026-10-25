#!/usr/bin/env python3
"""
一致性统计 —— 判定者间一致性实验的输出侧。

本实验的主结局不是「这条断言现在成不成立」（13 条里 12 条到期日在未来，
让判定者对未发生的事判 hit/miss 本身不成立），而是**可判定性评级**：

    mechanical  —— 到期日一到、数据齐全，判定无争议
    contested   —— 能判，但口径有争议空间
    unjudgeable —— 无法给出不依赖判定者立场的结论

这是测量工具的清晰度测试（content-validity 类任务），对全部条目今天就能答。
当前判定值作为可选副题，仅对数据已存在的条目有意义。

三个刻意的方法选择（都与「别把数字读错」有关）:

1. **ambiguous / unavailable 不算标度点。** 它们是「拒绝判定」，不是 miss 与
   partial 之间的某一格。名义 kappa 把它们当类别计入（测「是否同样认为无法
   判定」）；有序加权 kappa 把它们成对剔除（强行排序会把拒绝塞进刻度里）。
   报两个数，不合并成一个。

2. **未加权 kappa 会低估一致性。** 三档评级是序数，判 contested 与判
   mechanical 的分歧比判 unjudgeable 轻。故同时报线性加权 kappa。两者差多少
   本身是信息：差大 = 分歧集中在相邻档；差小 = 分歧跨档。

3. **bootstrap 按条目重采样，不按评分重采样。** 条目才是独立单位；同一判定者
   对不同条目的判断共享其个人口径，按评分重采样会把 CI 算窄。

用法:
  python kappa.py ratings_A.csv                      # 自动识别字段
  python kappa.py ratings_A.csv ratings_B.csv        # 两条件并列
  python kappa.py ratings_A.csv --field verdict      # 只看当前判定值
  python kappa.py ratings_A.csv --map _map.json      # 附分层一致性
  python kappa.py --selftest                         # 解析解自测
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = {
    "judgeability": {
        "cats": ["unjudgeable", "contested", "mechanical"],
        "ordered": ["unjudgeable", "contested", "mechanical"],
        "label": "可判定性",
    },
    "verdict": {
        "cats": ["miss", "partial", "hit", "ambiguous", "unavailable"],
        "ordered": ["miss", "partial", "hit"],
        "label": "判定值",
    },
}

CANON = {
    # 可判定性
    "mechanical": "mechanical", "机械": "mechanical", "可机械判定": "mechanical",
    "contested": "contested", "有争议": "contested", "可判但有争议": "contested",
    "unjudgeable": "unjudgeable", "无法判定": "unjudgeable",
    # 判定值
    "hit": "hit", "命中": "hit", "成立": "hit",
    "partial": "partial", "部分": "partial",
    "miss": "miss", "未命中": "miss", "不成立": "miss",
    "ambiguous": "ambiguous", "歧义": "ambiguous",
    "unavailable": "unavailable", "不可得": "unavailable",
}

BANDS = [
    (0.81, "almost perfect"), (0.61, "substantial"), (0.41, "moderate"),
    (0.21, "fair"), (0.00, "slight"), (-1.01, "poor"),
]


# ---------------------------------------------------------------- 数据

def read_ratings(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            item = str(r.get("item", "")).strip()
            judge = str(r.get("judge", "")).strip()
            if not item or not judge:
                continue
            rows.append({
                "item": item,
                "judge": judge,
                "judgeability": CANON.get(str(r.get("judgeability", "")).strip().lower(), ""),
                "verdict": CANON.get(str(r.get("verdict", "")).strip().lower(), ""),
                "confidence": r.get("confidence", ""),
                "reason": str(r.get("reason_code", "")).strip().upper(),
                "note": r.get("note", ""),
            })
    return rows


def pick_field(rows, requested=None):
    if requested:
        return requested
    has_j = sum(1 for r in rows if r["judgeability"])
    has_v = sum(1 for r in rows if r["verdict"])
    return "judgeability" if has_j >= has_v else "verdict"


def build_matrix(rows, field):
    rows = [r for r in rows if r[field]]
    judges = sorted({r["judge"] for r in rows})
    items = sorted({r["item"] for r in rows})
    mat = defaultdict(dict)
    for r in rows:
        mat[r["item"]][r["judge"]] = r[field]
    return items, judges, mat


# ---------------------------------------------------------------- 统计

def _po_pe(a, b, categories):
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = Counter(a), Counter(b)
    pe = sum((pa[c] / n) * (pb[c] / n) for c in categories)
    if pe >= 1.0 - 1e-12:
        return None
    return (po - pe) / (1 - pe)


def cohen(a, b, categories):
    return _po_pe(a, b, categories)


def cohen_weighted(a, b, ordered):
    """线性加权 kappa，仅用有序档成对完备的条目。"""
    pairs = [(x, y) for x, y in zip(a, b) if x in ordered and y in ordered]
    n = len(pairs)
    if n == 0:
        return None
    k = len(ordered)
    idx = {c: i for i, c in enumerate(ordered)}

    def w(x, y):
        return 1 - abs(idx[x] - idx[y]) / (k - 1)

    obs = sum(w(x, y) for x, y in pairs) / n
    pa = Counter(x for x, _ in pairs)
    pb = Counter(y for _, y in pairs)
    exp = sum(w(c1, c2) * (pa[c1] / n) * (pb[c2] / n) for c1 in ordered for c2 in ordered)
    if exp >= 1.0 - 1e-12:
        return None
    return (obs - exp) / (1 - exp)


def fleiss(mat, items, judges, categories):
    """Fleiss' kappa；要求每个条目被同一组判定者评完。"""
    k = len(judges)
    if k < 3:
        return None
    ps, counts = [], Counter()
    for it in items:
        vs = [mat[it].get(j) for j in judges]
        if any(v is None for v in vs):
            return None
        c = Counter(vs)
        counts.update(c)
        ps.append(sum(n * (n - 1) for n in c.values()) / (k * (k - 1)))
    p_bar = sum(ps) / len(ps)
    total = sum(counts.values())
    p_e = sum((counts[c] / total) ** 2 for c in categories)
    if p_e >= 1.0 - 1e-12:
        return None
    return (p_bar - p_e) / (1 - p_e)


def bootstrap_items(items, mat, judges, categories, reps=2000, seed=1):
    """按条目重采样。"""
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        sample = [rng.choice(items) for _ in items]
        if len(judges) >= 3:
            sub = {}
            for i, it in enumerate(sample):
                vs = [mat[it].get(j) for j in judges]
                if any(v is None for v in vs):
                    continue
                sub[f"{it}#{i}"] = dict(zip(judges, vs))
            if len(sub) < 2:
                continue
            v = fleiss(sub, list(sub), judges, categories)
        else:
            a, b = [], []
            for it in sample:
                va, vb = mat[it].get(judges[0]), mat[it].get(judges[1])
                if va is None or vb is None:
                    continue
                a.append(va)
                b.append(vb)
            v = cohen(a, b, categories)
        if v is not None:
            vals.append(v)
    if len(vals) < 50:
        return None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def band(v):
    if v is None:
        return "n/a"
    for cut, name in BANDS:
        if v >= cut:
            return name
    return "poor"


# ---------------------------------------------------------------- 报告

def report(path, rows, mp=None, field=None):
    field = pick_field(rows, field)
    spec = FIELDS[field]
    cats, ordered = spec["cats"], spec["ordered"]
    items, judges, mat = build_matrix(rows, field)

    out = [f"### {path.name}", "", f"字段: `{field}`（{spec['label']}）"]
    out.append(f"条目 {len(items)} · 判定者 {len(judges)} · 有效评分 {sum(1 for r in rows if r[field])} 条")
    missing = sum(1 for it in items for j in judges if mat[it].get(j) is None)
    if missing:
        out.append(f"缺失单元 {missing} 个（该判定者未评该条目）")
    out.append("")

    counts = Counter(mat[it][j] for it in items for j in judges if mat[it].get(j))
    if counts:
        out.append("**分值分布**: " + ", ".join(f"{k}×{v}" for k, v in counts.most_common()))

    if len(judges) == 2:
        a = [mat[i].get(judges[0]) for i in items]
        b = [mat[i].get(judges[1]) for i in items]
        keep = [(x, y) for x, y in zip(a, b) if x and y]
        a, b = [p[0] for p in keep], [p[1] for p in keep]
        kn, kw = cohen(a, b, cats), cohen_weighted(a, b, ordered)
        out.append(f"- Cohen kappa（名义）: **{kn:.3f}** ({band(kn)})" if kn is not None
                   else "- Cohen kappa: n/a（边缘分布退化）")
        out.append(f"- Cohen kappa（线性加权）: **{kw:.3f}** ({band(kw)})" if kw is not None
                   else "- 加权 kappa: n/a")
        if kn is not None and kw is not None:
            out.append(f"- 加权 − 未加权 = {kw - kn:+.3f}"
                       + ("　分歧集中在相邻档" if kw - kn > 0.05 else "　分歧跨档"))
    elif len(judges) >= 3:
        kf = fleiss(mat, items, judges, cats)
        out.append(f"- Fleiss kappa: **{kf:.3f}** ({band(kf)})" if kf is not None
                   else "- Fleiss kappa: n/a（存在缺失单元或类别退化）")
        out.append("")
        out.append("| 判定者对 | 名义 kappa | 加权 kappa |")
        out.append("|---|---|---|")
        for i in range(len(judges)):
            for j in range(i + 1, len(judges)):
                keep = [(mat[it].get(judges[i]), mat[it].get(judges[j])) for it in items]
                keep = [(x, y) for x, y in keep if x and y]
                if not keep:
                    continue
                aa, bb = [p[0] for p in keep], [p[1] for p in keep]
                kn, kw = cohen(aa, bb, cats), cohen_weighted(aa, bb, ordered)
                out.append(f"| {judges[i]} – {judges[j]} | "
                           f"{'n/a' if kn is None else f'{kn:.3f}'} | "
                           f"{'n/a' if kw is None else f'{kw:.3f}'} |")
    else:
        out.append("单一判定者，无法计算一致性。")

    ci = bootstrap_items(items, mat, judges, cats)
    if ci:
        out.append(f"- bootstrap 95% CI（按条目重采样 2000 次）: [{ci[0]:.3f}, {ci[1]:.3f}]"
                   f"　宽度 {ci[1] - ci[0]:.3f}")

    out.append("")
    out.append("**逐条分歧**")
    out.append("")
    dis = [(it, [mat[it].get(j, "—") for j in judges]) for it in items]
    dis = [(it, vs) for it, vs in dis if len(set(vs)) > 1]
    if not dis:
        out.append("无。")
    else:
        out.append("| 条目 | " + " | ".join(judges) + " |")
        out.append("|---" * (len(judges) + 1) + "|")
        for it, vs in dis:
            out.append(f"| {it} | " + " | ".join(vs) + " |")
        out.append("")
        out.append(f"分歧条目 {len(dis)} / {len(items)} = {len(dis) / len(items):.0%}")

    reasons = Counter(r["reason"] for r in rows if r["reason"])
    if reasons:
        out.append("")
        out.append("**理由码分布**: " + ", ".join(f"{k}×{v}" for k, v in reasons.most_common()))

    if mp:
        sub = {m["item"]: m for m in mp["items"]}
        strata = defaultdict(list)
        for it in items:
            strata[sub.get(it, {}).get("claim_type", "unknown")].append(it)
        out.append("")
        out.append("**按断言类型的一致率**（全部判定者给出同一值）")
        out.append("")
        out.append("| 类型 | 条目 | 完全一致 | 一致率 |")
        out.append("|---|---|---|---|")
        for k in sorted(strata, key=lambda x: -len(strata[x])):
            ids = strata[k]
            agree = sum(1 for it in ids
                        if len({mat[it].get(j) for j in judges if mat[it].get(j)}) == 1)
            out.append(f"| {k} | {len(ids)} | {agree} | {agree / len(ids):.0%} |")
        out.append("")
        out.append("> 每层 1–3 条时一致率的分母极小，单条翻转可达 33–100 个百分点。"
                   "故只报原始一致率，不报分层 kappa。")
        ctrl = [it for it, m in sub.items() if m.get("role") == "control"]
        for it in ctrl:
            vs = [mat[it].get(j, "—") for j in judges]
            out.append("")
            out.append(f"**对照项 {it}**: " + " / ".join(vs)
                       + "　→ 多数为 unjudgeable/contested 则对「该条无法操作化」构成外部支持。")

    # 副题: 当前判定值
    vrows = [r for r in rows if r["verdict"]]
    if field == "judgeability" and vrows:
        vc = Counter(r["verdict"] for r in vrows)
        out.append("")
        out.append("**副题（当前判定值）分布**: "
                   + ", ".join(f"{k}×{v}" for k, v in vc.most_common())
                   + "　（仅对数据已存在的条目有意义）")

    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- 自测

def selftest():
    ok = True

    def chk(name, got, want, tol=1e-3):
        nonlocal ok
        good = got is not None and abs(got - want) <= tol
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {name}: got={got!r} want={want}")

    V = FIELDS["verdict"]["cats"]
    VO = FIELDS["verdict"]["ordered"]
    J = FIELDS["judgeability"]["cats"]
    JO = FIELDS["judgeability"]["ordered"]
    print("解析解自测（verdict 字段）")

    a = ["hit"] * 6 + ["partial"] * 2 + ["miss"] * 2
    chk("完全相同 → 1.0", cohen(a, a, V), 1.0)

    b1 = ["hit"] * 5 + ["miss"] * 5
    b2 = ["hit"] * 4 + ["miss"] * 6
    chk("已知 0.8", cohen(b1, b2, V), 0.8)

    c1 = ["hit", "hit", "partial", "partial", "miss"]
    c2 = ["hit", "partial", "partial", "miss", "miss"]
    chk("未加权 12/34", cohen(c1, c2, V), 0.411765)
    chk("线性加权 24/44", cohen_weighted(c1, c2, VO), 0.545455)
    ok &= cohen_weighted(c1, c2, VO) > cohen(c1, c2, V)

    print("解析解自测（judgeability 字段，三档）")
    # 同构: mechanical 相当于 hit, contested 相当于 partial, unjudgeable 相当于 miss
    j1 = ["mechanical", "mechanical", "contested", "contested", "unjudgeable"]
    j2 = ["mechanical", "contested", "contested", "unjudgeable", "unjudgeable"]
    chk("未加权与 verdict 同构", cohen(j1, j2, J), 0.411765)
    chk("加权与 verdict 同构", cohen_weighted(j1, j2, JO), 0.545455)

    print("Fleiss 与退化情形")
    items = [f"I{i}" for i in range(6)]
    mat = {it: {"j1": "mechanical", "j2": "mechanical", "j3": "mechanical"} for it in items[:3]}
    mat.update({it: {"j1": "contested", "j2": "contested", "j3": "contested"} for it in items[3:]})
    chk("Fleiss 完全一致且非退化 → 1.0",
        fleiss(mat, items, ["j1", "j2", "j3"], J), 1.0)

    deg = {it: {"j1": "mechanical", "j2": "mechanical", "j3": "mechanical"} for it in items}
    got = fleiss(deg, items, ["j1", "j2", "j3"], J)
    ok &= got is None
    print(f"  {'PASS' if got is None else 'FAIL'}  单类别退化 → None: got={got!r}")

    rng = random.Random(0)
    r1 = [rng.choice(JO) for _ in range(400)]
    r2 = [rng.choice(JO) for _ in range(400)]
    kv = cohen(r1, r2, J)
    ok &= abs(kv) < 0.15
    print(f"  参考  独立随机 400 条: kappa={kv:+.3f}（应接近 0）")

    print("自测", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="评分 CSV")
    ap.add_argument("--map", default=None, help="packet_gen 产出的 _map.json")
    ap.add_argument("--field", default=None, choices=list(FIELDS))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.files:
        ap.error("需要至少一个评分 CSV，或用 --selftest")

    mp = json.loads(Path(args.map).read_text(encoding="utf-8")) if args.map else None
    blocks = []
    for f in args.files:
        rows = read_ratings(Path(f))
        if not any(r["judgeability"] or r["verdict"] for r in rows):
            print(f"跳过 {f}（无可识别评分）")
            continue
        blocks.append(report(Path(f), rows, mp, args.field))
    if not blocks:
        sys.exit("没有任何可用评分")
    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
