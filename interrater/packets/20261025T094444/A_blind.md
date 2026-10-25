# 判定包 · 条件 A · 盲判（无协议）

请**独立**判定下列 13 条断言，在 `ratings_A.csv` 中每行填写一条。
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

本包**不含**判定协议（即不含如何取数、如何折算、如何排除的规则）。若你因此无法判定，请如实填 `ambiguous` + `R2`/`R4`——这正是要被测出来的东西。

### IT-01

- 断言类型: `capability_milestone`
- 原始文件页码: 8

**原文摘录**

> it is strikingly plausible that by 2027, models will be able to do the work of an AI researcher/engineer

**作者给出的量级**: AGI(可替代 AI 研究员) 于 2027 年

**可观测定义**: 双轨 —— (A) METR 时间视野 50% 达 >= 8 小时且 80% 达 >= 2 小时; (B) 完成一项预先登记的、非自选的完整 AI 研究工程闭环

**判定阈值**: `>= 8h at 50% horizon AND >= 2h at 80% horizon, on a METR suite >= v1.1 explicitly declared non-saturated for the evaluated models`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-02

- 断言类型: `capability_gain_decomposition`
- 原始文件页码: 32

**原文摘录**

> METR ... found ... from 5% with just the base model, to 20% with the GPT-4 as posttrained on release, to nearly 40% today

**作者给出的量级**: 同一 GPT-4 基座经 unhobbling 从 5% 到约 40%

**可观测定义**: METR agentic task suite 上固定基座的版本序列得分

**判定阈值**: `>= 8x on same base model (5% -> 40%)`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-03

- 断言类型: `methodological_recommendation`
- 原始文件页码: 120

**原文摘录**

> some simple measurement of legibility and faithfulness ... this direction is criminally underrated in my view

**作者给出的量级**: CoT 可读性/忠实度可被简单测量并保持

**可观测定义**: 三个可计数采纳事件 —— (a) 主流模型卡出现 CoT 忠实度/可读性定量项, (b) 出现被 >=3 家实验室共同引用的公开基准, (c) 有模型因该项不达标而推迟发布或降级定位

**判定阈值**: `== 3 events all observed by 2028-12-31 (partial = exactly 2 of 3)`

**预期方向**: `==`　**到期日**: 2028-12-31

---

### IT-04

- 断言类型: `conversion_factor`
- 原始文件页码: 30

**原文摘录**

> an RLHF'd small model was equivalent to a non-RLHF'd >100x larger model in terms of human rater preference

**作者给出的量级**: RLHF ≈ 100 倍算力

**可观测定义**: 同架构同数据下, RLHF 与未 RLHF 模型在固定偏好评判下的等效规模倍率(以参数量的 log10 差折算)

**判定阈值**: `>= 1.0 OOM equivalent (i.e. >= 10x) at matched preference-judge`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-05

- 断言类型: `quantitative_trend`
- 原始文件页码: 9

**原文摘录**

> we should expect another ~100,000x effective compute scaleup over four years

**作者给出的量级**: 相对 GPT-4 +5 OOM 有效算力(约 10 万倍), 区间 3-6 OOM

**可观测定义**: 组汇总 —— 物理算力轴(他条) + 算法轴(他条) + unhobbling 轴(他条/他条/他条/他条/他条) 按同一 OOM 刻度加总

**判定阈值**: `>= 3.0 OOM total effective compute gain vs GPT-4 by 2027-12-31 (author band 3-6, best guess 5)`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-06

- 断言类型: `quantitative_trend`
- 原始文件页码: 26

**原文摘录**

> we should expect something like 1-3 OOMs of algorithmic efficiency gains (compared to GPT-4) by the end of 2027, maybe with a best guess of ~2 OOMs

**作者给出的量级**: 算法效率 1-3 OOM, 最佳 2

**可观测定义**: 分基准复算 —— 达到预设阈值所需算力/成本的累计下降, 折算为相对 GPT-4 的 OOM

**判定阈值**: `>= 2 OOM cumulative vs GPT-4 (partial band [1, 2))`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-07

- 断言类型: `institutional`
- 原始文件页码: 145

**原文摘录**

> by 27/28 we'll get some form of government AGI project

**作者给出的量级**: 2027/28 出现某种形式的政府 AGI 项目

**可观测定义**: 主要国家是否设立具有直接算力/权重控制权或强制安全审查权的 AGI 专项机构

**判定阈值**: `== at least one of: (a) statutory/executive-agency authority over frontier training clusters with mandatory pre-approval, AND (b) a dedicated budget line >= $10B for a government AGI program — by 2028-12-31`

**预期方向**: `==`　**到期日**: 2028-12-31

---

### IT-08

- 断言类型: `quantitative_trend`
- 原始文件页码: 21

**原文摘录**

> training compute used for frontier AI systems has grown at roughly ~0.5 OOMs/year

**作者给出的量级**: 0.5 OOM/年(约 3.16 倍/年)

**可观测定义**: Epoch AI 前沿训练算力序列的年度拟合斜率

**判定阈值**: `0.5 OOM/year`

**预期方向**: `>=`　**到期日**: 2027-12-31

---

### IT-09

- 断言类型: `capability_milestone`
- 原始文件页码: 63

**原文摘录**

> 2027/28: Proto-automated-researchers, can automate >90% ... 2028/29: 10x+ pace of progress → superintelligence

**作者给出的量级**: 2027/28 自动化 >90%; 2028/29 进入超智能

**可观测定义**: 分段判定 —— 阶段一(>90% 自动化)用任务覆盖率的加权; 阶段二(超智能)用 他条 的加速比 >= 10

**判定阈值**: `Stage-1: >= 90% weighted task-coverage of AI-research subtasks by 2028-12-31; Stage-2: >= 10x compression (他条 scale) by 2029-12-31`

**预期方向**: `>=`　**到期日**: 2029-12-31

---

### IT-10

- 断言类型: `capability_milestone`
- 原始文件页码: 158

**原文摘录**

> Before the decade is out, we will have built superintelligence.

**作者给出的量级**: 2030 年前建成超级智能

**可观测定义**: 无公认标准 —— 本审计判定该条不进入校准分数

**判定阈值**: （本条未给出阈值）

**预期方向**: `==`　**到期日**: 2030-12-31

---

### IT-11

- 断言类型: `conversion_factor`
- 原始文件页码: 35

**原文摘录**

> 100s tokens = a few minutes ... Millions = multiple months (+4 OOMs test-time compute)

**作者给出的量级**: 100 万 token ≈ 数月人类工作量; 人类 ≈ 100 token/分钟

**可观测定义**: 人类实际推理速率(分钟/千 token)的实测; 模型可用 token 上限的实测

**判定阈值**: `100 tokens/min within [50, 200]`

**预期方向**: `in_range`　**到期日**: 2027-12-31

---

### IT-12

- 断言类型: `structural`
- 原始文件页码: 109

**原文摘录**

> RLHF will predictably break down as AI systems get smarter ... human labeler-pay has gone from a few dollars for MTurk labelers to ~$100/hour for GPQA questions

**作者给出的量级**: 人类监督成本随能力上升而指数增长, 最终不可行

**可观测定义**: 专家标注单位成本的时间序列; 专家标注相对模型能力的判别力(信噪比)

**判定阈值**: `2.5x per OOM of capability_gain, on labeler cost per usable judgment`

**预期方向**: `>=`　**到期日**: 2028-12-31

---

### IT-13

- 断言类型: `structural`
- 原始文件页码: 95

**原文摘录**

> stealing the algorithmic secrets will be worth having a 10x or more larger cluster ... this could easily be worth 10x-100x compute

**作者给出的量级**: 算法秘密价值 = 10-100 倍算力

**可观测定义**: 代理指标 —— 开源最佳模型相对闭源前沿的等效算力差距, 用「落后月数 x 该期前沿算力斜率」折算为 OOM

**判定阈值**: `>= 1.0 OOM computed gap for >= 24 consecutive months, AND one independently verified leak of a frontier-relevant algorithmic recipe with third-party reproduced effect >= 3x compute-equivalent`

**预期方向**: `>=`　**到期日**: 2027-12-31

---
