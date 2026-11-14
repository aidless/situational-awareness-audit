# --- acceptance_backfill (EVAL_ACCEPTANCE_STANDARD.md P4) ---
# 证据来源: audit.yml（interrater 自测那一行）
# 命令逐字取自该来源，未增删任何参数。
# 归一: python → python3（本机无 python 别名，实测 Error 127）
# 追加: eval/run_cases.py（验收题库，20 条真调本仓 API；模板同 kv-serve-lab/eval）
.PHONY: eval

eval:
	python3 eval/run_cases.py
	python3 interrater/kappa.py --selftest
