# 试次记录字段表

`data/trials.jsonl`，一行一条试次。由 `scripts/probe.py record` 写入，写完即置 `0444`。
`scripts/analyze.py` 只读 `r_active` / `r_total` / `participant` / `category` / `synthetic` 五个字段，其余字段供复现与审计。

## 必填字段

| 字段 | 类型 | 含义 | 谁产生 |
|---|---|---|---|
| `participant` | str | 被试代号，形如 `S01`。不得含真名 | 主试 |
| `task` | str | 任务题号，须存在于 `tasks/tasks.json` | 主试 |
| `category` | str | `analytic` / `coding` / `critical`，由题号查表得出 | 脚本 |
| `lang` | str | `zh` / `en`，决定折算单位（词 或 汉字） | 脚本自动判定，可 `--lang` 覆盖 |
| `t_total_min` | float | 题面呈现至 `finish` 的墙钟分钟数 | 脚本从事件时间戳算 |
| `t_active_min` | float | 剔除 `pause→resume` 后的主动思考分钟数 | 同上 |
| `pauses` | int | 暂停次数 | 同上 |
| `transcript_tokens` | int | 清洗后转写的 token 数（`o200k_base`） | 脚本 |
| `unit` / `unit_count` | str / int | 计量单位（`word` 或 `cjk_char`）与其计数 | 脚本 |
| `tokens_per_unit` | float | **该条转写实测**的折算系数 | 脚本 |
| `fillers_removed` | int | 剔除的填充词与元话语个数 | 脚本 |
| `transcript_method` | str | `manual`（默认可接受）或 `asr_calibrated`（须先过 §5 校准） | 主试 |
| `transcriber` | str | 转写者代号 | 主试 |
| `transcript_sha256` | str | 转写全文哈希，防事后修改 | 脚本 |
| `r_active` | float | **判定的主量** = tokens ÷ t_active_min | 脚本 |
| `r_total` | float | 下界 = tokens ÷ t_total_min，并列报告 | 脚本 |
| `synthetic` | bool | `true` 表示模拟数据。**在场即拒绝判定** | 脚本默认 `false` |
| `notes` | str | 自由备注，须写明任何偏离协议之处 | 主试 |

## 事件流

`events` 是 `{kind, t}` 的列表，`kind ∈ {start, pause, resume, finish}`，`t` 为本地时刻 `%Y-%m-%dT%H:%M:%S`。
`t_total_min` 与 `t_active_min` 完全由此重算 —— 这是「不靠事后回忆」的实现。

## 判定前置检查

`analyze.py` 在出判定前依次检查，任一不通过即输出 `pending` 并说明原因：

1. 是否存在 `synthetic: true` 的记录 → 全部剔除；若原始文件里这些记录与真实记录混在同一文件，整份拒绝判定。
2. 被除数是否 ≥ 12 → 不足则只报数值不报判定。
3. IQR 是否 > 中位数 → 是则判 `ambiguous`（离散度说明这不是稳定的类量）。

## 不得改动的部分

`threshold`（`100 tokens/min within [50, 200]`）、判定带边界、类别拆分阈值（3×）、离散裁决规则，均已在 `data/claims.yaml` 与 `data/seal.json` 中封存（`sha256 45c03a96…`）。分析脚本若要改这些常量，必须先解封并记录理由 —— 而解封本身就意味着这次审计失效。
