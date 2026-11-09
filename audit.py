#!/usr/bin/env python3
"""
Situational Awareness 断言审计 —— 结构校验 / 封存 / 评分

用法:
  python audit.py validate                 结构与完整性校验(封存前必跑)
  python audit.py verify                   封存哈希、条数、历史留痕
  python audit.py drift                    METHOD 与脚本、证据缺失、OOM 去重
  python audit.py score                    读取 data/scores/*.json, 标明非终判
  python audit.py brief                    生成「阈值待锁定」清单
  python audit.py seal [--reason TEXT]     首次封存, 或在留痕后重封存
  python audit.py trail --against GITREV   相对基线, 改哈希或改判必须留痕

设计约束:
  - 已封存的阈值可以改, 但必须走 seal --reason, 把旧封存追加到 seal_history.jsonl
  - 评分脚本不判断真值, 也不把窗口未关的记录写成终判
  - ambiguous / unavailable 不是 miss; 缺证据不得记成判错
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAIMS = ROOT / "data" / "claims.yaml"
SEAL = ROOT / "data" / "seal.json"
HISTORY = ROOT / "data" / "seal_history.jsonl"
SCORES = ROOT / "data" / "scores"
README = ROOT / "README.md"
METHOD = ROOT / "METHOD.md"
FAILURES = ROOT / "FAILURE_MODES.md"
WORKFLOW = ROOT / ".github" / "workflows" / "audit.yml"

REQUIRED = ["id", "section", "page", "quote", "claim_type",
            "author_magnitude", "observable", "threshold",
            "direction", "due", "decisiveness", "notes"]
VALID_DIR = {">=", "<=", "==", ">", "<", "in_range"}
VALID_DEC = {"high", "medium", "low"}
# 进入计分分母的三种结果。其余值不得被当成 miss。
SCORED_VERDICTS = {"hit", "partial", "miss"}
# 没判 / 证据缺失。METHOD.md G7: 不得计入 miss。
NON_MISS_VERDICTS = {"ambiguous", "unavailable"}
# in_range 类阈值必须在 threshold 字段内给出闭区间, 且必须写明双向失配的后果
RANGE_PAT = re.compile(r"\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]")
CENSUS_ARROW = re.compile(r"(\d+)\s*→\s*(\d+)")


def load_yaml(path):
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("需要 pyyaml: pip install -r requirements.txt")
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


def census(doc):
    claims = doc["claims"]
    excluded = [c["id"] for c in claims if c.get("excluded_from_scoring")]
    return {"n": len(claims), "excluded": excluded, "denom": len(claims) - len(excluded)}


def place_verdict(claim, verdict):
    """把一条判定归入桶。结构排除优先; 证据缺失不得落入 miss。"""
    v = str(verdict).strip().lower()
    if v == "excluded" or claim.get("excluded_from_scoring"):
        return "excluded"
    if v in NON_MISS_VERDICTS:
        return v
    if v in SCORED_VERDICTS:
        return v
    return "unknown"


def judgment_status(score, claim, today):
    """到期日前一律不是终判。没有 final 标记时, 过期也不自动升级。"""
    due = date.fromisoformat(str(claim["due"]))
    if score.get("final") is True and today >= due and score.get("window_open") is not True:
        return "终判"
    return "非终判"


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
    info = census(doc)
    verdict = "PASS" if not errors else "FAIL"

    print(f"结构校验: {verdict}  断言 {info['n']} 条  计分分母 {info['denom']}")
    for e in errors:
        print(f"  [错误] {e}")
    for w in warns:
        print(f"  [提示] {w}")
    if pending:
        print(f"  阈值待锁定 {len(pending)} 条: {', '.join(pending)}")
    if info["excluded"]:
        print(f"  结构排除(不进分母): {', '.join(info['excluded'])}")
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


def seal_decision(existing, new_digest, new_count, reason):
    """noop: 哈希与条数都没变, 不许重写时间戳。refuse: 变了但没有理由。"""
    if existing is None:
        return "write"
    if existing.get("claims_sha256") == new_digest and existing.get("claim_count") == new_count:
        return "noop"
    if not str(reason or "").strip():
        return "refuse"
    return "reseal"


def cmd_seal(doc, reason):
    pending = [c["id"] for c in doc["claims"] if not str(c.get("threshold", "")).strip()]
    if pending:
        print(f"拒绝封存: {len(pending)} 条阈值未填 -> {', '.join(pending)}")
        return 1
    digest = sha256_of(CLAIMS)
    info = census(doc)
    existing = json.loads(SEAL.read_text(encoding="utf-8")) if SEAL.exists() else None
    decision = seal_decision(existing, digest, info["n"], reason)
    if decision == "noop":
        print("封存未变化, 不重写 seal.json")
        print(f"  claims_sha256 = {digest}")
        print(f"  claim_count = {info['n']}  计分分母 = {info['denom']}")
        return 0
    if decision == "refuse":
        print("拒绝重封存: 断言表与已封存哈希不一致, 且没有 --reason。")
        print("事后改阈值必须留痕:")
        print('  python audit.py seal --reason "改了什么、为什么"')
        print("该命令先把旧封存追加到 data/seal_history.jsonl, 再写新的 seal.json。")
        return 1
    if decision == "reseal":
        archived = dict(existing)
        archived["superseded_reason"] = reason.strip()
        archived["superseded_at"] = datetime.now().isoformat(timespec="seconds")
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(archived, ensure_ascii=False) + "\n")
        print(f"已归档旧封存: {existing['claims_sha256']}")
    record = {
        "sealed_at": datetime.now().isoformat(timespec="seconds"),
        "claims_file": CLAIMS.name,
        "claims_sha256": digest,
        "claim_count": info["n"],
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
    SEAL.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已封存: {SEAL}")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def check_history(record):
    """历史文件只保存被替换的封存。没有该文件表示尚未重封过, 不视为失败。"""
    errors, notes = [], []
    if not HISTORY.exists():
        return errors, notes
    seen = set()
    last_at = None
    for i, line in enumerate(HISTORY.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"seal_history 第 {i} 行不是 JSON")
            continue
        h = row.get("claims_sha256")
        if not h:
            errors.append(f"seal_history 第 {i} 行缺 claims_sha256")
            continue
        if h == record.get("claims_sha256"):
            errors.append("seal_history 含有当前哈希; 历史只保留被替换的封存")
        if h in seen:
            errors.append(f"seal_history 重复哈希 {h[:12]}")
        seen.add(h)
        if "superseded_reason" not in row:
            notes.append(f"seal_history 第 {i} 行是早期归档, 没有 superseded_reason")
        sealed_at = row.get("sealed_at")
        if sealed_at and last_at and sealed_at < last_at:
            errors.append("seal_history 的 sealed_at 倒序")
        if sealed_at:
            last_at = sealed_at
    if last_at and record.get("sealed_at") and record["sealed_at"] < last_at:
        errors.append("当前 seal.json 的时间早于历史中的封存")
    return errors, notes


def cmd_verify(doc):
    errors, notes = [], []
    if not SEAL.exists():
        print("未找到封存文件, 请先执行 seal")
        return 1
    record = json.loads(SEAL.read_text(encoding="utf-8"))
    info = census(doc)
    digest = sha256_of(CLAIMS)
    if record.get("claims_sha256") != digest:
        errors.append("封存不一致: 断言表在封存后被修改。重封必须带 --reason, 旧哈希进入 seal_history.jsonl")
    if record.get("claim_count") != info["n"]:
        errors.append(
            f"条数漂移: seal.json claim_count={record.get('claim_count')} "
            f"与 claims.yaml 的 {info['n']} 不一致"
        )
    hist_errors, hist_notes = check_history(record)
    errors.extend(hist_errors)
    notes.extend(hist_notes)
    print(
        f"封存一致性: {'FAIL' if errors else 'PASS'}  "
        f"断言 {info['n']} 条  计分分母 {info['denom']}  "
        f"seal.claim_count={record.get('claim_count')}"
    )
    print(f"  实际 claims_sha256 = {digest}")
    print(f"  封存 claims_sha256 = {record.get('claims_sha256')}")
    if info["excluded"]:
        print(f"  结构排除(不进分母): {', '.join(info['excluded'])}")
    for n in notes:
        print(f"  [注] {n}")
    for e in errors:
        print(f"  [错误] {e}")
    return 0 if not errors else 1


def readme_problem_lines(text):
    m = re.search(r"^## 问题\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    return [ln for ln in m.group(1).splitlines() if ln.strip()]


def method_census(text):
    return CENSUS_ARROW.findall(text)


def oom_errors(claims):
    """锁定协议里的去重句还在不在。改写这些句子必须连检查一起改, 差值本身就是留痕。"""
    by_id = {c["id"]: c for c in claims}
    errors = []
    for cid in ("C02", "C03", "C04", "C05", "C11"):
        if cid not in by_id:
            errors.append(f"OOM 去重检查缺少 {cid}")
    if errors:
        return errors
    proto = by_id["C02"].get("resolution_protocol") or ""
    for rule in ("D1", "D2", "D3", "D4", "D5", "D6"):
        if rule not in proto:
            errors.append(f"C02 协议缺少去重规则 {rule}")
    if "而非加法项" not in proto:
        errors.append("C02 未写明系数不得作为加法项 (D5)")
    if "系数" not in proto:
        errors.append("C02 协议未写明换算率是系数")
    parts = [p.strip() for p in str(by_id["C02"].get("aggregated_from", "")).split(",") if p.strip()]
    if "C11" not in parts:
        errors.append("C02.aggregated_from 不再列出 C11, D5 会失去盯防对象")
    c04 = str(by_id["C04"].get("threshold", ""))
    if "cumulative" not in c04.lower():
        errors.append("C04 阈值未标明 cumulative, 有与 C03 斜率重复计入的风险")
    if re.search(r"0\.5\s*OOM\s*/\s*year", c04, re.I):
        errors.append("C04 被锁成 0.5 OOM/year, 会与 C03 把同一输入计两次")
    if str(by_id["C03"].get("threshold", "")).strip() == c04.strip():
        errors.append("C03 与 C04 阈值相同")
    if by_id["C11"].get("claim_type") != "conversion_factor":
        errors.append("C11 不再是 conversion_factor, 却仍在 C02 的加总清单里")
    if "不可相加" not in (by_id["C05"].get("resolution_protocol") or ""):
        errors.append("C05 未声明其 OOM 不得与 C02 相加")
    return errors


def interim_errors(doc, today):
    """到期日前关掉窗口或标上 final, 就是把中间记录写成终判。"""
    errors = []
    by_id = {c["id"]: c for c in doc["claims"]}
    if not SCORES.exists():
        return errors
    for f in sorted(SCORES.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"{f.name}: 不是 JSON")
            continue
        for s in payload.get("scores", []):
            claim = by_id.get(s.get("id"))
            if not claim:
                errors.append(f"{f.name}: 未知断言 {s.get('id')}")
                continue
            try:
                due = date.fromisoformat(str(claim["due"]))
            except ValueError:
                errors.append(f"{s.get('id')}: due 无法解析")
                continue
            if s.get("final") is True and today < due:
                errors.append(f"{s['id']}: 到期日 {claim['due']} 未到, 不得标记 final")
            if s.get("window_open") is False and today < due:
                errors.append(f"{s['id']}: 到期日未到却写了 window_open=false")
            if s.get("final") is True and s.get("window_open") is True:
                errors.append(f"{s['id']}: final 与 window_open 同时为真")
    return errors


def fold_scores(claims, entries):
    """entries 按时间顺序。同一条被记两次时, 后一次必须带 revision_note, 且只计一次。"""
    by_id = {c["id"]: c for c in claims}
    folded = {}
    errors = []
    for source, raw in entries:
        cid = raw.get("id")
        claim = by_id.get(cid)
        if claim is None:
            errors.append(f"{source}: 未知断言 {cid}")
            continue
        kind = place_verdict(claim, raw.get("verdict", ""))
        if kind == "unknown":
            errors.append(
                f"{source}: {cid} 的 verdict {raw.get('verdict')!r} 无法归类, "
                "拒绝把它算进 miss"
            )
            continue
        if cid in folded:
            prev = folded[cid]["verdict"]
            if prev != str(raw.get("verdict", "")).strip().lower() and not str(
                raw.get("revision_note", "")
            ).strip():
                errors.append(
                    f"{cid}: 判定从 {prev} 改为 {raw.get('verdict')}, 没有 revision_note"
                )
        folded[cid] = {
            "kind": kind,
            "verdict": str(raw.get("verdict", "")).strip().lower(),
            "score": raw,
            "claim": claim,
            "source": source,
        }
    return folded, errors


def selftest():
    errors = []

    def check(cond, msg):
        if not cond:
            errors.append("selftest: " + msg)

    plain = {"id": "X", "claim_type": "t", "due": "2099-01-01"}
    excluded = {"id": "Z", "claim_type": "t", "due": "2099-01-01", "excluded_from_scoring": True}
    check(place_verdict(plain, "unavailable") == "unavailable", "unavailable 被记成 miss")
    check(place_verdict(plain, "ambiguous") == "ambiguous", "ambiguous 被记成 miss")
    check(place_verdict(plain, "miss") == "miss", "miss 没有进入 miss 桶")
    check(place_verdict(plain, "hit") == "hit", "hit 归类错误")
    check(place_verdict(plain, "partial") == "partial", "partial 归类错误")
    check(place_verdict(excluded, "miss") == "excluded", "结构排除被当成 miss")
    check(place_verdict(plain, "pending") == "unknown", "未知档被静默归桶")
    check(seal_decision(None, "a", 1, None) == "write", "首次封存应写盘")
    check(
        seal_decision({"claims_sha256": "a", "claim_count": 24}, "a", 24, None) == "noop",
        "哈希未变不应重写封存",
    )
    check(
        seal_decision({"claims_sha256": "a", "claim_count": 24}, "b", 24, None) == "refuse",
        "无理由的重封存必须拒绝",
    )
    check(
        seal_decision({"claims_sha256": "a", "claim_count": 24}, "b", 24, "修正笔误") == "reseal",
        "带理由的重封存应放行",
    )
    check(
        seal_decision({"claims_sha256": "a", "claim_count": 24}, "a", 25, None) == "refuse",
        "只改条数也必须留痕",
    )
    folded, fold_errors = fold_scores(
        [plain],
        [("q1", {"id": "X", "verdict": "unavailable"}),
         ("q2", {"id": "X", "verdict": "miss"})],
    )
    check(any("revision_note" in e for e in fold_errors), "改判未要求 revision_note")
    check(folded["X"]["kind"] == "miss", "后一次判定没有留下")
    counts = Counter(item["kind"] for item in folded.values())
    check(counts["unavailable"] == 0 and counts["miss"] == 1, "同一条被计了两次")
    only_missing, _ = fold_scores([plain], [("q", {"id": "X", "verdict": "unavailable"})])
    missing_counts = Counter(item["kind"] for item in only_missing.values())
    check(missing_counts["miss"] == 0 and missing_counts["unavailable"] == 1, "单独的 unavailable 进入了 miss")
    scored_n = sum(missing_counts[k] for k in SCORED_VERDICTS)
    check(scored_n == 0, "证据缺失进入了计分分母")
    return errors


def cmd_drift(doc):
    errors = []
    info = census(doc)
    if not SEAL.exists():
        errors.append("未封存, 无法核对条数")
    else:
        record = json.loads(SEAL.read_text(encoding="utf-8"))
        if record.get("claim_count") != info["n"]:
            errors.append(
                f"条数漂移: seal.json={record.get('claim_count')} claims.yaml={info['n']}"
            )
    if not METHOD.exists():
        errors.append("缺少 METHOD.md")
    else:
        method = METHOD.read_text(encoding="utf-8")
        arrows = method_census(method)
        expected = (str(info["n"]), str(info["denom"]))
        if arrows != [expected]:
            errors.append(
                f"METHOD.md 的分母变化 {arrows or '缺失'} 与注册表 {expected[0]}→{expected[1]} 不一致"
            )
        for word in ("hit", "partial", "miss", "ambiguous", "unavailable"):
            if f"`{word}`" not in method:
                errors.append(f"METHOD.md 未列出判定值 `{word}`")
        if "不得计入 miss" not in method:
            errors.append("METHOD.md 丢失「不得计入 miss」")
        if "seal --reason" not in method:
            errors.append("METHOD.md 未写 seal --reason, 与封存命令不一致")
    if not README.exists():
        errors.append("缺少 README.md")
    else:
        readme = README.read_text(encoding="utf-8")
        lines = readme_problem_lines(readme)
        if lines is None:
            errors.append("README.md 缺少「## 问题」")
        elif len(lines) > 3:
            errors.append(f"README「问题」有 {len(lines)} 行, 超过 3 行")
        elif len(lines) == 0:
            errors.append("README「问题」是空的")
        today = date.today()
        open_ids = []
        for c in doc["claims"]:
            if c.get("excluded_from_scoring"):
                continue
            try:
                due = date.fromisoformat(str(c["due"]))
            except ValueError:
                continue
            if due > today:
                open_ids.append(c["id"])
        if open_ids and "STATUS: WORK-IN-PROGRESS" not in readme:
            errors.append(
                f"还有 {len(open_ids)} 条计分断言未到期, "
                "README 必须标明 STATUS: WORK-IN-PROGRESS"
            )
        if open_ids and re.search(r"Grade:\s*A\b|STATUS:\s*A\b|终分已出", readme):
            errors.append("未到期的审计被写成了终审或 A")
        table = re.search(
            r"断言数.*?\*\*(\d+)\s*条\*\*.*?分母\s*\*\*(\d+)\*\*",
            readme,
            re.S,
        )
        if not table:
            errors.append("README 状态表没有写出断言条数与计分分母")
        elif (int(table.group(1)), int(table.group(2))) != (info["n"], info["denom"]):
            errors.append(
                f"README 状态表 {table.group(1)}/{table.group(2)} "
                f"与注册表 {info['n']}/{info['denom']} 不一致"
            )
        for cmd in ("audit.py validate", "audit.py verify", "audit.py drift", "audit.py score"):
            if cmd not in readme:
                errors.append(f"README 离线路径缺少 {cmd}")
    if not FAILURES.exists():
        errors.append("缺少 FAILURE_MODES.md")
    else:
        text = FAILURES.read_text(encoding="utf-8")
        for phrase in ("事后改阈值", "证据缺失", "OOM"):
            if phrase not in text:
                errors.append(f"FAILURE_MODES.md 未写「{phrase}」")
    if not WORKFLOW.exists():
        errors.append("缺少 .github/workflows/audit.yml")
    else:
        wf = WORKFLOW.read_text(encoding="utf-8")
        for cmd in ("audit.py validate", "audit.py verify", "audit.py drift", "audit.py score"):
            if cmd not in wf:
                errors.append(f"CI 未调用 {cmd}")
    errors.extend(oom_errors(doc["claims"]))
    errors.extend(interim_errors(doc, date.today()))
    errors.extend(selftest())
    print(
        f"漂移检查: {'FAIL' if errors else 'PASS'}  "
        f"断言 {info['n']} 条  计分分母 {info['denom']}"
    )
    for e in errors:
        print(f"  [错误] {e}")
    if not errors:
        print("  条数与封存一致; METHOD 的分母、证据缺失、OOM 去重规则与脚本一致")
    return 0 if not errors else 1


def load_score_entries():
    entries = []
    files = sorted(SCORES.glob("*.json")) if SCORES.exists() else []
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        for s in payload.get("scores", []):
            entries.append((f.name, s))
    return files, entries


def cmd_score(doc, today=None):
    today = today or date.today()
    if not SEAL.exists():
        print("未封存即评分会破坏预注册性质, 中止")
        return 1
    files, entries = load_score_entries()
    info = census(doc)
    if not files:
        print("data/scores/ 下无评分文件。这不是 0 分, 是还没有写下判定。")
        print(f"注册断言 {info['n']} 条, 计分分母 {info['denom']}。终分不存在。")
        return 0
    folded, errors = fold_scores(doc["claims"], entries)
    early = interim_errors(doc, today)
    errors.extend(early)
    print("评分报告: 非终分")
    print(
        f"注册断言 {info['n']} 条, 计分分母 {info['denom']} "
        f"(结构排除 {', '.join(info['excluded']) or '无'})。"
    )
    print("下面的比例只覆盖已经写下的判定, 不是计分分母上的校准分, 也不是终判。")
    counts = Counter()
    by_type = {}
    for item in folded.values():
        kind = item["kind"]
        counts[kind] += 1
        if kind in SCORED_VERDICTS:
            bucket = by_type.setdefault(item["claim"]["claim_type"], Counter())
            bucket[kind] += 1
    print(f"评分文件 {len(files)} 份\n按类型 (hit / partial / miss):")
    for t, bucket in sorted(by_type.items()):
        h, p_, m = bucket["hit"], bucket["partial"], bucket["miss"]
        n = h + p_ + m
        rate = f"   hit={h / n:.0%}" if n else ""
        print(f"  {t:32s} {h} / {p_} / {m}{rate}")
    h, p_, m = counts["hit"], counts["partial"], counts["miss"]
    n = h + p_ + m
    if n:
        print(
            f"\n本窗口计入分母的条目: {n}  hit {h}  partial {p_}  miss {m}  "
            f"(partial 按 0.5 折是报告惯例: {(h + 0.5 * p_) / n:.0%}, 不是终分)"
        )
    else:
        print("\n本窗口没有 hit / partial / miss。")
    if counts["excluded"]:
        print(f"排除(结构上不可判, 不记 miss): "
              + ", ".join(sorted(i["score"]["id"] for i in folded.values() if i["kind"] == "excluded")))
    for kind, label in (("ambiguous", "暂无法判定"), ("unavailable", "证据缺失")):
        ids = sorted(i["score"]["id"] for i in folded.values() if i["kind"] == kind)
        if ids:
            print(f"{label}(不记 miss, 不进计分分母): {', '.join(ids)}")
    print("\n逐条:")
    for cid in sorted(folded):
        item = folded[cid]
        status = judgment_status(item["score"], item["claim"], today)
        print(
            f"  {cid}  {item['verdict']}  {status}  "
            f"due {item['claim']['due']}  来自 {item['source']}"
        )
    for e in errors:
        print(f"  [错误] {e}")
    return 0 if not errors else 1


def git_show(rev, path):
    r = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=ROOT, capture_output=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout


def git_files(rev, prefix):
    r = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", rev, prefix],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    return [ln for ln in r.stdout.splitlines() if ln]


def cmd_trail(against):
    if not against or set(against) <= {"0"}:
        print("没有可比较的基线, 跳过留痕对比")
        return 0
    errors = []
    base_raw = git_show(against, "data/seal.json")
    if base_raw is None:
        print(f"无法读取 {against}:data/seal.json")
        return 1
    base_seal = json.loads(base_raw.decode("utf-8"))
    if not SEAL.exists():
        print("工作区没有 seal.json")
        return 1
    head_seal = json.loads(SEAL.read_text(encoding="utf-8"))
    base_hash = base_seal.get("claims_sha256")
    head_hash = head_seal.get("claims_sha256")
    history = HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else ""
    if base_hash != head_hash and base_hash not in history:
        errors.append(
            "封存哈希相对基线变了, 但 seal_history.jsonl 没有基线那条哈希。"
            "这是没有留痕的事后修改。"
        )
    base_scores = git_files(against, "data/scores") or []
    base_scores = [p for p in base_scores if p.endswith(".json")]
    for path in base_scores:
        raw = git_show(against, path)
        if raw is None:
            errors.append(f"无法读取基线 {path}")
            continue
        base_payload = json.loads(raw.decode("utf-8"))
        head_path = ROOT / path
        if not head_path.exists():
            errors.append(f"删除了 {path}: 这是把已写下的判定整文件抹掉")
            continue
        head_payload = json.loads(head_path.read_text(encoding="utf-8"))
        head_by_id = {s["id"]: s for s in head_payload.get("scores", [])}
        for s in base_payload.get("scores", []):
            cid = s.get("id")
            if cid not in head_by_id:
                errors.append(f"{path}: 删掉了 {cid} 的判定 ({s.get('verdict')})")
                continue
            old_v = str(s.get("verdict", "")).strip().lower()
            new = head_by_id[cid]
            new_v = str(new.get("verdict", "")).strip().lower()
            if old_v != new_v and not str(new.get("revision_note", "")).strip():
                errors.append(
                    f"{cid}: 判定从 {old_v} 改为 {new_v}, 没有 revision_note"
                )
    print(f"留痕对比 ({against}): {'FAIL' if errors else 'PASS'}")
    if base_hash == head_hash:
        print("  封存哈希未变")
    else:
        print(f"  基线 {base_hash}")
        print(f"  当前 {head_hash}")
    for e in errors:
        print(f"  [错误] {e}")
    return 0 if not errors else 1


def parse_args(argv):
    reason = None
    against = None
    i = 0
    while i < len(argv):
        if argv[i] == "--reason" and i + 1 < len(argv):
            reason = argv[i + 1]
            i += 2
        elif argv[i] == "--against" and i + 1 < len(argv):
            against = argv[i + 1]
            i += 2
        else:
            return None, None, f"未知参数 {argv[i]}"
    return reason, against, None


def main():
    commands = {"validate", "seal", "verify", "score", "brief", "drift", "trail"}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    reason, against, err = parse_args(sys.argv[2:])
    if err:
        print(err)
        print(__doc__)
        return 2
    if cmd == "trail":
        if not against:
            print("用法: python audit.py trail --against <git-rev>")
            return 2
        return cmd_trail(against)
    doc = load_yaml(CLAIMS)
    if cmd == "seal":
        return cmd_seal(doc, reason)
    if cmd == "score":
        return cmd_score(doc)
    return {
        "validate": cmd_validate,
        "verify": cmd_verify,
        "drift": cmd_drift,
        "brief": cmd_brief,
    }[cmd](doc)


if __name__ == "__main__":
    sys.exit(main())
