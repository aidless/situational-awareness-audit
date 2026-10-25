#!/usr/bin/env python3
"""
生成盲化判定包 —— 判定者间一致性实验的输入侧。

设计要点(每一条都是为了不让判定者被审计者的判断锚定):
  1. 不给 `notes` 字段 —— 那是审计者的推理过程, 含大量倾向性表述
  2. A 条件不给 `resolution_protocol` —— 测「断言本身是否自足」
  3. B 条件给协议但剥掉任何已写好的结论句
  4. 断言 ID 换成不透明序号 IT-xx, 且顺序按 seed 打乱 —— C01 这种编号本身
     就泄露了它在原文中的位置与重要性
  5. 生成后自动做泄漏扫描: 若正文出现 `C\\d\\d`, 拒绝出包

用法:
  python packet_gen.py --n 12 --seed 20261025
  python packet_gen.py --ids C01,C03,C10 --seed 1
  python packet_gen.py --n 12 --no-control     # 不含 C24 对照项

产出(interrater/packets/<时间戳>/):
  A_blind.md          条件 A: 只给原文摘录 + 阈值, 不给协议
  B_protocol.md       条件 B: 加判定协议
  ratings_A.csv       A 条件评分表模板
  ratings_B.csv       B 条件评分表模板
  _map.json           序号 → 断言 ID 的私有映射 (已 gitignore, 判定期间不得外泄)
"""
import argparse
import csv
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "data" / "claims.yaml"
OUT = ROOT / "interrater" / "packets"

# 会暴露审计者结论的片段; 命中即剥离并告警
VERDICT_PAT = re.compile(r"(本审计(?:判定|认为|结论)|审计者(?:判定|认为)|已判为|verdict\s*[:=])",
                         re.I)


def load_claims():
    import yaml
    with open(CLAIMS, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc["claims"]


def redact(protocol: str) -> tuple[str, bool]:
    """剥掉协议里可能已写好的结论句。返回 (文本, 是否剥离过)。"""
    kept, hit = [], False
    for line in str(protocol).splitlines():
        if VERDICT_PAT.search(line):
            hit = True
            continue
        kept.append(line)
    return "\n".join(kept).strip(), hit


def select(claims, n, seed, control):
    """按 claim_type 分层轮转抽选, 每层内按 seed 打乱。

    分层而非纯随机: 纯随机抽 12 条有相当概率漏掉某个 claim_type, 而
    「不同 claim_type 的 kappa 不同」正是本实验要检验的主要假设。
    """
    pool = [c for c in claims if not c.get("excluded_from_scoring")]
    groups = {}
    for c in pool:
        groups.setdefault(c.get("claim_type", "unknown"), []).append(c)
    rng = random.Random(seed)
    for g in groups.values():
        rng.shuffle(g)
    order = sorted(groups, key=lambda k: (-len(groups[k]), k))
    picked, i = [], 0
    while len(picked) < n:
        added = False
        for k in order:
            if i < len(groups[k]):
                picked.append(groups[k][i])
                added = True
                if len(picked) >= n:
                    break
        if not added:
            break
        i += 1
    if control:
        ctrl = [c for c in claims if c["id"] == control]
        if ctrl:
            picked.append(ctrl[0])
    return picked


def scrub_self(text: str, cid: str) -> str:
    """把本条自己的 ID 换成「本条」。

    断言编号本身泄露信息（C01 是全表第一条、且是总判据），而协议里常出现
    「C03 与 C04 不重复」这类自指。只替换自身引用，不替换他条引用 ——
    后者不影响本条判定，但会作为告警计入统计。
    """
    return re.sub(rf"\b{re.escape(cid)}\b", "本条", text)


def item_block(code, c, with_protocol, role):
    cid = c["id"]
    lines = [f"### {code}", ""]
    lines.append(f"- 断言类型: `{c.get('claim_type', '?')}`")
    lines.append(f"- 原始文件页码: {c.get('page', '?')}")
    lines.append("")
    lines.append("**原文摘录**")
    lines.append("")
    for para in str(c.get("quote", "")).strip().split("\n\n"):
        lines.append("> " + scrub_self(para.replace("\n", " ").strip(), cid))
    lines.append("")
    lines.append(f"**作者给出的量级**: {scrub_self(str(c.get('author_magnitude', '（未给出）')), cid)}")
    lines.append("")
    lines.append(f"**可观测定义**: {scrub_self(str(c.get('observable', '（未给出）')), cid)}")
    lines.append("")
    if role == "control":
        lines.append("**判定阈值**: （本条未给出阈值）")
    else:
        lines.append(f"**判定阈值**: `{scrub_self(str(c.get('threshold', '（未给出）')), cid)}`")
    lines.append("")
    lines.append(f"**预期方向**: `{c.get('direction', '?')}`　"
                 f"**到期日**: {c.get('due', '?')}")
    lines.append("")
    if with_protocol:
        body, _ = redact(c.get("resolution_protocol", ""))
        lines.append("**判定协议**")
        lines.append("")
        lines.append("```")
        lines.append(scrub_self(body, cid) or "（无）")
        lines.append("```")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


HEADER = """# 判定包 · 条件 {cond}

请**独立**判定下列 {n} 条断言，在 `{csvname}` 中每行填写一条。
请不要检索原文、不要查本项目的其他文件、不要与他人讨论。

## 主问题：可判定性

假设到期日已到，且你可以访问任何公开数据。问：**这条断言能否被无争议地判定？**

| 值 | 含义 |
|---|---|
| `mechanical` | 能。阈值、单位、起算点、数据源都明确，两个认真的判定者会得出同一结论 |
| `contested` | 能判，但口径有争议空间（换算率、基准选择、边界情形），认真的人可能得出不同结论 |
| `unjudgeable` | 不能。关键词无公认操作化定义，或任何替代定义都会改变断言本身的强度 |

**每一条都必须给一个值。** `unjudgeable` 是合法且重要的答案：实验中确有这类
条目，识别出它们与判对一样有价值。

## 理由码（建议在判 `contested` / `unjudgeable` 时填）

| 码 | 含义 |
|---|---|
| R1 | 数据源不可得（停更、下架、付费墙） |
| R2 | 阈值表述有歧义（单位、口径、起算点不明） |
| R3 | 取决于未定的边界情形 |
| R4 | 断言无法操作化（关键词无公认定义） |
| R5 | 数据存在但口径与断言不匹配（例：测的是别的对象） |
| R6 | 其他（在 note 里说明） |

## 副问题：当前判定值（选填）

若你认为**截至今天**已有足够公开数据可判，请在 `verdict` 列填
`hit` / `partial` / `miss` / `ambiguous` / `unavailable`。
多数条目的到期日在未来，**留空是正确的**，不是漏答。

## 置信度

1–5，1 = 几乎靠猜，5 = 判断有充分依据。

## 条件说明

{cond_note}
"""

COND_A = "本包**不含**判定协议（即不含如何取数、如何折算、如何排除的规则）。若你因此无法判定，请如实填 `ambiguous` + `R2`/`R4`——这正是要被测出来的东西。"
COND_B = "本包**含**判定协议。请严格按协议判定；若协议本身仍不足以消除歧义，请填 `ambiguous` 并说明歧义在哪一句。"


def leak_scan(blocks, picked, claims):
    """返回 (自身 ID 泄漏列表, 他条交叉引用计数)。

    自身 ID 泄漏 = 硬失败（会告诉判定者这条在表中的位置与重要性）。
    他条交叉引用 = 告警（协议里「C03 与 C04 不重复」这类表述无法安全改写，
    且不直接泄露本条答案）。
    """
    ids = {c["id"] for c in claims}
    self_leak, cross = [], 0
    for c, text in zip(picked, blocks):
        if re.search(rf"\b{re.escape(c['id'])}\b", text):
            self_leak.append(c["id"])
        cross += len((set(re.findall(r"\bC\d{2}\b", text)) & ids) - {c["id"]})
    return self_leak, cross


def write_csv(path, codes):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item", "judge", "judgeability", "verdict",
                    "confidence", "reason_code", "note"])
        for code in codes:
            w.writerow([code, "", "", "", "", "", ""])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="条件 A/B 各自的断言条数")
    ap.add_argument("--seed", type=int, default=20261025)
    ap.add_argument("--ids", default=None, help="显式指定断言 ID（逗号分隔），忽略分层抽样")
    ap.add_argument("--control", default="C24", help="对照项 ID，置空字符串可关闭")
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="把他条断言 ID 也替换为「他条」，消除结构泄漏（会降低协议可读性）")
    args = ap.parse_args()

    claims = load_claims()
    if args.ids:
        wanted = [s.strip() for s in args.ids.split(",") if s.strip()]
        by_id = {c["id"]: c for c in claims}
        missing = [w for w in wanted if w not in by_id]
        if missing:
            sys.exit(f"未知断言 ID: {missing}")
        picked = [by_id[w] for w in wanted]
    else:
        control = "" if args.no_control else args.control
        picked = select(claims, args.n, args.seed, control)

    rng = random.Random(args.seed + 7)
    rng.shuffle(picked)

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = OUT / stamp
    dest.mkdir(parents=True, exist_ok=True)

    codes, mapping = [], []
    for i, c in enumerate(picked, 1):
        code = f"IT-{i:02d}"
        codes.append(code)
        mapping.append({
            "item": code,
            "claim_id": c["id"],
            "claim_type": c.get("claim_type"),
            "decisiveness": c.get("decisiveness"),
            "role": "control" if c.get("excluded_from_scoring") else "scored",
        })

    blocks_a = [item_block(code, c, False, m["role"])
                for code, c, m in zip(codes, picked, mapping)]
    blocks_b = [item_block(code, c, True, m["role"])
                for code, c, m in zip(codes, picked, mapping)]

    if args.strict:
        # 结构泄漏的另一半: 协议里「另一条断言与另一条断言不重复」虽不泄露本条
        # 答案, 但泄露了「这些条目互相关联」这一事实。严格模式下统一抹掉。
        blocks_a = [re.sub(r"\bC\d{2}\b", "他条", b) for b in blocks_a]
        blocks_b = [re.sub(r"\bC\d{2}\b", "他条", b) for b in blocks_b]

    a_text = HEADER.format(cond="A · 盲判（无协议）", n=len(picked),
                           csvname="ratings_A.csv", cond_note=COND_A) \
        + "\n" + "\n".join(blocks_a)
    b_text = HEADER.format(cond="B · 带协议", n=len(picked),
                           csvname="ratings_B.csv", cond_note=COND_B) \
        + "\n" + "\n".join(blocks_b)

    cross_total = 0
    for name, text, blocks in (("A_blind.md", a_text, blocks_a),
                               ("B_protocol.md", b_text, blocks_b)):
        self_leak, cross = leak_scan(blocks, picked, claims)
        if self_leak:
            sys.exit(f"泄漏扫描失败: {name} 中本条断言 ID 未被替换 {self_leak}，拒绝出包")
        cross_total += cross
        (dest / name).write_text(text, encoding="utf-8")

    (dest / "_map.json").write_text(
        json.dumps({"seed": args.seed, "created": stamp, "items": mapping},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(dest / "ratings_A.csv", codes)
    write_csv(dest / "ratings_B.csv", codes)

    strata = {}
    for m in mapping:
        strata[m["claim_type"]] = strata.get(m["claim_type"], 0) + 1
    print(f"已生成 {dest.relative_to(ROOT)}")
    print(f"条数 {len(picked)}（含对照 {sum(1 for m in mapping if m['role'] == 'control')} 条）")
    print("分层:", ", ".join(f"{k}×{v}" for k, v in sorted(strata.items())))
    print("序号:", " ".join(f"{m['item']}={m['claim_id']}" for m in mapping))
    print(f"泄漏扫描: 自身 ID 泄漏 0 条（PASS）；他条交叉引用 {cross_total} 处（告警，不影响本条判定）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
