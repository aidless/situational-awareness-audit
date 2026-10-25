#!/usr/bin/env python3
"""
Situational Awareness 断言审计 —— 结构校验 / 封存 / 评分

用法:
  python audit.py validate            结构与完整性校验(封存前必跑)
  python audit.py seal                计算 sha256 封存(要求全部阈值已填)
  python audit.py verify              校验封存文件与当前 claims.yaml 是否一致
  python audit.py score               读取 data/scores/<quarter>.json 输出校准报告
  python audit.py brief               生成「阈值待锁定」清单(按可判定性排序)

设计约束:
  - 阈值一旦封存不得修改; 修改必须建立新版本 claims_v2.yaml 并重新封存
  - 评分脚本不判断真值, 只按已封存的阈值做机械比对, 避免事后解释
"""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAIMS = ROOT / "data" / "claims.yaml"
SEAL = ROOT / "data" / "seal.json"
SCORES = ROOT / "data" / "scores"

REQUIRED = ["id", "section", "page", "quote", "claim_type",
            "author_magnitude", "observable", "threshold",
            "direction", "due", "decisiveness", "notes"]
VALID_DIR = {">=", "<=", "==", ">", "<", "in_range"}
VALID_DEC = {"high", "medium", "low"}
# in_range 类阈值必须在 threshold 字段内给出闭区间, 且必须写明双向失配的后果
RANGE_PAT = re.compile(r"\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]")


def load_yaml(path):
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("需要 pyyaml: 使用 ~/.workbuddy/binaries/python/envs/default/bin/python 运行")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_pdf_digest():
    """原文 PDF 的 sha256; 不在时返回 None。

    原文副本不随仓库分发(版权原因, 见 PROVENANCE.md), 故此处不得抛异常 ——
    否则新克隆的仓库一跑 seal 就崩。封存的核心是 claims_sha256, 原文哈希只是
    给持有副本的人一个自校验锚点。
    """
    pdf = ROOT / "raw" / "sa_full.pdf"
    if not pdf.exists():
        return None
    try:
        return sha256_of(pdf)
    except OSError:
        return None


def cmd_validate(doc):
    claims = doc["claims"]
    errors, warns = [], []

    if len({c["id"] for c in claims}) != len(claims):
        errors.append("断言 ID 存在重复")

    for c in claims:
        cid = c.get("id", "?")
        for k in REQUIRED:
            if k not in c:
                errors.append(f"{cid}: 缺字段 {k}")
        if c.get("direction") not in VALID_DIR:
            errors.append(f"{cid}: direction 非法 {c.get('direction')!r}")
        if c.get("direction") == "in_range":
            th = str(c.get("threshold", ""))
            if not RANGE_PAT.search(th):
                errors.append(f"{cid}: direction=in_range 时 threshold 必须含闭区间 [lo, hi]")
            elif "hit" not in str(c.get("resolution_protocol", "")).lower():
                warns.append(f"{cid}: in_range 类断言建议在 resolution_protocol 写明四档判据")
        if c.get("decisiveness") not in VALID_DEC:
            errors.append(f"{cid}: decisiveness 非法 {c.get('decisiveness')!r}")
        try:
            datetime.strptime(str(c.get("due")), "%Y-%m-%d")
        except (ValueError, TypeError):
            errors.append(f"{cid}: due 不是 YYYY-MM-DD")
        if not isinstance(c.get("page"), int):
            errors.append(f"{cid}: page 必须是整数页码")
        if c.get("claim_type") == "conversion_factor" and not c.get("source_tier"):
            warns.append(f"{cid}: 折算率类断言建议补 source_tier (A/B/C/D)")

        # excluded 类断言: 不进入校准分数, 但必须写明排除理由
        if c.get("excluded_from_scoring"):
            if not str(c.get("exclusion_reason", "")).strip():
                errors.append(f"{cid}: excluded_from_scoring=true 时必须写 exclusion_reason")
            elif not any(k in str(c.get("resolution_protocol", ""))
                         for k in ("排除", "不判", "EXCLUDED")):
                warns.append(f"{cid}: 排除类断言建议在 resolution_protocol 写明为何不判")

    pending = [c["id"] for c in claims if not str(c.get("threshold", "")).strip()]
    verdict = "PASS" if not errors else "FAIL"

    print(f"结构校验: {verdict}  断言 {len(claims)} 条")
    for e in errors:
        print(f"  [错误] {e}")
    for w in warns:
        print(f"  [提示] {w}")
    if pending:
        print(f"  阈值待锁定 {len(pending)} 条: {', '.join(pending)}")
    print_field(doc)
    return 0 if not errors else 1


def print_field(doc):
    claims = doc["claims"]
    print("\n分布:")
    for label, key in (("部分", "section"), ("类型", "claim_type"),
                       ("可判定性", "decisiveness"), ("到期年", None)):
        cnt = Counter(c["due"][:4] if key is None else c[key] for c in claims)
        print(f"  {label}: " + "  ".join(f"{k}={v}" for k, v in sorted(cnt.items())))


def cmd_brief(doc):
    claims = doc["claims"]
    pending = [c for c in claims if not str(c.get("threshold", "")).strip()]
    order = {"high": 0, "medium": 1, "low": 2}
    pending.sort(key=lambda c: (c["due"], order.get(c["decisiveness"], 9)))
    print(f"待锁定阈值 {len(pending)} 条 (按到期日升序 / 可判定性降序)\n")
    for c in pending:
        print(f"{c['id']}  p.{c['page']}  due={c['due']}  {c['decisiveness']}")
        print(f"     主张: {c['author_magnitude']}")
        print(f"     观测量: {c['observable']}")
        print()
    return 0


def cmd_seal(doc):
    pending = [c["id"] for c in doc["claims"] if not str(c.get("threshold", "")).strip()]
    if pending:
        print(f"拒绝封存: {len(pending)} 条阈值未填 -> {', '.join(pending)}")
        return 1
    digest = sha256_of(CLAIMS)
    record = {
        "sealed_at": datetime.now().isoformat(timespec="seconds"),
        "claims_file": CLAIMS.name,
        "claims_sha256": digest,
        "claim_count": len(doc["claims"]),
    }
    src = source_pdf_digest()
    if src:
        record["source_pdf_sha256"] = src
    else:
        record["source_pdf_sha256"] = None
        record["source_pdf_note"] = (
            "原文 PDF 不在 raw/sa_full.pdf; 本仓库不含原文(见 PROVENANCE.md)。"
            "持有副本者请自行核对 sha256 = "
            "68735f1b5a3d30fb276e42493389d016d4afb46fef922b44ed7ebf7ad55189d3"
        )
    SEAL.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已封存: {SEAL}")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(doc):
    if not SEAL.exists():
        print("未找到封存文件, 请先执行 seal")
        return 1
    record = json.loads(SEAL.read_text(encoding="utf-8"))
    ok = record["claims_sha256"] == sha256_of(CLAIMS)
    print("封存一致性: " + ("PASS" if ok else "FAIL —— 断言表在封存后被修改"))
    return 0 if ok else 1


def cmd_score(doc):
    if not SEAL.exists():
        print("未封存即评分会破坏预注册性质, 中止")
        return 1
    files = sorted(SCORES.glob("*.json")) if SCORES.exists() else []
    if not files:
        print("data/scores/ 下无评分文件")
        return 0
    by_id = {c["id"]: c for c in doc["claims"]}
    tally = defaultdict(lambda: [0, 0, 0])
    per_claim = {}
    excluded = []          # 结构上不可判, 不进分母
    ambiguous = []         # 本可判但证据不足, 也不进分母, 但单独统计
    for f in files:
        for s in json.loads(f.read_text(encoding="utf-8")).get("scores", []):
            c = by_id.get(s["id"])
            if not c:
                continue
            v = str(s["verdict"]).lower()
            # excluded 与 ambiguous 都不能当成 miss —— 那会把"没判"记成"判错"
            if v == "excluded" or c.get("excluded_from_scoring"):
                excluded.append(s["id"])
                continue
            if v == "ambiguous":
                ambiguous.append(s["id"])
                continue
            hit = v == "hit"
            partial = v == "partial"
            bucket = tally[c["claim_type"]]
            bucket[0] += 1 if hit else 0
            bucket[1] += 1 if partial else 0
            bucket[2] += 1
            per_claim.setdefault(s["id"], []).append(v)
    print(f"评分文件 {len(files)} 份\n按类型命中率 (hit / partial / 计分条数):")
    for t, (h, p_, n) in sorted(tally.items()):
        print(f"  {t:32s} {h} / {p_} / {n}" + (f"   hit={h / n:.0%}" if n else ""))
    total_h = sum(v[0] for v in tally.values())
    total_p = sum(v[1] for v in tally.values())
    total_n = sum(v[2] for v in tally.values())
    if total_n:
        print(f"\n计分条数: {total_n}  hit {total_h} ({total_h / total_n:.0%})  "
              f"partial {total_p}  (partial 按 0.5 折: {(total_h + 0.5 * total_p) / total_n:.0%})")
        print(f"分母说明: 24 条中断言表分母 23 (排除 {len(set(excluded))} 条), 本窗口计分 {total_n} 条")
    if excluded:
        print(f"排除(结构上不可判, 不记 miss): {', '.join(sorted(set(excluded)))}")
    if ambiguous:
        print(f"暂无法判定(证据不足, 不记 miss): {', '.join(sorted(set(ambiguous)))}")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"validate", "seal", "verify", "score", "brief"}:
        print(__doc__)
        return 2
    doc = load_yaml(CLAIMS)
    return {"validate": cmd_validate, "seal": cmd_seal,
            "verify": cmd_verify, "score": cmd_score, "brief": cmd_brief}[sys.argv[1]](doc)


if __name__ == "__main__":
    sys.exit(main())
