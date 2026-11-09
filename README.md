# Situational Awareness 断言审计

## 问题

对 Leopold Aschenbrenner《Situational Awareness》里已封存的断言做跨时间审计：阈值事先 sha256 锁定，到期后按协议记分，改阈值必须留痕。
这不是预测市场，也不对「会不会发生」定价。
现在还没有终分：多数到期日在未来；2026Q4 里的 C19 miss 与 C15 partial 都是窗口内中间记录，不是终判。

## 状态

**STATUS: WORK-IN-PROGRESS** — 还不到 A。下面任何一条还在，就不是终审，也不是 A。

- 多数断言的到期日在 2027 及以后。全表没有终分。2026Q4 的两条记录窗口都还开着：C19 miss 到 2026-12-31，C15 partial 到 2027-06-30。
- 单人审计。`interrater/` 已预注册，没有真人判定者的数据，一致性还没测。
- C10 要求至少 12 名被试。仪器在，数据不在。这是证据未收集，不是 miss。
- 可迁移的部分写在 `METHOD.md`（七道闸门）。这不是一个可安装的通用库：没有第二个语料，没有对外 API。
- C02 的 OOM 加总要等组成断言到期才能算。`drift` 只检查去重规则还在，不算总数。

直接推到默认分支、同时改写 `seal_history.jsonl` 使新提交看起来自洽时，每周定时任务对不上推送前的哈希。pull request 与 push 上的 `trail` 才对照基线。见 `FAILURE_MODES.md`。

同一段话的英文：

An audit of sealed claims over time: thresholds are sha256-locked, then scored on their deadlines.
This is not a prediction market.
There is no final score yet; the 2026Q4 C19 miss and C15 partial are interim.

## 离线复现

不需要原文 PDF。新克隆后只装 `pyyaml`。这条路径应在一刻钟内结束，实际是秒级：

```bash
pip install -r requirements.txt
python3 audit.py validate   # 结构；打印断言条数与计分分母
python3 audit.py verify     # 封存哈希、条数与 seal.json、历史留痕
python3 audit.py drift      # METHOD、证据缺失不计 miss、OOM 去重规则
python3 audit.py score      # 有 data/scores/ 就打印，并标明非终判
```

`validate` / `verify` / `drift` / `score` 都会在 CI 里跑。评分文件不存在时 `score` 退出码为 0，并说明这是「还没判」，不是 0 分。

## 当前状态

| 项 | 值 |
|---|---|
| 断言数 | **24 条**（其中 C24 排除不计分 → 校准分母 **23**） |
| 封存 | 已封存，`claims_sha256` 见 `data/seal.json` |
| 判定时间线 | 2026-12-31（1 条）→ 2027-06-30（1 条）→ **2027-12-31（12 条集中到期，占计分表 52%）** → 2028（7 条）→ 2029–2030（2 条） |
| 已完成评分 | 2026Q4 中间评分：C19 miss、C15 partial（均非终判） |

## 五条核心纪律

**① 预注册封存。** 阈值写完后生成 sha256，`audit.py verify` 会拦住任何事后修改。已经发生过一次：修正 C10 的折算系数时闸门正确报 FAIL，最终走「明示修正 + 归档旧封存 + 重封存」。封存的价值不在于不许改，在于**改了必须留痕**。

**② 区分「没判」与「判错」。** C24 因为无法操作化而被**排除**而非降级——改写不是审计，分母 24→23。C01 的证据源可能到期时已停更，设了 F3 规则：证据缺失最多判 partial，不能记 miss。脚本层面为此修过 bug：原来把任何非 hit 都算进 miss 桶。

**③ 给弱断言找可操作替身，并明说放宽了多少。** C13 的「十年压一年」换成压缩比 K，门槛从 10x 降到 3x，报告里直接写「这是宽松化」。

**④ 加法前先去重。** C02 的六条去重规则防止同一收益在 OOM 加法里被计两次（C07/C08 存在包含关系、C11 是系数不是加法项等）。判折算率组要**加总**，不是逐条平均。

**⑤ 数字在正文，标签在表格。** C02 必须报三轴贡献占比而非只报 Total；C10 若判 ambiguous，结论句必须直接给出中位数、IQR 与二者之比。防止一个标签把结论吞掉。

## 三种失效模式

这三类是书里的数字会怎样出错。审计器自己会怎样把账记错（事后改阈值、把证据缺失记成 miss、OOM 重复计入），见 `FAILURE_MODES.md`。

书里的三类，按发现难度递增：

1. **口径可换** —— 数字取错了，能查出来。
2. **数字不存在** —— 如「人类思维速率」，从来没人测过，得先造定义再造仪器（这就是 C10）。
3. **数字存在于错误的位置** —— 最难发现。C04 的 `0.5 OOM/年` 是真数，但它是**推导前提**不是结论；C11 的 `1.2:1` 也是真的，但那是 Hex 棋盘游戏的实测，作者外推到语言模型时已悄悄换成 `1.33:1`。**任何单句引用都准确，只有放回 OOM 加法里才暴露。它伪装成"数字都对"。**

## 一条预注册判断

C02 的预算是 `A_phys + A_algo ≈ 4.4 OOM`，已落在作者 3–6 的区间内。所以最可能的结局是**总数命中，但「unhobbling 是主杠杆」的归因落空**——数字对了，归因错了。这比单纯的预测对错更有意思。

## 目录结构

```
├── METHOD.md              可迁移的七道闸门（本项目的通用部分）
├── FAILURE_MODES.md       审计器自身怎样把账记错（改阈值、证据缺失、OOM 重复计入）
├── EVIDENCE_2027.md       2027-12-31 到期的 12 条证据收集预案（源预登记 + 快照纪律）
├── PROVENANCE.md          原文出处 · sha256 · 复现方式（原文不随仓库分发）
├── LICENSE                代码 MIT
├── LICENSE-DOCS.md        文档与数据 CC BY 4.0
├── report.html            审计报告
├── LOCKED_*.md            六批锁定记录，含每条的判断依据与自纠
├── data/claims.yaml       24 条断言 · 阈值 · 判定协议
├── data/seal.json         封存记录
├── data/seal_history.jsonl  历次封存
├── data/schedule.md       判定台历（deadlines.py 生成，CI 防漂移）
├── data/scores/*.json     按季度评分
├── audit.py               校验 / 封存 / 评分
├── deadlines.py            到期日机械计数
├── c10/                   C10 实证包
└── interrater/            IR-1 判定者间一致性实验（出包 / 统计 / 预注册）
```

`raw/`（原文 PDF 与逐页文本）**不在本仓库**，版权原因与复现方式见 `PROVENANCE.md`。

## 使用

```bash
# 离线路径见上文。下面是同一套命令，外加封存与台历。
python audit.py validate
python audit.py verify
python audit.py drift
python audit.py score        # 有评分文件才有逐条输出；窗口未关的标为非终判
python audit.py brief        # 待锁定阈值清单（当前应为 0 条）
python audit.py seal --reason "改了什么、为什么"   # 仅在断言表已改、且 verify 为 FAIL 时

python deadlines.py --write   # 重新生成判定台历（CI 会比对，防手抄漂移）

# IR-1 判定者间一致性实验
python interrater/packet_gen.py --n 12 --seed 20261025 --strict   # 出盲判包
python interrater/kappa.py ratings_A.csv --map <包>/_map.json     # 算一致性
python interrater/selftest_pipeline.py                            # 判别力自测
```

依赖：`pyyaml`（`requirements.txt`）。C10 实证包的完整功能另需 `tiktoken`、`faster-whisper`、`piper-tts`，见 `c10/requirements.txt`。那些不进离线审计路径，也不进 CI 的判定检查。

## CI

[![audit](https://github.com/aidless/situational-awareness-audit/actions/workflows/audit.yml/badge.svg)](https://github.com/aidless/situational-awareness-audit/actions/workflows/audit.yml)

徽章只表示 `audit.yml` 有没有变红，不是审计分数，也不是终判。

涉及 `data/`、`audit.py`、`README.md`、`METHOD.md`、`FAILURE_MODES.md`、`deadlines.py`、`interrater/` 的推送与 PR 会跑 `.github/workflows/audit.yml`，另外每周一 09:00 UTC 巡检一次。清单与脚本一致：

1. **结构校验** —— `audit.py validate`。字段齐全，并打印条数与计分分母
2. **封存一致性** —— `audit.py verify`。sha256 与 `claim_count` 必须等于 `seal.json`。变红意味着有人在封存后改了断言表，必须走「明示修正 + 归档 + `seal --reason`」
3. **漂移** —— `audit.py drift`。条数对不上封存或 `METHOD.md` 的分母、证据缺失被记成 miss、OOM 去重规则被拿掉，都会变红
4. **评分打印** —— `audit.py score`。有 `data/scores/` 就逐条打印，窗口未关的标为非终判。没有终分
5. **留痕** —— `audit.py trail`。只在 pull request 和 push 上对照基线。哈希变了而历史里没有旧哈希，或已写下的判定被删掉、改判却没有 `revision_note`，就变红。每周定时任务没有基线，不做这一条
6. **C10 判定器自测** —— 判定带边界、唯一分母口径、synthetic 硬闸门
7. **台历漂移** —— 重新生成 `data/schedule.md` 并比对。到期条数是可机械导出的量，**手抄必漂移**：本项目曾把「2027 全年 13 条」误挂到「2027-12-31 当天」上（当天实为 12 条，C15 在 06-30）。改由 `deadlines.py` 生成并由 CI 比对后才不会重复发生
8. **预注册完整性** —— `interrater/PREREG.md` 的 sha256 是否仍等于 `PREREG.sha256`。与第 2 条同理：分析计划也不能在看到数据之后改
9. **一致性统计自测** —— kappa 的解析解校验（含线性加权、单类别退化、独立随机应趋近 0）
10. **判定包生成** —— 按固定 seed 出包，验证盲化与泄漏扫描仍有效
11. **判别力自测** —— 用合成判定者验证流程能显示出预注册预期的分化（若连已知强弱的分化都显示不出，真实数据也无法解读）
12. **语法检查** —— 全部脚本可编译
13. **静态检查** —— `ruff` 查未定义名 / 重复定义 / 冗余导入。加这条的直接动因是一次真实事故：`calibrate_asr.py` 用了 `os.environ` 却没 `import os`，`py_compile` 通过、CI 全绿，函数一调就 `NameError`。**编译级检查抓不到名字解析错误**，只有静态分析能

除 ruff 之外都不需要原文 PDF（本仓库不含原文），运行时依赖只有 pyyaml。这是刻意的：**一个需要原文才能变绿的 CI 是没用的 CI。**

依赖分两个文件：`requirements.txt` 只放 CI 真正用到的 `pyyaml`，`c10/requirements.txt` 放 C10 全功能所需的 `tiktoken` / `faster-whisper` / `piper-tts`。分开是为了让 CI 保持轻量。

## C10 实证包

24 条里唯一一条协议明写「不接受二手引用、必须自做 ≥12 被试实证」的断言：作者的 `~100 tokens/分钟` 是「1 亿 AI 研究者等效」的唯一分母，而在全篇 165 页里它是唯一一个没有出处的数字。

`c10/` 下有完整的协议、12 题冻结题库、分段计时采集器、统计判定脚本、以及 ASR 转写校准的实测结果。**判定目前是 `pending`——工具全就绪，缺 12 个被试的数据。**

两个已查出的问题值得一提：
- 已封存的协议里原写「英文 0.75 词/token、中文 1.5 字/token」，那是 bpe 时代常数；改用 `o200k_base` 实测后是 1.1216 与 0.8492，**两个偏差方向相反**，会让中英被试的可比性完全失真。
- 用 ASR 自动转写看起来可行（字符保留率 96.3%），但填充词保留率是 **0%**——删词与错字在总数上互相抵消。故协议强制人工转写。

## 可迁移的协议

这个仓库里真正通用的不是 24 条断言，是 `METHOD.md` 里那套流程：抽取（G1）→ 定位（G2）→ 操作化准入（G3，T1/T2）→ 去重（G4）→ 阈值五要素（G5）→ 预注册封存（G6）→ 判定与归因（G7）。

适用于任何以数量级主张为核心的预测文本：行业报告、政策白皮书、投研结论、评测论文的 claim 段。

三条最值得单独记住的：

- **G2 定位**：同一个数在「结论位 / 前提位 / 系数位」上判定方式完全不同。把前提当结论、把系数加成加数，是唯一一种「所有数字都对但论证仍错」的失效模式。
- **G3 准入**：降级的前提是「降级后判的仍是作者的主张」。做不到就**排除**，不是降级——否则那是改写，不是审计。
- **G7 纪律**：`ambiguous` 与 `unavailable` 不得计入 miss。「没判」和「判错」在统计上是两件事，任何「非 hit 即 miss」的实现都会把证据缺失系统性记成断言失败。

## IR-1：把「单人审计」这条边界变成数字

`interrater/` 是一个已预注册、尚未收数据的实验。它要回答的不是「这些断言对不对」，而是**这套协议是否足以让别人得出同样的判定**。

设计上的三个决定：

- **主结局是可判定性评级，不是 hit/miss。** 12 条到期日在 2027–2028 年，让判定者对未发生的事判 hit/miss 本身不成立。故问的是「若到期日已到且数据齐全，这条能否被无争议地判定」，取 `mechanical` / `contested` / `unjudgeable`。全部条目今天就能答。
- **组内两条件，顺序固定**：先盲判（只给摘录与阈值，不给协议），提交后再给协议。代价是学习效应，故协议带来的改善只能当上界。
- **预注册明确拒绝用 kappa 做假设检验。** 13 条时 bootstrap 95% CI 宽度约 **0.61**——k=0.45 与 k=0.05 在这个样本量下无法区分。所以主要结局是描述性的分层一致率，kappa 只作次要摘要，不报 p 值。**这不是保守，是因为报了就会错。**

另设一条对照：C24（已因无法操作化被排除）混在盲判包里。若独立判定者也给不出阈值，则排除决定获得外部支持；若多数判定者给出了明确结论，则当初的排除依据不足，须在报告中更正。

状态：预注册已封存（`interrater/PREREG.sha256`，CI 看守），判定包可复现生成，缺 2–3 名判定者。

## 边界

这是一个**单人审计**。24 条的判定会受审计者的口径选择影响：去重规则、排除决定、数据源优先级均由一人裁定。它不能替代同行评审，只能提供一份**可复现的判定记录**——任何人拿到同一份原文、同一套阈值，应该得出同样的判定。这是它能承诺的全部。

这句话现在有对应的测量，而不再只是一句声明：见上文 **IR-1**。它的目的不是把这条边界消掉，而是把分歧发生在哪一类断言上定位出来——如果分歧集中在需自造定义的那几条，那正好说明协议起作用的地方与不起作用的地方各在哪里。

## 许可

代码 MIT（`LICENSE`）；文档与数据 CC BY 4.0（`LICENSE-DOCS.md`）。原文不在此仓库内，其版权归原作者；`claims.yaml` 中的简短摘录仅用于定位与核对，同样不受本仓库许可约束。
