#!/usr/bin/env python3
"""token 折算系数实测。

C10 协议 S4 条原本写「英文 ~0.75 词/token、中文 ~1.5 字/token」。
这两个数是 bpe 时代经验值；作者指的是 GPT-4，故须用 GPT-4 系词表 o200k_base 实测。

用法:
    python token_coef.py                      # 跑内置样本，给出手册常数的偏差
    python token_coef.py path/to/transcript.txt --lang zh
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tiktoken
except ImportError:
    sys.exit("需要 tiktoken: pip install tiktoken")

ENC_NAME = "o200k_base"
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# 手册常数：每 token 对应的词/字数量（bpe 时代经验值）
MANUAL_WORDS_PER_TOKEN = 0.75
MANUAL_CJK_PER_TOKEN = 1.5

SAMPLES = {
    "en": (
        "To prove this greedy algorithm is optimal, we use an exchange argument. "
        "Consider an optimal solution that differs from the greedy one at the earliest "
        "possible position. The greedy choice is at least as good as any alternative at "
        "that step, so we can swap the optimal solution's choice for the greedy choice "
        "without increasing cost. This produces another optimal solution agreeing with "
        "greedy on one more position, contradicting the choice of the earliest difference."
    ),
    "zh": (
        "要证明这个贪心算法最优，我们用交换论证。考虑一个与贪心解最早出现差异的最优解。"
        "在那一位置上，贪心选择至少不劣于任何其他选择，因此我们可以把最优解的选择替换成"
        "贪心选择而不增加代价。这样得到的仍是另一个最优解，且与贪心解多一致一个位置，"
        "这与我们选择最早出现差异的位置相矛盾。"
    ),
}

# 填充词 / 元话语：计数时剔除，因为它们不对应实质思考（见 C10_EXPERIMENT.md §6 V2）
#
# 设计原则: 只剔除「独立成段、且自身不承载命题内容」的片段。
# 中文里「这个」「那」「就是」常作指示代词或谓词（「那个位置」「就是右端点」），
# 全文替换会误删实质内容。故中文只剔除纯语音填充词与纯元话语短语，
# 每剔除一个都须能指着说「它删掉不损失任何命题」。
FILLER_PATTERNS = [
    # 纯语音填充
    re.compile(r"^(嗯+|呃+|啊+|哦+|唉+|诶+|欸+)$"),
    # 纯元话语短语
    re.compile(r"^(然后呢|就是说|怎么说呢|让我想想|我想想|我看看)$"),
    # 英文
    re.compile(r"^(um+|uh+|er+|hmm+|like|you know|I mean|let me think|so)$", re.I),
]


def count_tokens(text: str, encoding: str = ENC_NAME) -> int:
    enc = tiktoken.get_encoding(encoding)
    return len(enc.encode(text, disallowed_special=()))


def strip_fillers(text: str) -> tuple[str, int]:
    """剔除独立成段的填充词与元话语，返回 (清洗后文本, 剔除数)。

    首版的两个缺陷（已修，且会影响结论，故记录）:
      1. 用 `re.split(r"([，。！？；：、,.!?;:\\n]+)", text)` 后把标点分组一起丢弃，
         清洗文本变成无句读的汉字串，`，。` 全丢。
      2. 英文按中文标点切分 —— 整句是一个 piece，永远匹配不上单字填充词，
         等于英文完全不剔除。
    修正后：标点保留、中英分别定切分边界、只剔除长度 ≤3 汉字的独立填充段。
    """
    if not text:
        return "", 0
    text = re.sub(r"\s+", " ", text).strip()
    cjk_ratio = len(CJK.findall(text)) / max(len(text), 1)
    is_zh = cjk_ratio > 0.15
    # 英文: 句读边界；中文: 只要逗顿句号，不用冒号 —— 冒号后常紧跟列表内容
    sep = r"[，。！？；、]+" if is_zh else r"[.!?;\n]+"

    kept, removed = [], 0
    for piece in re.split(f"({sep})", text):
        if not piece:
            continue
        if re.fullmatch(sep, piece):
            kept.append(piece)
            continue
        if is_zh:
            seg = piece.strip()
            if not seg:
                continue
            if re.fullmatch(r"[^\u4e00-\u9fff]{0,3}", seg):  # 纯标点残留
                kept.append(seg)
                continue
            if len(CJK.findall(seg)) <= 3 and any(p.fullmatch(seg) for p in FILLER_PATTERNS):
                # 填充段整体删除，但保留其后的分隔符由下一次循环补上
                removed += 1
                continue
            kept.append(seg)
        else:
            out_words = []
            for w in piece.split():
                if any(p.fullmatch(w.strip(" ,.")) for p in FILLER_PATTERNS):
                    removed += 1
                    continue
                out_words.append(w)
            if out_words:
                kept.append(" ".join(out_words) + " ")

    joined = "".join(kept)
    if is_zh:
        # 删掉填充段后常留下「。，」这类累赘标点或句首标点，压平之。
        # 注意方向：保留**后面**那个标点删掉前面多余的（lookbehind），
        # 用 lookahead 删前面会删掉真正的句号。
        joined = re.sub(r"(?<=[，。！？；、])[，、；]+", "", joined)
        joined = re.sub(r"^[，、；。！？]+", "", joined)
    return re.sub(r"\s+", " ", joined).strip(), removed


def _clean_text(text: str, lang: str) -> str:
    return strip_fillers(text)[0]


def measure(text: str, lang: str | None = None) -> dict:
    """对一段转写做完整折算。lang 为 None 时按 CJK 字符占比自动判定。"""
    cjk_n = len(CJK.findall(text))
    total_chars = max(len(text), 1)
    if lang is None:
        lang = "zh" if cjk_n / total_chars > 0.15 else "en"

    clean, removed = strip_fillers(text)
    n_tok = count_tokens(clean)

    if lang == "en":
        words = len([w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", clean)])
        unit, unit_name = words, "word"
        manual_per_token = MANUAL_WORDS_PER_TOKEN
    else:
        words = len(CJK.findall(clean))
        unit, unit_name = words, "cjk_char"
        manual_per_token = MANUAL_CJK_PER_TOKEN

    if unit == 0:
        return {
            "lang": lang, "unit": unit_name, "unit_count": 0, "tokens": n_tok,
            "tokens_per_unit": None, "manual_tokens_per_unit": round(1 / manual_per_token, 4),
            "error": "empty transcript",
        }

    return {
        "lang": lang,
        "unit": unit_name,
        "unit_count": unit,
        "tokens": n_tok,
        "tokens_per_unit": round(n_tok / unit, 4),
        "manual_tokens_per_unit": round(1 / manual_per_token, 4),
        "manual_bias_pct": round(((1 / manual_per_token) / (n_tok / unit) - 1) * 100, 1),
        "fillers_removed": removed,
        "encoding": ENC_NAME,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="转写文本文件；省略则跑内置样本")
    ap.add_argument("--lang", choices=["zh", "en"], default=None)
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非表格")
    args = ap.parse_args()

    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
        res = measure(text, args.lang)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else res)
        return 0

    rows = []
    for lang, text in SAMPLES.items():
        rows.append(measure(text, lang))

    print(f"编码: {ENC_NAME}  样本: 内置各一段（学术性论述）\n")
    hdr = f"{'语言':<6}{'单位':<12}{'单位数':>7}{'tokens':>9}{'实测 tok/单位':>16}{'手册 tok/单位':>16}{'手册偏差':>10}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['lang']:<6}{r['unit']:<12}{r['unit_count']:>7}{r['tokens']:>9}"
            f"{r['tokens_per_unit']:>16.4f}{r['manual_tokens_per_unit']:>16.4f}"
            f"{r['manual_bias_pct']:>+9.1f}%"
        )
    print(
        "\n含义: 手册偏差为正 = 手册常数会让该语言被试的速率被高估；为负 = 被低估。\n"
        "故 C10 协议 S4 的固定常数应作废，改为对每条转写逐条实测。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
