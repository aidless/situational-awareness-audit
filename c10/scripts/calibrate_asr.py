#!/usr/bin/env python3
"""仪器校准：ASR 转写能否用于「数词」？

背景：C10 被测量是「产出性内部独白的词数」。若用语音转写自动出词数，
必须先验证转写工具的目标函数（还原语义）与被测量定义（数词）是否一致。

已实测结论（2026-10-24，见 calib/asr_calibration.json）:
  中文 TTS 朗读 82 个汉字 → faster-whisper tiny 转写 79 个汉字，字符保留率 0.963；
  但 **填充词保留 0/3**，字符级相似度仅 0.714。
  即：总字数看起来对得上，是因为「删掉填充词」与「插入错字」在计数上互相抵消了。
  逐字比对后才能看出这不是「数得准」，而是「错误相互抵消」——
  而 C10 恰恰只关心填充词那一部分，正好是被删干净的那部分。

故协议规定：转写方法必须记 manual，用 asr_calibrated 前须先做个体校准。

依赖:
    pip install faster-whisper
    export HF_HUB_DISABLE_XET=1 HF_ENDPOINT=https://hf-mirror.com   # 国内镜像

用法:
    python calibrate_asr.py --audio x.wav --truth x.txt
    python calibrate_asr.py --selftest-text     # 仅检查分词/计数逻辑，无需模型
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import wave
from pathlib import Path

import numpy as np

FILLER_ZH = ["嗯", "呃", "啊", "哦", "唉", "诶"]
FILLER_EN = [r"\bum\b", r"\buh\b", r"\ber\b", r"\bhmm\b", r"\byou know\b", r"\bI mean\b"]


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*|[\u4e00-\u9fff]+", text)


def filler_count(text: str) -> int:
    n = sum(text.count(f) for f in FILLER_ZH)
    for pat in FILLER_EN:
        n += len(re.findall(pat, text, flags=re.I))
    return n


def load_wav16k(path: Path) -> np.ndarray:
    """读 16k 单声道 wav 为 float32。用 wav+numpy 而非 av，
    因为 faster-whisper 依赖的 av 版本与本机 PyAV 的 `metadata_errors` 参数不兼容。"""
    with wave.open(str(path)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("需先转成 16k 单声道: ffmpeg -i in.wav -ar 16000 -ac 1 out.wav")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(audio: np.ndarray, model_size: str = "tiny", lang: str = "zh") -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("需要 faster-whisper: pip install faster-whisper")
    # initial_prompt 让输出简体+带标点，否则默认输出繁体且几乎无标点（首版踩过）
    prompt = "以下是普通话的句子，使用简体中文。" if lang == "zh" else ""
    m = WhisperModel(model_size, device="cpu", compute_type="int8",
                     download_root=os.environ.get("WHISPER_CACHE",
                                                  os.path.expanduser("~/.cache/whisper")))
    segs, _info = m.transcribe(audio, beam_size=5, language=lang,
                               vad_filter=False, initial_prompt=prompt)
    return "".join(s.text for s in segs).strip()


def compare(truth: str, hyp: str) -> dict:
    cjk_t = len(re.findall(r"[\u4e00-\u9fff]", truth))
    cjk_h = len(re.findall(r"[\u4e00-\u9fff]", hyp))
    ft, fh = filler_count(truth), filler_count(hyp)
    sim = difflib.SequenceMatcher(None, truth, hyp).ratio()
    return {
        "truth_units": cjk_t or len(words(truth)),
        "hyp_units": cjk_h or len(words(hyp)),
        "retention": round((cjk_h or len(words(hyp))) / max(cjk_t or len(words(truth)), 1), 4),
        "truth_fillers": ft,
        "hyp_fillers": fh,
        "filler_retention": round(fh / ft, 4) if ft else None,
        "char_similarity": round(sim, 4),
    }


def verdict(r: dict) -> tuple[str, str]:
    """判 ASR 是否可用于数词。三个条件须全部满足。"""
    problems = []
    if r["retention"] < 0.95:
        problems.append(f"字数保留 {r['retention']:.1%} < 95%")
    if r["filler_retention"] is not None and r["filler_retention"] < 0.80:
        problems.append(f"填充词保留 {r['filler_retention']:.0%} < 80%（C10 只关心这部分）")
    if r["char_similarity"] < 0.95:
        problems.append(f"字符相似度 {r['char_similarity']:.1%} < 95%")
    if problems:
        return "UNUSABLE", "；".join(problems)
    return "USABLE", "全部条件满足，但仍须按个体口音复核"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio")
    ap.add_argument("--truth")
    ap.add_argument("--model", default="tiny")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--selftest-text", action="store_true")
    args = ap.parse_args()

    if args.selftest_text:
        t = "嗯，这个我认为，呃，贪心是对的，然后呢我们看交换论证。"
        h = "这个我认为贪心是对的，我们看交换论证。"
        ft, fh = filler_count(t), filler_count(h)
        print("分词/计数逻辑自测:")
        print(f"  真值填充词 {ft} / 转写 {fh}")
        assert ft == 2 and fh == 0, "填充词计数不符预期"
        print("  PASS —— 逻辑可用。真实校准需音频。")
        return 0

    if not (args.audio and args.truth):
        ap.error("需要 --audio 与 --truth")

    truth = Path(args.truth).read_text(encoding="utf-8")
    audio = load_wav16k(Path(args.audio))
    hyp = transcribe(audio, args.model, args.lang)
    r = compare(truth, hyp)
    r.update(seconds=round(len(audio) / 16000, 2), model=args.model, lang=args.lang)

    for k, v in r.items():
        print(f"{k:18} {v}")
    print()
    tag, why = verdict(r)
    print(f"结论: {tag} —— {why}")
    print("\n真值:", truth[:120])
    print("转写:", hyp[:120])

    out = Path("calib/asr_calibration.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**r, "verdict": tag, "reason": why}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
