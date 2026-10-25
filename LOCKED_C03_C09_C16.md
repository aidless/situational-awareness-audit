# 锁定记录：C03 / C09 / C16

锁定时间：2026-10-24
锁定人：liuzewen
机器可读源：`data/claims.yaml`（本条一经 `audit.py seal` 即不可改，仅可追加补记）

---

## 为什么要分三批锁

C19/C15 是「结果类」断言 —— 收入数字、能力比。C03/C09/C16 是「输入类」断言 —— 算力斜率、后训练增益、集群功率。

这个区分很重要：**结果类断言错了，只说明作者的推论跳得太远；输入类断言错了，整条论证的分母就是假的。** 作者的全部结论建立在「三个通道各贡献若干 OOM」之上，而这三个通道的每一条都依赖一个外部数字。C03 是物理算力通道的斜率，C09 是 unhobbling 通道的证据，C16 是物理算力通道的上限。

锁这三条时遇到的核心问题不是「阈值填多少」，而是**三处口径陷阱**。逐一记录。

---

## C03：0.5 OOM/年 —— 一条被口径差掩盖的断言

### 原文

> "For the last decade and a half, primarily because of broad scaleups in investment (and specializing chips for AI workloads in the form of GPUs and TPUs), the training compute used for frontier AI systems has grown at roughly ~0.5 OOMs/year."
> —— p.21

注意这句话的窗口：「the last decade and a half」，即从原文写作时点往回推约十五年，约 2009–2024。样本是「frontier AI systems」，在他自己的图里对应的是跨领域（视觉、语言、多模态）的 notable models。

### 现在的数字不是同一个数

Epoch AI 当前的公开口径是：

| 口径 | 数值 | 覆盖窗口 | 样本 |
|---|---|---|---|
| Epoch 现行 | 5x/年 = **0.7 OOM/年**（90% CI 0.6–0.8），倍增 5.2 个月 | 2020 年起 | 前沿语言模型 top-5 |
| Epoch 历史口径 | 4.4x/年 = **约 0.64 OOM/年** | 2010 年起 | notable models 全样本 |
| 作者断言 | **0.5 OOM/年** | 约 2009–2024 | frontier systems（跨领域） |

**如果拿 0.7 去跟 0.5 比，会得出「作者低估了算力增长，他太保守」的结论。这个结论是错的。**

理由是窗口。0.7 只覆盖 2020 年之后，而 2020–2024 恰好是 GPT-3 到 GPT-4 这一轮超常放量期 —— 作者本人在 p.21 也承认「The compute scaleup from GPT-2 to GPT-3 in a year was an unusual overhang」。用一段超常期的斜率去判一个十五年趋势的断言，等于用有利窗口替被检验者补分。

这跟用不利窗口扣分是同一类错误。审计里两种都要防。

### 因此锁定的判据是「复算作者的数」

```
R1 全样本口径：~2010 年起 notable models 全样本, log10(FLOP) ~ 年份 OLS  → 与 0.5 比
R2 现代口径：  2020-01-01 起前沿语言模型 top-5, 同样 OLS               → 仅旁证
```

判定用 R1，不用 R2，也不直接引用 Epoch 的现行结论。

| 结果 | 判定 |
|---|---|
| R1 ≥ 0.45 | hit —— 与 0.5 之差在作者「roughly」的容差内 |
| 0.35 ≤ R1 < 0.45 | partial（0.5 分） |
| R1 < 0.35 | miss —— 后续所有外推的乘数效应失效 |

同时要求：斜率必须由本审计自行复算，写下数据点数与样本量；若 Epoch 在窗口内更换统计方法（log 底、模型筛选阈值、前沿定义），须同时报告变更前后两个值。否则这条断言就变成「引用一个会变动的二手数字」。

### 这条为什么值得单列

如果 R1 落在 0.5–0.7，那结论是「作者的数字没错，只是用了偏保守的全历史窗口」—— 一个诚实的预测者该得的评价。如果 R1 只有 0.35，那 2027 年 +2 OOM 的推论就缺了分母，而整本《Situational Awareness》的第一部分（Counting the OOMs）就是这条推论的展开。

**这是全表 24 条里，单条错误代价最高的一条。**

---

## C16：1000 MW IT power —— 三个功率口径的陷阱

### 原文

> "~2026: +2 OOMs, ~1M H100-equivalent, $10s of billions, ~1 GW; ~2028: +3 OOMs, ~10M, $100s of billions, ~10 GW"
> —— p.77, Table 4

### 为什么不判 10 GW

作者自己在同页脚注 49 里留了后门：「if instead of needing that amount of power in one location, we could spread it among 100 locations, it'd be a lot easier」。10 GW 单点在美国现有电网下几乎不可能落地，判它会变成判一个作者已经豁免掉的命题。

因此锁定为**跨越 1000 MW 这一个台阶**，检验的是「单体设施是否已进入 GW 级并继续向上」。10 GW 作为第二指标记录，不参与判定。

### 三个功率口径

| 口径 | 含义 | 典型关系 |
|---|---|---|
| **IT power** | GPU 服务器供电 | 1.0x（基准） |
| 设施总功率 facility power | 含冷却 | 约 1.2–1.4x（PUE） |
| 电网接入 / 变电站 / 发电装机 | 许可与容量 | 可高至 2–3x |

**只有 IT power 是主判据。** 用后两者判 hit 属于口径作弊 —— 而这一作弊在 2026 年的财经报道里极其常见（「某公司建了 1.8 GW 的数据中心」通常指电网接入，不是 IT 负载）。

### 数据源优先级

1. SEC 文件中明确的 compute power / GPU server power
2. 公司官方博客或财报会明确给出的功率
3. 第三方独立测绘（Epoch AI Frontier Data Centers，卫星影像 + 冷却设备功率模型）
4. 媒体转述 —— 仅 P3 旁证，不作判定依据

hit 需 (1)(2)(3) 中至少两类独立来源支持。

### 2026-10-25 基线快照

Epoch AI Frontier Data Centers：95 站点、合计 **14.2 GW IT power / 14.8M H100e**、覆盖率 43%。

| 站点 | IT power | H100e | 状态 |
|---|---|---|---|
| Colossus 2（SpaceXAI, Memphis） | **946 MW** | 1,112k | operational |
| Anthropic-Amazon New Carlisle | — | 818k | — |
| Microsoft Fairwater Atlanta | — | 769k | — |
| Google Pryor (North) | — | 637k | — |
| Meta Prometheus | ~600 MW（另一处记 536k H100e） | 536k | — |
| OpenAI Stargate Abilene | — | 509k | — |

在建/规划中的 GW 级：

- **Meta Hyperion**：1,632 MW IT by Q1 2028，4,143k H100e
- **Microsoft Fairwater Wisconsin**：2,263 MW IT by Q2 2028，4,528k H100e

建设周期参考：GW 级设施从开工到 GW 级运行中位 **2.1 年**（90% CI 1.0–3.6 年）。

### 预注册判断：大概率 hit，但须区分两种解释

Colossus 2 已达 **946 MW**，距 1000 MW 差 5.4%，且该公司 S-1 明确规划扩至更高档位，Epoch 测算 Q1 2027 可达 1,531 MW IT。

按此轨迹，本条极可能在 2027 年内判 hit。作者给的时间点是「~2026 年 1 GW」，若实际在 2027 年跨过，属约 1 年延迟 —— 记为 **hit but late**，不改变计数，须在记录中标注。

**但这里有一个必须提前写下的解释歧义**：这一条 hit，既可能是「作者的算力趋势判断正确」，也可能是「某一个具体公司（SpaceXAI）执行超预期，而行业整体节奏未必如此」。这两种解释在数据上不可区分，但在结论上差别很大 —— 前者支持作者的 OOM 计数法，后者只是一个离群点。

因此判定时必须同时记录：**全球 95 站点的 IT power 中位数与分布**，而不只看最大值。若最大值 hit 而中位数远低于趋势线，本条应记为「hit 但分布不支持」—— 分数照算，解释降级。

---

## C09：同一基座的 8x —— 方向性易证，量级难证

### 原文

> "METR ... similarly found very large performance improvements on their set of agentic tasks, via unhobbling from the same GPT-4 base model: from 5% with just the base model, to 20% with the GPT-4 as posttrained on release, to nearly 40% today from better posttraining, tools, and agent scaffolding (Figure 16)."
> —— p.32

### 图 16 的完整数据（作者只引了其中三行）

| 配置 | grab bag 成功率 |
|---|---|
| basic gpt-4-base | 5.0% |
| basic gpt-4-0314 | 20.0% |
| basic gpt-4-0613 | 30.0% |
| chat gpt-4-0613 | 21.0% |
| Chat gpt-3.5-turbo-0613 | 9.0% |
| AutoGPT gpt-4-0613 | 15.0% |
| LangChain ReAct gpt-4-0613 | 21.0% |
| All tools gpt-4-0613 | 32.0% |
| **All tools + RM gpt-4-0613** | **38.0%** |
| All tools + RM gpt-3.5-turbo-0613 | 11.0% |

作者写「nearly 40%」取的是最后一行 38.0%。但看全表会发现两件事：

1. **同代内跨度 2.5x**（15%–38%），全部是 gpt-4-0613，唯一变量是脚手架方式（AutoGPT / LangChain ReAct / all tools / all tools + RM）。也就是说：**脚手架方式比「后训练」更能左右分数。** 把 5%→40% 全归因于「better posttraining」并不准确，作者原文写的是「better posttraining, tools, and agent scaffolding」三个并列 —— 但后续论证里「后训练」被当作了主要机制。
2. **同脚手架下，3.5 与 4.0 差距约 3–4x**（11% vs 38%）。这说明基座能力本身仍是主导变量，不是脚手架能跨越的。

### 锁定判据（三条必须同时成立）

- **T1 方向性**：同一基座 + 更好后训练/工具/脚手架，成功率提升 ≥ 2x
- **T2 量级**：最好配置 / base model 比值 ≥ 5x
- **T3 独立性**：第三方评测机构（METR / AISI）或公开可复现任务集，任务版本固定并记录

| 结果 | 判定 |
|---|---|
| T1 且 T2 且 T3 | hit |
| T1 为真，比值为 2x–5x | partial（0.5 分） |
| 提升 < 2x 或无同基座对照 | miss |
| 任务集被替换或下架 | ambiguous |

### 关键约束：任务集版本必须钉死

grab bag 是 METR 的早期内部套件 —— 条目零散、成功率量级个位数到三成、未以同一形式持续维护。METR 现行的正式公开产物是另外三样：

- **HCAST**：180+ 任务，1 分钟至 8 小时以上，140 名受试者 563 次尝试
- **RE-Bench**：7 个 8 小时开放式 ML 研究工程环境，61 名专家 71 次尝试（ICML 2025）
- **Time Horizon 1.1**：228 任务（GPT-4 时代基线 170 + 73 HCAST 拼接）

**这三者都不能直接与 grab bag 的 5%/40% 比对。** 任务集不同、成功率口径不同、难度标定不同。若判定时改用 RE-Bench 或 TH，必须在记录中明确声明「任务集已变更，本条按方向性 T1 判定，量级 T2 仅作参考」。

### 明确排除的证据类型

- **速度类证据**。「代理比人类快 10 倍提交方案」—— RE-Bench 原文同时记录：代理提交快 10x 以上、成本 $123 vs 人类 $1,855，**但多数代理方案得分接近 0**。速度与成本是这条论证里最常被混用的变量。
- 不同基座之间的进步（2025–2026 模型换了基座，进步不能归因于 unhobbling）
- 只在自建任务集成立、任务集未公开的结果
- 实验室自述有提升而无对照基线

### 预注册判断：hit 或 partial，但解释价值有限

方向性几乎必然成立 —— 工具调用与后训练收益在 2024–2026 已有大量公开证据，Epoch 自己也写明「post-training improvements — especially for domains like coding — stack on top of pre-training gains」。

不确定的是 T2 的 5x 量级，以及 **5% 这个 base model 基线在新任务集上是否还成立**。base model 直接对话成功率极低是 grab bag 的特点，换到 HCAST 式任务可能连个位数都不到 —— 基线越低，比值越容易被放大。

**所以本条即便 hit，它证明的也只是「unhobbling 是独立通道」，不证明作者对该通道 5–30x 有效算力等价增益的量级估计正确。** 这个区分必须写死在判定记录里，否则 hit 会被误读为对整条论证的背书。

---

## 三条的共性

锁完这五条（C19/C15/C03/C16/C09），一个模式已经很清楚：

**作者的每一条断言，其可证伪性都取决于一个他没写出来的口径。** AI 收入指哪条财报科目、训练算力取哪个拟合窗口、功率是 IT 还是 facility、任务集是哪一版、8 小时预算还是 32 小时 —— 每一个都是 2–3 倍量级的判断空间，而作者的结论恰好都落在这些空间的边界附近。

这不是作者不严谨。他在 165 页里给了足够多的脚注与来源分级（他自己就区分了 SF rumor 与 Epoch 估算）。问题在于：**当一个预言的正确性依赖于若干未声明的口径选择时，事后判定就必然会滑向「怎么解释都对」。** 预注册的作用，就是在结果出现之前把这些选择全部固定，让「解释」这条路被堵死。

这也是这套表真正的产出 —— 不是那 24 个 hit/miss，而是这 24 次被迫把模糊措辞翻译成可判定条件的过程。

---

## 下一批建议

剩余 19 条中，建议按「可独立验证程度」排序：

| 顺位 | 条目 | 理由 |
|---|---|---|
| 1 | **C21**（专家监督成本指数增长、最终不可行） | 作者自称「criminally underrated」。可直接做成本微实证，不依赖任何外部数据库 |
| 2 | **C10**（人类 ≈ 100 tokens/分钟） | 全链条分母，从未被测量过。一次小型实验即可给出数点 |
| 3 | **C04**（算法效率 0.5 OOM/年） | 与 C03 同源，Epoch 已有 3.0x/年（0.5 OOM/年，CI 0.4–0.6）可直接对标 |

C06–C11 五个折算率是作者的论证核心，但它们的可判定性普遍偏低（C11 的 1.2:1 推算是 2021 年 Hex 棋盘实验的外推）。建议在 C21/C10 之后集中处理，届时可能只能给出「区间是否被后续证据覆盖」这种较弱形式的判定 —— 这本身也是一个值得写下来的结论。
