# Bench — Situational Awareness 断言审计基准

> 本目录登记 situational-awareness-audit 的**真实基准**：可复现的 CI 十检查、C10 实证校准、
> IR-1 判定者间一致性实验。所有数字都能从仓库内落盘文件重取（命令列在下方）。

## 基准 1 — CI 十检查（可复现验证，2026-11-01 实测全部 PASS）

| # | 检查 | 真实行为 | 复跑命令 |
|---|---|---|---|
| 1 | 断言解析 | 24 条断言字段齐全、阈值格式合法 | `python audit.py validate` |
| 2 | 封存一致性 | `claims.yaml` sha256 必须仍等于 `seal.json` 记的值 | `python audit.py verify` |
| 3 | C10 判定器自测 | 判定带边界、唯一分母口径、synthetic 硬闸门 | CI |
| 4 | 台历漂移 | `deadlines.py` 重新生成并比对 | `python deadlines.py --write && git diff --exit-code data/schedule.md` |
| 5 | 预注册完整性 | `interrater/PREREG.md` sha256 必须等于 `PREREG.sha256` | `sha256sum -c interrater/PREREG.sha256` |
| 6 | 一致性统计自测 | kappa 解析解（线性加权 / 单类别退化 / 独立随机趋近 0） | `python interrater/kappa.py --selftest` |
| 7 | 判定包生成 | 固定 seed 出包，验证盲化与泄漏扫描 | `python interrater/packet_gen.py --n 12 --seed 20261025 --strict` |
| 8 | 判别力自测 | 合成判定者能显示预注册预期的分化 | `python interrater/selftest_pipeline.py <最新包>` |
| 9 | 语法检查 | 全部脚本可编译 | `python -m py_compile audit.py deadlines.py interrater/*.py` |
| 10 | 静态检查 | `ruff` 查未定义名 / 重复定义 / 冗余导入 | `ruff check --select F821,F811,F401 ...` |

## 基准 2 — C10 实证校准（真实测量，`c10/calib/`）

| 指标 | 实测值 | 来源 |
|---|---|---|
| 字符保留率 | 96.34% | `c10/calib/asr_calibration.json`（retention 0.9634） |
| 填充词保留率 | **0%**（< 80% 门槛 → verdict `UNUSABLE`） | 同上（filler_retention 0.0） |
| 字符相似度 | 71.4%（< 95% 门槛） | 同上（char_similarity 0.7143） |
| 英文 词/token | 1.1216（`o200k_base` 实测） | README C10 实证包 |
| 中文 字/token | 0.8492（`o200k_base` 实测） | 同上 |

- **判读**：ASR 自动转写字符保留率高（96.3%）但填充词保留 **0%**——删词与错字在总数上互相抵消，故协议**强制人工转写**（`verdict=UNUSABLE`）。
- **边界**：C10 判定目前 `pending`——工具全就绪，缺 12 个被试的数据。

## 基准 3 — IR-1 判定者间一致性（预注册，`interrater/`）

| 项 | 真实值 | 来源 |
|---|---|---|
| 主结局 | 可判定性评级（mechanical/contested/unjudgeable），非 hit/miss | `interrater/PREREG.md` |
| 抽样 | 12 条分层轮转 + 1 条对照（C24，excluded） | `packet_gen.py --n 12 --seed 20261025 --strict` |
| 包 | 13 条（IT-01…IT-13），A_blind / B_protocol 双条件 | `interrater/packets/20261025T094444/` |
| 预注册假设 | H1（纯数字类 vs 自造定义类一致率差 ≥20pp）、H2（协议减少分歧 ≥25%）、H3（C24 排除获得外部支持） | `interrater/PREREG.md` |
| bootstrap 95% CI 宽度 | ≈0.61（13 条时 k=0.45 与 k=0.05 不可区分） | README IR-1 节 |

- **判读**：预注册**明确拒绝**用 kappa 做假设检验（样本量下报了就会错）；主结局是描述性分层一致率。
- **边界**：组内两条件固定顺序 → 学习效应，协议改善只能当**上界**，不能当净效应。

## 复跑命令

```bash
# 基准 1：本地重放 CI 十检查（2026-11-01 实测全部 PASS）
python audit.py validate && python audit.py verify && python audit.py brief
python deadlines.py --write && git diff --exit-code data/schedule.md
cd interrater && sha256sum -c PREREG.sha256 && python kappa.py --selftest
python packet_gen.py --n 12 --seed 20261025 --strict
python selftest_pipeline.py <最新包路径>

# 基准 2：读 C10 校准（真实测量）
cat c10/calib/asr_calibration.json
```

## Fail-closed（真实代码）

- `audit.py verify`：封存一致性 FAIL 时**拦住**——`claims.yaml` 在封存后被修改必须走「明示修正 + 归档旧封存 + 重封存」，不能悄悄改完直接推（README 核心纪律 ①，已发生过一次：修正 C10 折算系数时闸门正确报 FAIL）。
- **非 hit 即 miss 修复**：任何「非 hit 即 miss」的实现会把证据缺失系统性记成断言失败——G7 纪律明确 `ambiguous` / `unavailable` 不得计入 miss。
