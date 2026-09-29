# v0.2-alpha 本地试评分产物

由项目根目录运行 `.venv/Scripts/python.exe tools/run_quant_validation.py` 复现。

- `scores_comparison.csv`：62条逐条旧/新类型、四维分、候选积分、发布积分与复核状态。
- `artifacts_scorecard.json`：完整预处理、摘要、证据、限制、指标、评分理由及版本。
- `metrics.csv`、`eda.json`：10指标矩阵与按来源划分的描述统计。
- `scorecard.json`：冻结的分位切点、退化标记、校准记录摘要哈希。
- `design_disagreements.csv`：与模拟素材作者设计类型不一致的记录，供人工查看。
- `validation_summary.json`：实跑分组汇总、环境版本与验证范围。

详细报告和流程图见 [PART2_SCORECARD_VALIDATION.md](../../PART2_SCORECARD_VALIDATION.md)。这是同62条探索定标后回代的结果，不是独立测试。旧/新分数尺度发生变化；全部alpha记录PendingReview，不发布员工积分。原有12条中11条为测试数据，新增50条全部为模拟数据。
